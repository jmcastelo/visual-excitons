"""
Export of the 2D plots as publication figures, drawn with Matplotlib (see
core/figures.py): the data and styles of the plots on screen, translated to
plain values; a dialog with the options and a live preview; figure files and
standalone scripts.
"""

import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QSettings, QTimer, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QFormLayout, QCheckBox, QComboBox, QDoubleSpinBox,
                               QSpinBox, QLabel, QPushButton, QFileDialog, QMessageBox, QSizePolicy,
                               QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView)

from visual_excitons.core import figures
from visual_excitons.core.figure_script import writeFigureScript
from .inspector import NoteLabel

FIGURE_FILTERS = ('PDF (*.pdf);;SVG (*.svg);;EPS (*.eps);;PNG image (*.png);;TIFF image (*.tif *.tiff)')
PANEL_NAMES = {'dispersion': 'Dispersion', 'absorption': 'Absorption', 'bands': 'Band structure'}

# Journal column widths (cm)
WIDTH_PRESETS = [('One column (8.6 cm)', 8.6), ('One and a half columns (12.9 cm)', 12.9),
                 ('Two columns (17.8 cm)', 17.8), ('Custom', None)]

# Qt pen styles and pyqtgraph symbols, as Matplotlib line styles and markers
_DASHES = {Qt.PenStyle.SolidLine: '-', Qt.PenStyle.DashLine: '--', Qt.PenStyle.DotLine: ':',
           Qt.PenStyle.DashDotLine: '-.', Qt.PenStyle.DashDotDotLine: (0, (3, 1, 1, 1, 1, 1))}
_MARKERS = {'o': 'o', 's': 's', 't': 'v', 't1': '^', 't2': '>', 't3': '<', 'd': 'D', '+': 'P', 'p': 'p',
            'h': 'h', 'star': '*', 'x': 'X', 'arrow_up': '^', 'arrow_right': '>', 'arrow_down': 'v',
            'arrow_left': '<', 'crosshair': '+'}


def penStyle(pen, symbol='o', size=6):
    """A curve style for core.figures from a Qt pen and a pyqtgraph symbol and size (pixels)."""
    dash = _DASHES.get(pen.style(), '-')
    return {'color': pen.color().name(), 'width': max(0.6, 0.8 * pen.widthF()) if pen.widthF() else 1.0,
            'dash': list(dash) if isinstance(dash, tuple) else dash,
            'marker': _MARKERS.get(symbol, 'o'), 'markerSize': max(1.5, 0.55 * size)}


def figureStyles(dispersionStyle, absorptionStyle, bandStructureStyle):
    def curves(style, points=True):
        pens = style.curveStyle.curvePens
        symbols = style.pointStyle.pointSymbols if points else []
        sizes = style.pointStyle.pointSizes if points else []
        return [penStyle(pen, symbols[i] if i < len(symbols) else 'o', sizes[i] if i < len(sizes) else 6)
                for i, pen in enumerate(pens)]
    return {'dispersion': {'curves': curves(dispersionStyle)},
            'absorption': {'curves': curves(absorptionStyle)},
            'bands': {'curves': curves(bandStructureStyle, points=False),
                      'fill': bandStructureStyle.brush.color().name()}}


