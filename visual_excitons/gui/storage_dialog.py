"""
The Results and storage dialog: whether results go in session files and are
kept between runs, how much space they may take, the cached symmetry matrices,
and the folder where both are kept. MainWindow applies its values
(MainWindow.openStorageDialog).
"""

import os
from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QCheckBox, QDoubleSpinBox,
                               QSpinBox, QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox, QDialogButtonBox)

from visual_excitons.core.results_cache import droppedBy
from .inspector import NoteLabel

GB, MB = 2 ** 30, 2 ** 20


def formatSize(size):
    return f'{size / GB:.2f} GB' if size >= GB else f'{size / MB:.1f} MB'


class StorageDialog(QDialog):
    """
    The settings of the results and of what is kept on disk. `values`: dict
    with 'storeSessionResults', 'keepResults' (bools), 'cacheLimit',
    'wavefunctionLimit' (bytes) and 'folder' (str); `defaultFolder`: the
    folder offered by Default. `usage` gives, for the folder in use, the sizes
    of the kept results (the most recently used first) and the size of the
    symmetry matrices;
    `clearResults` and `clearSymmetry` delete them and return the space freed.
    """

    def __init__(self, values, defaultFolder, usage, clearResults, clearSymmetry, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Results and storage')
        self.defaultFolder = str(defaultFolder)
        self.usage, self.clearResultsCallback, self.clearSymmetryCallback = usage, clearResults, clearSymmetry

        # Sessions
        self.sessionResultsCheckBox = QCheckBox('Store results in session files')
        self.sessionResultsCheckBox.setChecked(values['storeSessionResults'])
        self.sessionResultsCheckBox.setToolTip('Saved sessions show their results at once when opened, without '
                                               'computing anything')
        sessions = QGroupBox('Sessions')
        QVBoxLayout(sessions).addWidget(self.sessionResultsCheckBox)

        # Results kept between runs
        self.keepResultsCheckBox = QCheckBox('Keep results between runs')
        self.keepResultsCheckBox.setChecked(values['keepResults'])
        self.keepResultsCheckBox.setToolTip('Keep the results of each dataset when it is left or the program closed, '
                                            'and show them again when it is opened (if its databases did not change)')
        self.cacheLimitSpinBox = QDoubleSpinBox(minimum=0.1, maximum=100.0, singleStep=0.5, decimals=1, suffix=' GB')
        self.cacheLimitSpinBox.setValue(values['cacheLimit'] / GB)
        self.cacheLimitSpinBox.setToolTip('Beyond it, the datasets not opened for longest lose their results first')
        # What a lower limit would drop, said before OK
        self.shrinkNote = NoteLabel()
        self.shrinkNote.hide()
        self.cacheLimitSpinBox.valueChanged.connect(self.updateShrinkNote)
        self.wavefunctionLimitSpinBox = QSpinBox(minimum=1, maximum=100 * 1024, singleStep=50, suffix=' MB')
        self.wavefunctionLimitSpinBox.setValue(round(values['wavefunctionLimit'] / MB))
        self.wavefunctionLimitSpinBox.setToolTip('Larger wave functions are not kept (they are computed again when '
                                                 'needed); the other results of their dataset are')
        self.resultsUsageLabel = NoteLabel()
        self.clearResultsButton = QPushButton('Clear')
        self.clearResultsButton.setToolTip('Forget the results kept for every dataset (now)')
        self.clearResultsButton.clicked.connect(self.clearResults)
        resultsUsage = QHBoxLayout()
        resultsUsage.addWidget(self.resultsUsageLabel, 1)
        resultsUsage.addWidget(self.clearResultsButton)
        results = QGroupBox('Results kept between runs')
        form = QFormLayout(results)
        form.addRow(self.keepResultsCheckBox)
        form.addRow('Space for them:', self.cacheLimitSpinBox)
        form.addRow(self.shrinkNote)
        form.addRow('Wave functions up to:', self.wavefunctionLimitSpinBox)
        form.addRow(resultsUsage)
        self.keepResultsCheckBox.toggled.connect(self.updateEnabled)
        self.keepResultsCheckBox.toggled.connect(self.updateShrinkNote)

        # Symmetry matrices
        self.symmetryUsageLabel = NoteLabel()
        self.clearSymmetryButton = QPushButton('Clear')
        self.clearSymmetryButton.setToolTip('Forget the representation matrices kept (now): the next symmetry analysis '
                                            'of each dataset computes them again')
        self.clearSymmetryButton.clicked.connect(self.clearSymmetry)
        symmetryUsage = QHBoxLayout()
        symmetryUsage.addWidget(self.symmetryUsageLabel, 1)
        symmetryUsage.addWidget(self.clearSymmetryButton)
        symmetry = QGroupBox('Symmetry matrices')
        symmetryLayout = QVBoxLayout(symmetry)
        symmetryLayout.addWidget(NoteLabel('The representation matrices of the symmetry analysis (Composition panel) '
                                           'take a while to compute: they are kept for each dataset, for any exciton.'))
        symmetryLayout.addLayout(symmetryUsage)

        # Location
        self.folderEdit = QLineEdit(values['folder'])
        self.folderEdit.setToolTip('The folder where the results between runs and the symmetry matrices are kept')
        browseButton = QPushButton('Browse…')
        browseButton.clicked.connect(self.browse)
        defaultButton = QPushButton('Default')
        defaultButton.setToolTip(f'The cache folder of your system: {self.defaultFolder}')
        defaultButton.clicked.connect(lambda: self.folderEdit.setText(self.defaultFolder))
        folderRow = QHBoxLayout()
        folderRow.addWidget(self.folderEdit, 1)
        folderRow.addWidget(browseButton)
        folderRow.addWidget(defaultButton)
        location = QGroupBox('Location')
        locationLayout = QVBoxLayout(location)
        locationLayout.addLayout(folderRow)
        locationLayout.addWidget(NoteLabel('Both are kept in this folder. Changing it moves what is kept there.'))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for box in (sessions, results, symmetry, location):
            layout.addWidget(box)
        layout.addWidget(buttons)
        self.updateEnabled()
        self.updateUsage()
        self.resize(560, self.sizeHint().height())

    @Slot()
    def updateEnabled(self, *args):
        keep = self.keepResultsCheckBox.isChecked()
        self.cacheLimitSpinBox.setEnabled(keep)
        self.wavefunctionLimitSpinBox.setEnabled(keep)

    def updateUsage(self):
        self.resultsSizes, symmetrySize = self.usage()
        size, count = sum(self.resultsSizes), len(self.resultsSizes)
        self.resultsUsageLabel.setText(f'In use: {formatSize(size)} for {count} dataset{"" if count == 1 else "s"}.')
        self.symmetryUsageLabel.setText(f'In use: {formatSize(symmetrySize)}.')
        self.clearResultsButton.setEnabled(count > 0)
        self.clearSymmetryButton.setEnabled(symmetrySize > 0)
        self.updateShrinkNote()

    @Slot()
    def updateShrinkNote(self, *args):
        """Say how many datasets would lose their results with the space set, if fewer fit than are kept."""
        dropped = droppedBy(getattr(self, 'resultsSizes', []), self.cacheLimitSpinBox.value() * GB)
        if dropped and self.keepResultsCheckBox.isChecked():
            everything = dropped == len(self.resultsSizes)
            self.shrinkNote.setText(f'<span style="color:#e67e22">⚠</span> Less than what is kept now: OK drops the '
                                    + ('results of every dataset.' if everything else
                                       f'results of the {dropped} dataset{"" if dropped == 1 else "s"} not opened for '
                                       'longest.'))
        self.shrinkNote.setVisible(bool(dropped) and self.keepResultsCheckBox.isChecked())

    @Slot()
    def clearResults(self):
        freed = self.clearResultsCallback()
        self.updateUsage()
        self.resultsUsageLabel.setText(self.resultsUsageLabel.text() + f' Cleared {formatSize(freed)}.')

    @Slot()
    def clearSymmetry(self):
        freed = self.clearSymmetryCallback()
        self.updateUsage()
        self.symmetryUsageLabel.setText(self.symmetryUsageLabel.text() + f' Cleared {formatSize(freed)}.')

    @Slot()
    def browse(self):
        folder = QFileDialog.getExistingDirectory(self, 'Folder for results and symmetry matrices',
                                                  self.folderEdit.text() or self.defaultFolder)
        if folder:
            self.folderEdit.setText(folder)

    def values(self):
        cacheLimit = round(self.cacheLimitSpinBox.value() * GB)
        return {'storeSessionResults': self.sessionResultsCheckBox.isChecked(),
                'keepResults': self.keepResultsCheckBox.isChecked(),
                'cacheLimit': cacheLimit,
                'wavefunctionLimit': min(self.wavefunctionLimitSpinBox.value() * MB, cacheLimit),
                'folder': self.folderEdit.text().strip() or self.defaultFolder}

    def accept(self):
        folder = Path(self.values()['folder']).expanduser()
        problem = ''
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if not os.access(folder, os.W_OK):
                problem = 'it cannot be written to'
        except OSError as error:
            problem = str(error)
        if problem:
            QMessageBox.warning(self, 'Results and storage', f'The folder {folder} cannot be used: {problem}.')
            return
        super().accept()
