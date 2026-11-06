"""
Main window: a navigation bar on the left switches between the pages (System,
Spectra, Wavefunction); menus, a status bar and persistent settings frame them.
"""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QStackedWidget, QWidget, QHBoxLayout, QLabel, QFileDialog, QMessageBox,
                               QApplication, QProgressBar, QToolButton)

from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from visual_excitons.core.dataset import findDataset, datasetName, datasetExists
from .options_widget import OptionsWidget
from .graphs_widget import GraphsWidget
from .graphs_3d_widget import Graphs3DWidget
from .navigation_bar import NavigationBar
from .theme import themeManager, THEME_MODES
from .persistence import StateRegistry, GLOBAL, DATASET


# Opened on the first run, when there is no recent dataset (relative to the repository)
DEFAULT_DATASET_FOLDER = Path(__file__).resolve().parents[2] / 'data' / 'BiI3_Bulk_8x8x8'

MAX_RECENT_DATASETS = 8

SYSTEM_PAGE, SPECTRA_PAGE, WAVEFUNCTION_PAGE = range(3)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings('VisualExcitons', 'VisualExcitons')
        self.theme = themeManager()

        self.options = Options()
        self.calculations = Calculations(self.options)
        self.dataset = None

        self.createStyles()
        self.createPages()
        self.createMenus()
        self.createStatusBar()

        # A new SAVE directory invalidates everything computed before; reset
        # first, then redraw the lattice
        self.options.databaseFound.connect(lambda found: self.calculations.resetDataset())
        self.options.databaseFound.connect(self.wavefunctionPage.onDatasetChanged)
        self.options.databaseFound.connect(self.updateDatasetLabel)
        self.options.numQPointsChanged.connect(self.updateDatasetLabel)
        self.options.saveDirChanged.connect(self.updateDatasetLabel)

        self.calculations.busyStarted.connect(self.onTaskStarted)
        self.calculations.busyChanged.connect(self.onBusyChanged)
        self.calculations.progressChanged.connect(self.onProgress)
        self.calculations.taskCancelled.connect(self.onTaskCancelled)
        self.calculations.errorOccurred.connect(self.onError)
        self.calculations.excitonSelected.connect(self.onExcitonSelected)

        self.theme.themeChanged.connect(self.spectraPage.setDarkTheme)
        self.theme.themeChanged.connect(self.wavefunctionPage.setDarkTheme)
        self.setTheme(self.settings.value('theme', 'System'))

        # Parameters kept between sessions (see persistence.py): preferences now,
        # those of a dataset when it is opened
        self.state = StateRegistry()
        self.state.add('spectra', self.spectraPage.inspector.persistence)
        self.state.add('spectraLayout', self.spectraPage.persistence)
        self.state.add('wavefunction', self.wavefunctionPage.inspector.persistence)
        self.state.add('wavefunctionLayout', self.wavefunctionPage.persistence)
        # A dataset opened for the first time starts from the defaults, not from
        # the parameters of the previous one
        self.datasetDefaults = self.state.values(DATASET)
        self.state.restore(GLOBAL, self.loadJson('state', {}))

        if not self.restoreGeometry(self.settings.value('geometry', b'')):
            self.resize(1600, 1000)
        self.setPage(int(self.settings.value('page', SYSTEM_PAGE)))
        self.openInitialDataset()

    # Construction

    def createStyles(self):
        self.dispersionStyle = DispersionStyle()
        self.absorptionStyle = AbsorptionStyle()
        self.bandStructureStyle = BandStructureStyle()

        self.dispersionStyle.setLinkedStyles([self.absorptionStyle, self.bandStructureStyle])
        self.absorptionStyle.setLinkedStyles([self.dispersionStyle, self.bandStructureStyle])
        self.bandStructureStyle.setLinkedStyles([self.dispersionStyle, self.absorptionStyle])

        calc = self.calculations
        self.dispersionStyle.styleChanged.connect(calc.emitExcitonDispersionReady)
        self.absorptionStyle.styleChanged.connect(calc.emitExcitonAbsorption)
        self.bandStructureStyle.styleChanged.connect(calc.emitExcitonBandStructure)

        calc.excitonDispersionNumCurvesChanged.connect(self.dispersionStyle.setNumCurves)
        calc.excitonDispersionInit.connect(self.dispersionStyle.applyDefaultStyle)
        calc.excitonAbsorptionCurveAppended.connect(self.absorptionStyle.appendCurveStyle)
        calc.excitonAbsorptionCurveRemoved.connect(self.absorptionStyle.removeCurveStyle)
        calc.excitonBandStructureNumCurvesChanged.connect(self.bandStructureStyle.setNumCurves)
        calc.excitonBandStructureInit.connect(self.bandStructureStyle.applyDefaultStyle)

    def createPages(self):
        self.systemPage = OptionsWidget(self.options)
        self.spectraPage = GraphsWidget(self.options, self.calculations, self.dispersionStyle, self.absorptionStyle,
                                        self.bandStructureStyle)
        self.wavefunctionPage = Graphs3DWidget(self.options, self.calculations)
        self.spectraPage.inspector.showWavefunctionRequested.connect(lambda: self.setPage(WAVEFUNCTION_PAGE))
        self.systemPage.qPathApplied.connect(self.saveQPath)

        self.stack = QStackedWidget()
        for page in (self.systemPage, self.spectraPage, self.wavefunctionPage):
            self.stack.addWidget(page)

        self.navigation = NavigationBar()
        self.navigation.addPage('System', 'crystal', 'Data, crystal lattice and Q-path (Ctrl+1)')
        self.navigation.addPage('Spectra', 'spectrum', 'Dispersion, absorption and band structure (Ctrl+2)')
        self.navigation.addPage('Wave\nfunction', 'orbital', 'Exciton wave function in real space (Ctrl+3)')
        self.navigation.pageSelected.connect(self.setPage)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def createMenus(self):
        # File
        fileMenu = self.menuBar().addMenu('&File')

        openAction = QAction('&Open dataset…', self)
        openAction.setShortcut(QKeySequence.StandardKey.Open)
        openAction.setStatusTip('Open the folder of a calculation; its SAVE, BSE and GW directories are found automatically')
        openAction.triggered.connect(self.chooseDataset)
        fileMenu.addAction(openAction)

        self.recentMenu = fileMenu.addMenu('Open &recent')
        self.updateRecentMenu()

        fileMenu.addSeparator()
        quitAction = QAction('&Quit', self)
        quitAction.setShortcut(QKeySequence.StandardKey.Quit)
        quitAction.triggered.connect(self.close)
        fileMenu.addAction(quitAction)

        # View
        viewMenu = self.menuBar().addMenu('&View')

        pageGroup = QActionGroup(self)
        self.pageActions = []
        for index, text in enumerate(('&System', 'S&pectra', '&Wave function')):
            action = QAction(text, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(f'Ctrl+{index + 1}'))
            action.triggered.connect(lambda checked=False, index=index: self.setPage(index))
            pageGroup.addAction(action)
            viewMenu.addAction(action)
            self.pageActions.append(action)

        viewMenu.addSeparator()
        self.inspectorAction = QAction('Show &side panel', self)
        self.inspectorAction.setCheckable(True)
        self.inspectorAction.setChecked(self.settings.value('showInspector', True, type=bool))
        self.inspectorAction.setShortcut(QKeySequence('Ctrl+B'))
        self.inspectorAction.toggled.connect(self.setInspectorVisible)
        viewMenu.addAction(self.inspectorAction)
        self.setInspectorVisible(self.inspectorAction.isChecked())

        themeMenu = viewMenu.addMenu('&Theme')
        themeGroup = QActionGroup(self)
        self.themeActions = {}
        for mode in THEME_MODES:
            action = QAction(mode, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, mode=mode: self.setTheme(mode))
            themeGroup.addAction(action)
            themeMenu.addAction(action)
            self.themeActions[mode] = action

        # Help
        helpMenu = self.menuBar().addMenu('&Help')
        aboutAction = QAction('&About Visual Excitons', self)
        aboutAction.triggered.connect(self.showAbout)
        helpMenu.addAction(aboutAction)

    def createStatusBar(self):
        # Running calculation: its message and stage, progress, and a cancel button
        self.taskLabel = QLabel()
        self.taskProgressBar = QProgressBar()
        self.taskProgressBar.setFixedWidth(160)
        self.taskProgressBar.setMaximumHeight(16)
        self.cancelButton = QToolButton()
        self.cancelButton.setText('Cancel')
        self.cancelButton.setToolTip('Stop the calculation and the queued ones (Esc)')
        self.cancelButton.setAutoRaise(True)
        self.cancelButton.clicked.connect(self.calculations.cancel)

        self.taskWidget = QWidget()
        layout = QHBoxLayout(self.taskWidget)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(self.taskLabel)
        layout.addWidget(self.taskProgressBar)
        layout.addWidget(self.cancelButton)
        self.taskWidget.hide()
        self.statusBar().addPermanentWidget(self.taskWidget)

        cancelShortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancelShortcut.activated.connect(self.calculations.cancel)

        self.datasetLabel = QLabel()
        self.datasetLabel.setContentsMargins(8, 0, 8, 0)
        self.statusBar().addPermanentWidget(self.datasetLabel)
        self.updateDatasetLabel()

    # Pages and panels

    @Slot(int)
    def setPage(self, index: int):
        index = min(max(int(index), 0), self.stack.count() - 1)
        self.stack.setCurrentIndex(index)
        self.navigation.setCurrentIndex(index)
        if hasattr(self, 'pageActions'):
            self.pageActions[index].setChecked(True)

    @Slot(bool)
    def setInspectorVisible(self, visible: bool):
        for page in (self.spectraPage, self.wavefunctionPage):
            page.inspector.setVisible(visible)

    @Slot(str)
    def setTheme(self, mode: str):
        self.theme.setMode(mode)
        if hasattr(self, 'themeActions'):
            self.themeActions[self.theme.mode].setChecked(True)

    # Datasets

    def recentDatasets(self):
        try:
            recent = json.loads(self.settings.value('recentDatasets', '[]'))
        except (TypeError, ValueError):
            recent = []
        return [dataset for dataset in recent if isinstance(dataset, dict)]

    def addRecentDataset(self, dataset):
        recent = [d for d in self.recentDatasets() if d.get('save') != dataset.get('save')]
        recent.insert(0, dataset)
        self.settings.setValue('recentDatasets', json.dumps(recent[:MAX_RECENT_DATASETS]))
        self.updateRecentMenu()

    def updateRecentMenu(self):
        self.recentMenu.clear()
        recent = self.recentDatasets()
        for dataset in recent:
            action = QAction(datasetName(dataset), self)
            action.setToolTip(dataset.get('save') or '')
            action.setEnabled(datasetExists(dataset))
            action.triggered.connect(lambda checked=False, dataset=dataset: self.openDataset(dataset))
            self.recentMenu.addAction(action)
        self.recentMenu.setEnabled(bool(recent))

    def openInitialDataset(self):
        for dataset in self.recentDatasets():
            if datasetExists(dataset):
                self.openDataset(dataset)
                return
        if DEFAULT_DATASET_FOLDER.is_dir():
            dataset = findDataset(DEFAULT_DATASET_FOLDER)
            if datasetExists(dataset):
                self.openDataset(dataset)

    @Slot()
    def chooseDataset(self):
        start = str(Path(self.dataset['save']).parent.parent) if self.dataset and self.dataset.get('save') else str(Path.cwd())
        folder = QFileDialog.getExistingDirectory(self, 'Open dataset', start, QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        dataset = findDataset(folder)
        if not datasetExists(dataset):
            QMessageBox.warning(self, 'Open dataset', f'No SAVE directory (with ns.db1) found in\n{folder}')
            return
        if dataset['diago'] is None:
            QMessageBox.warning(self, 'Open dataset', 'No BSE directory (with ndb.BS_diago_Q* files) found next to\n'
                                f'{dataset["save"]}\n\nYou can choose it on the System page.')
        self.openDataset(dataset)

    def openDataset(self, dataset):
        # Keep the parameters of the dataset being left
        self.storeDatasetState()

        # What was saved for this dataset (Q-path, parameters), even when it is
        # found again through Open dataset
        saved = next((d for d in self.recentDatasets() if d.get('save') == dataset.get('save')), {})
        self.dataset = {**{key: saved[key] for key in ('qPath', 'state') if key in saved}, **dict(dataset)}
        dataset = self.dataset
        self.options.setGW(bool(dataset.get('gw')))
        self.options.setSaveDir(dataset['save'])
        if dataset.get('diago'):
            self.options.setDiagoDir(dataset['diago'])
        if dataset.get('qp'):
            self.options.setQPDir(dataset['qp'])

        # The Q-path last set on this dataset, if any
        qPath = dataset.get('qPath')
        if qPath:
            if self.systemPage.restoreQPath(qPath):
                self.statusBar().showMessage(f'Q-path {self.options.getPathString()} restored', 4000)
            else:
                # Not valid any more (e.g. different lattice): forget it
                self.dataset.pop('qPath', None)
                self.statusBar().showMessage('The saved Q-path could not be restored: set it again', 8000)

        self.state.restore(DATASET, dataset.get('state') or self.datasetDefaults)
        self.addRecentDataset(self.dataset)
        self.updateDatasetLabel()

    def storeDatasetState(self):
        """Save the parameters of the current dataset with it, in the recent datasets."""
        if self.dataset is None:
            return
        self.dataset['state'] = self.state.values(DATASET)
        recent = [dict(self.dataset) if d.get('save') == self.dataset.get('save') else d for d in self.recentDatasets()]
        self.settings.setValue('recentDatasets', json.dumps(recent))

    def loadJson(self, key, default):
        try:
            return json.loads(self.settings.value(key, json.dumps(default)))
        except (TypeError, ValueError):
            return default

    @Slot(dict)
    def saveQPath(self, state: dict):
        """Remember the Q-path of the current dataset, restored when it is opened again."""
        if self.dataset is None or self.dataset.get('save') != self.options.saveDir:
            return
        self.dataset['qPath'] = state
        self.addRecentDataset(self.dataset)

    @Slot()
    def updateDatasetLabel(self, *args):
        name = datasetName({'save': self.options.saveDir, 'diago': self.options.diagoDir,
                            'qp': self.options.qpDir if self.options.gw else None})
        parts = [name] if name else ['No dataset']
        if self.options.variant:
            parts.append(f'ibrav {self.options.ibrav} ({self.options.variant})' if self.options.ibrav != -1 else self.options.variant)
        if self.options.nQpoints:
            parts.append(f'{self.options.nQpoints} Q-points')
        self.datasetLabel.setText('  ·  '.join(parts))
        self.setWindowTitle(f'{name} — Visual Excitons' if name else 'Visual Excitons')

    # Calculations

    @Slot(bool)
    def onBusyChanged(self, busy: bool):
        self.taskWidget.setVisible(busy)
        # The window stays usable: a busy cursor, not a wait cursor
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()
            if not self.statusBar().currentMessage():
                self.statusBar().showMessage('Ready', 2000)

    @Slot(str)
    def onTaskStarted(self, message: str):
        self.taskMessage = message
        self.taskStage = ''
        self.taskProgressBar.setRange(0, 0)  # unknown length until a stage reports it
        self.updateTaskLabel()

    @Slot(int, int, str)
    def onProgress(self, done: int, total: int, stage: str):
        if total > 0:
            self.taskProgressBar.setRange(0, total)
            self.taskProgressBar.setValue(min(done, total))
        else:
            self.taskProgressBar.setRange(0, 0)
        self.taskStage = stage
        self.updateTaskLabel()

    def updateTaskLabel(self):
        text = getattr(self, 'taskMessage', '')
        if getattr(self, 'taskStage', ''):
            text = f'{text.rstrip("…")} — {self.taskStage}'
        queued = self.calculations.tasks.queuedCount()
        if queued:
            text += f'  (+{queued} queued)'
        self.taskLabel.setText(text)

    @Slot(str)
    def onTaskCancelled(self, message: str):
        self.statusBar().showMessage(f'Cancelled: {message.rstrip("…").lower()}', 4000)

    @Slot(str, str)
    def onError(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    @Slot(int, int, float)
    def onExcitonSelected(self, qIndex: int, excIndex: int, energy: float):
        self.statusBar().showMessage(f'Selected exciton {excIndex} at Q-point {qIndex + 1} (E = {energy:.4f} eV)', 8000)

    # Misc

    def showAbout(self):
        QMessageBox.about(self, 'About Visual Excitons',
                          '<b>Visual Excitons</b><br>Visualization of excitonic properties computed with '
                          '<a href="https://www.yambo-code.eu/">Yambo</a>, read through YamboPy.')

    def closeEvent(self, event):
        # Stop the calculations; the running one ends at its next progress check
        self.calculations.cancel()
        self.calculations.tasks.waitForDone(10000)
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('page', self.stack.currentIndex())
        self.settings.setValue('theme', self.theme.mode)
        self.settings.setValue('showInspector', self.inspectorAction.isChecked())
        self.settings.setValue('state', json.dumps(self.state.values(GLOBAL)))
        self.storeDatasetState()
        super().closeEvent(event)