def figureData(calculations):
    """The results on screen, as data for core.figures."""
    calc = calculations
    data = {}
    axes = getattr(calc, 'dispersionAxes', {}) or {}
    ticks, labels = list(axes.get('specialPoints', [])), list(axes.get('labels', []))
    if len(calc.dispPoints):
        data['dispersion'] = {'points': np.asarray(calc.dispPoints, dtype=float),
                              'xInter': np.asarray(calc.dispXInter, dtype=float),
                              'yInter': np.asarray(calc.dispYInter, dtype=float), 'ticks': ticks, 'labels': labels}
    if calc.excAbsData:
        data['absorption'] = [{
            'q': int(d['q']), 'energy': np.asarray(d['energy'], dtype=float),
            'absorption': np.asarray(d['absorption'], dtype=float),
            'brightEnergy': np.asarray(d['brightExcEnergy'], dtype=float),
            'brightAbsorption': np.asarray(d['brightExcAbsorption'], dtype=float),
            'brightIndices': np.asarray(d['brightExcIndices'], dtype=float),
            'brightIntensities': np.asarray(d['brightExcIntensities'], dtype=float),
            'darkEnergy': np.asarray(d['darkExcEnergy'], dtype=float)} for d in calc.excAbsData]
    if len(calc.k):
        data['bands'] = {'k': np.asarray(calc.k, dtype=float), 'bands': np.asarray(calc.bands, dtype=float),
                         'weights': np.asarray(calc.weights, dtype=float) * calc.weightFactor,
                         'ticks': ticks, 'labels': labels}
    positions = calc.selectedExcitonPositions()
    data['selected'] = {'dispersion': [list(map(float, p)) for p in positions['dispersion']],
                        'absorption': [list(map(float, p)) for p in positions['absorption']]}
    return data


def figureImage(figure):
    """A Matplotlib figure rendered as a QImage (for the preview)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    canvas = FigureCanvasAgg(figure)
    canvas.draw()
    buffer = np.asarray(canvas.buffer_rgba())
    height, width = buffer.shape[:2]
    return QImage(buffer.tobytes(), width, height, 4 * width, QImage.Format.Format_RGBA8888).copy()


class FigureExportDialog(QDialog):
    """Options of the figure, with a live preview; saves figures and scripts."""

    def __init__(self, data, styles, defaultName='figure', programVersion='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export 2D figure')
        self.data, self.styles = data, styles
        self.defaultName, self.programVersion = defaultName, programVersion
        self.settings = QSettings('VisualExcitons', 'VisualExcitons')
        available = figures.availablePanels(data)

        # Panels: checkable, in the order of the list (drag to reorder)
        self.panelList = QListWidget()
        self.panelList.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.panelList.setMaximumHeight(90)
        self.panelList.setToolTip('The panels of the figure, in this order (drag to reorder)')
        saved = self.loadOptions()
        order = [p for p in saved['panels'] if p in PANEL_NAMES] + [p for p in PANEL_NAMES if p not in saved['panels']]
        for panel in order:
            item = QListWidgetItem(PANEL_NAMES[panel])
            item.setData(Qt.ItemDataRole.UserRole, panel)
            flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled
            if panel in available:
                flags |= Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            else:
                item.setToolTip('No data: compute it first')
            item.setFlags(flags)
            item.setCheckState(Qt.CheckState.Checked if panel in saved['panels'] and panel in available
                               else Qt.CheckState.Unchecked)
            self.panelList.addItem(item)
        if not any(self.panelList.item(i).checkState() == Qt.CheckState.Checked for i in range(self.panelList.count())):
            for i in range(self.panelList.count()):
                if self.panelList.item(i).data(Qt.ItemDataRole.UserRole) in available:
                    self.panelList.item(i).setCheckState(Qt.CheckState.Checked)
                    break

        self.arrangementComboBox = QComboBox()
        self.arrangementComboBox.addItems(['In a row', 'In a column'])
        self.arrangementComboBox.setCurrentIndex(0 if saved['arrangement'] == 'row' else 1)
        self.shareEnergyCheckBox = QCheckBox('Dispersion and absorption on one energy axis')
        self.shareEnergyCheckBox.setToolTip('In a row: the absorption rotated, its energy along the energy axis of the dispersion')
        self.shareEnergyCheckBox.setChecked(saved['shareEnergy'])

        self.widthComboBox = QComboBox()
        self.widthComboBox.addItems([label for label, width in WIDTH_PRESETS])
        self.widthSpinBox = QDoubleSpinBox(minimum=2.0, maximum=60.0, singleStep=0.1, decimals=1, suffix=' cm')
        self.heightSpinBox = QDoubleSpinBox(minimum=2.0, maximum=60.0, singleStep=0.1, decimals=1, suffix=' cm')
        self.widthSpinBox.setValue(saved['width'])
        self.heightSpinBox.setValue(saved['height'])
        preset = next((i for i, (label, width) in enumerate(WIDTH_PRESETS) if width == saved['width']),
                      len(WIDTH_PRESETS) - 1)
        self.widthComboBox.setCurrentIndex(preset)
        self.widthSpinBox.setEnabled(WIDTH_PRESETS[preset][1] is None)
        self.widthComboBox.currentIndexChanged.connect(self.onWidthPreset)

        self.fontComboBox = QComboBox()
        self.fontComboBox.addItems(list(figures.FONTS))
        self.fontComboBox.setCurrentText(saved['font'])
        self.fontSizeSpinBox = QDoubleSpinBox(minimum=4.0, maximum=24.0, singleStep=0.5, decimals=1, suffix=' pt')
        self.fontSizeSpinBox.setValue(saved['fontSize'])
        self.dpiSpinBox = QSpinBox(minimum=72, maximum=2400, singleStep=50, suffix=' dpi')
        self.dpiSpinBox.setValue(saved['dpi'])
        self.dpiSpinBox.setToolTip('Resolution of PNG and TIFF files (vector formats do not need it)')

        self.checkBoxes = {}
        for key, text, tip in (('panelLabels', 'Panel letters (a), (b)...', ''),
                               ('legend', 'Legend of the spectra', ''),
                               ('excitonBars', 'Bright and dark excitons below the absorption', ''),
                               ('labelExcitons', 'Index of the bright excitons', ''),
                               ('highlight', 'Ring around the selected exciton', ''),
                               ('gamma', 'Typeset path labels (Γ, Σ₁, K′)', ''),
                               ('titles', 'Titles of the panels', '')):
            box = QCheckBox(text)
            box.setChecked(bool(saved[key]))
            box.setToolTip(tip)
            self.checkBoxes[key] = box

        layoutForm = QFormLayout()
        layoutForm.addRow('Panels:', self.panelList)
        layoutForm.addRow('Arrangement:', self.arrangementComboBox)
        layoutForm.addRow('', self.shareEnergyCheckBox)
        layoutForm.addRow('Width:', self.widthComboBox)
        layoutForm.addRow('', self.widthSpinBox)
        layoutForm.addRow('Height:', self.heightSpinBox)
        layoutForm.addRow('Font:', self.fontComboBox)
        layoutForm.addRow('Font size:', self.fontSizeSpinBox)
        layoutForm.addRow('Resolution:', self.dpiSpinBox)
        for box in self.checkBoxes.values():
            layoutForm.addRow(box)

        self.saveFigureButton = QPushButton('Save figure…')
        self.saveFigureButton.setDefault(True)
        self.saveFigureButton.clicked.connect(self.saveFigure)
        self.saveScriptButton = QPushButton('Save as script…')
        self.saveScriptButton.setToolTip('A Python script and its data file that recreate the figure with Matplotlib,\n'
                                         'to adapt it freely; it does not need Visual Excitons')
        self.saveScriptButton.clicked.connect(self.saveScript)
        buttons = QDialogButtonBox()
        buttons.addButton(self.saveFigureButton, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.saveScriptButton, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)

        controls = QVBoxLayout()
        controls.addLayout(layoutForm)
        controls.addStretch(1)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 320)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet('QLabel { background: white; border: 1px solid #bbb; }')
        self.previewNote = NoteLabel('Preview at the size of the figure; the files are vector graphics '
                                     '(PDF, SVG, EPS) or at the chosen resolution.')
        previewLayout = QVBoxLayout()
        previewLayout.addWidget(self.preview, 1)
        previewLayout.addWidget(self.previewNote)

        top = QHBoxLayout()
        top.addLayout(controls)
        top.addLayout(previewLayout, 1)
        main = QVBoxLayout(self)
        main.addLayout(top, 1)
        main.addWidget(buttons)

        # Preview, updated shortly after the options change
        self.previewTimer = QTimer(self)
        self.previewTimer.setSingleShot(True)
        self.previewTimer.setInterval(250)
        self.previewTimer.timeout.connect(self.updatePreview)
        for signal in (self.arrangementComboBox.currentIndexChanged, self.shareEnergyCheckBox.toggled,
                       self.widthSpinBox.valueChanged, self.heightSpinBox.valueChanged,
                       self.fontComboBox.currentIndexChanged, self.fontSizeSpinBox.valueChanged,
                       self.panelList.itemChanged, self.panelList.model().rowsMoved):
            signal.connect(self.requestPreview)
        for box in self.checkBoxes.values():
            box.toggled.connect(self.requestPreview)
        self.resize(1000, 640)
        self.updatePreview()

    # Options

    def loadOptions(self):
        try:
            saved = json.loads(self.settings.value('figureExport/options', '{}'))
        except (TypeError, ValueError):
            saved = {}
        return {**figures.DEFAULT_OPTIONS, **{k: v for k, v in saved.items() if k in figures.DEFAULT_OPTIONS}}

    def options(self):
        panels = [self.panelList.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.panelList.count())
                  if self.panelList.item(i).checkState() == Qt.CheckState.Checked]
        options = {'panels': panels, 'arrangement': 'row' if self.arrangementComboBox.currentIndex() == 0 else 'column',
                   'shareEnergy': self.shareEnergyCheckBox.isChecked(), 'width': self.widthSpinBox.value(),
                   'height': self.heightSpinBox.value(), 'font': self.fontComboBox.currentText(),
                   'fontSize': self.fontSizeSpinBox.value(), 'dpi': self.dpiSpinBox.value()}
        options.update({key: box.isChecked() for key, box in self.checkBoxes.items()})
        return options

    def storeOptions(self):
        self.settings.setValue('figureExport/options', json.dumps(self.options()))

    @Slot(int)
    def onWidthPreset(self, index):
        width = WIDTH_PRESETS[index][1]
        self.widthSpinBox.setEnabled(width is None)
        if width is not None:
            self.widthSpinBox.setValue(width)

    # Preview

    @Slot()
    def requestPreview(self, *args):
        self.previewTimer.start()

    def buildFigure(self):
        return figures.buildFigure(self.data, self.styles, self.options())

    @Slot()
    def updatePreview(self):
        try:
            figure = self.buildFigure()
        except ValueError as error:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(str(error))
            self.saveFigureButton.setEnabled(False)
            self.saveScriptButton.setEnabled(False)
            return
        self.saveFigureButton.setEnabled(True)
        self.saveScriptButton.setEnabled(True)
        image = figureImage(figure)
        pixmap = QPixmap.fromImage(image)
        target = self.preview.size()
        if pixmap.width() > target.width() or pixmap.height() > target.height():
            pixmap = pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.requestPreview()

    # Saving

    def folder(self):
        return self.settings.value('exportDir', str(Path.cwd()))

    def chooseFile(self, title, suffix, filters):
        filename, chosen = QFileDialog.getSaveFileName(self, title, str(Path(self.folder()) / f'{self.defaultName}{suffix}'),
                                                       filters)
        if not filename:
            return None
        if not Path(filename).suffix:
            extension = chosen.split('*')[-1].split(')')[0].split()[0] if '*' in chosen else suffix
            filename += extension
        self.settings.setValue('exportDir', str(Path(filename).parent))
        return filename

    @Slot()
    def saveFigure(self):
        filename = self.chooseFile('Save figure', '.pdf', FIGURE_FILTERS)
        if not filename:
            return
        try:
            figures.saveFigure(self.buildFigure(), filename, self.options())
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, 'Save figure failed', str(error))
            return
        self.storeOptions()
        self.savedFile = filename
        self.previewNote.setText(f'Saved {filename}')

    @Slot()
    def saveScript(self):
        filename = self.chooseFile('Save figure as a script', '.py', 'Python script (*.py)')
        if not filename:
            return
        try:
            script, dataFile = writeFigureScript(filename, self.data, self.styles, self.options(),
                                                 programVersion=self.programVersion)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, 'Save script failed', str(error))
            return
        self.storeOptions()
        self.savedFile = str(script)
        self.previewNote.setText(f'Saved {script} and its data, {dataFile.name}: run it with python to make the figure')

    def reject(self):
        self.storeOptions()
        super().reject()
