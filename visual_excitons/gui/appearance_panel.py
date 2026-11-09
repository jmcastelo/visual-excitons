"""
The Appearance panel: the styles of the 2D plots (core/style.py), edited in
place.

Three toggle buttons choose the plot (also chosen by the brush button of each
plot's panel, its right-click menu, or by clicking one of its curves); its
styles are in collapsible sections, only those it has. `Apply to` chooses
between all the curves and one of them. Color and font buttons open a dialog
that previews on the plot as you pick; Cancel restores the styles as they were
(`openReverting`).
"""

from contextlib import ExitStack

from PySide6.QtCore import Qt, Signal, Slot, QSignalBlocker, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QIcon, QPixmap, QBrush
from PySide6.QtWidgets import (QPushButton, QHBoxLayout, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
                               QColorDialog, QFontDialog, QDialog, QWidget, QLabel, QTabBar, QSizePolicy,
                               QAbstractSpinBox)

from visual_excitons.core.style import PEN_STYLES
from .inspector import Inspector, formLayout

GRAPHS = {'dispersion': 'Dispersion', 'absorption': 'Absorption', 'bands': 'Band structure'}

PATTERNS = ['Solid', 'Dashed', 'Dotted', 'Dash-dot', 'Dash-dot-dot']   # as PEN_STYLES
SYMBOLS = {'o': 'Circle', 's': 'Square', 't': 'Triangle down', 't1': 'Triangle up', 't2': 'Triangle right',
           't3': 'Triangle left', 'd': 'Diamond', '+': 'Plus', 'p': 'Pentagon', 'h': 'Hexagon', 'star': 'Star',
           'x': 'Cross', 'arrow_up': 'Arrow up', 'arrow_right': 'Arrow right', 'arrow_down': 'Arrow down',
           'arrow_left': 'Arrow left', 'crosshair': 'Crosshair'}

# Axes elements: (attribute of the color, attribute of the font or None, label)
AXES_ELEMENTS = [('titleColor', 'titleFont', 'Title'), ('labelsColor', 'labelsFont', 'Axis labels'),
                 ('ticksColor', 'ticksFont', 'Tick labels'), ('axesColor', None, 'Axes'),
                 ('backgroundColor', None, 'Background')]


def blocked(*widgets):
    """Context in which `widgets` emit no signals: showing a value must not apply it again."""
    stack = ExitStack()
    for widget in widgets:
        stack.enter_context(QSignalBlocker(widget))
    return stack


def openReverting(dialog, styles, refresh=None):
    """
    Show a color or font dialog that previews its value on the plots; Cancel
    (or closing it) restores `styles` as they were when it opened, the style of
    each curve included. Modal: one dialog at a time, so that one restore
    cannot undo what was done in another dialog.
    """
    snapshots = [(style, style.state()) for style in styles]

    def finished(result):
        dialog.finished.disconnect(finished)
        if result == QDialog.DialogCode.Rejected:
            for style, state in snapshots:
                style.setState(state, curves=True)
            if refresh is not None:
                refresh()

    dialog.finished.connect(finished)
    dialog.setModal(True)
    dialog.show()


def appearanceIcon(size=16) -> QIcon:
    """A painter's palette, for the Appearance buttons of the plot panels."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size * 2
    painter.setPen(QPen(QColor(120, 120, 120), s * 0.06))
    painter.setBrush(QColor(235, 215, 170))
    painter.drawEllipse(QRectF(s * 0.06, s * 0.12, s * 0.88, s * 0.76))
    painter.setPen(Qt.PenStyle.NoPen)
    for (x, y), color in zip(((0.28, 0.32), (0.5, 0.24), (0.72, 0.34), (0.3, 0.6)),
                             ('#d62728', '#2ca02c', '#1f77b4', '#ff7f0e')):
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(s * (x - 0.09), s * (y - 0.09), s * 0.18, s * 0.18))
    painter.end()
    return QIcon(pixmap)


class ColorButton(QPushButton):
    """A swatch of a color (crossed out for none)."""

    def __init__(self, toolTip='', parent=None):
        super().__init__(parent)
        self.baseToolTip = toolTip
        self.color = None
        self.setFixedWidth(52)

    def setColor(self, color):
        self.color = None if color is None else QColor(color)
        self.setToolTip(f'{self.baseToolTip}: {self.color.name() if self.color is not None else "none"}'
                        if self.baseToolTip else '')
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        rect = self.rect().adjusted(8, 6, -8, -6)
        painter.setPen(QPen(self.palette().color(self.foregroundRole()), 1))
        if self.color is None:
            painter.drawRect(rect)
            painter.drawLine(rect.bottomLeft(), rect.topRight())
        else:
            painter.setBrush(QBrush(self.color))
            painter.drawRect(rect)
        painter.end()


class FontButton(QPushButton):
    """The family and size of a font, which it shows in."""

    def setFontValue(self, font):
        self.setText(f'{font.family()}, {font.pointSize()} pt' if font.pointSize() > 0 else font.family())


class AppearancePanel(Inspector):
    graphChanged = Signal(str)

    def __init__(self, styles: dict, curveNames=None, parent=None):
        """
        `styles`: {'dispersion', 'absorption', 'bands'} styles; `curveNames(key,
        count)`: the names of the curves of a plot (default: Curve 1, 2...).
        """
        super().__init__(parent)
        self.styles = styles
        self.curveNames = curveNames or (lambda key, count: [f'Curve {i + 1}' for i in range(count)])
        self.graph = 'dispersion'
        self.colorDialog = QColorDialog(self)
        self.colorDialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        self.fontDialog = QFontDialog(self)
        self.colorSlot = self.fontSlot = None   # what each dialog applies, while open

        self.refreshTimer = QTimer(self)
        self.refreshTimer.setSingleShot(True)
        self.refreshTimer.setInterval(0)
        self.refreshTimer.timeout.connect(self.refresh)

        self.buildGraphSelector()
        self.buildCurvesSection()
        self.buildSymbolsSection()
        self.buildAxesSection()
        self.buildLegendSection()
        self.buildFillSection()
        self.alignLabels()

        for key, style in styles.items():
            style.styleChanged.connect(self.scheduleRefresh)
            style.currentCurveIndexChanged.connect(lambda key=key: self.onCurveClicked(key))
            axes = style.axesStyle
            for name in axes.COLORS:
                getattr(axes, name).changed.connect(self.scheduleRefresh)
            for name in axes.FONTS:
                getattr(axes, name).changed.connect(self.scheduleRefresh)
            axes.axesWidthChanged.connect(self.scheduleRefresh)
        legend = styles['absorption'].legendStyle
        for signal in (legend.textColorChanged, legend.textSizeChanged, legend.backgroundColorChanged,
                       legend.borderPenChanged, legend.offsetChanged):
            signal.connect(self.scheduleRefresh)
        styles['bands'].weightFactorChanged.connect(self.scheduleRefresh)

        for spinBox in self.findChildren(QAbstractSpinBox):
            spinBox.setSizePolicy(QSizePolicy.Policy.Maximum, spinBox.sizePolicy().verticalPolicy())
        self.setGraph('dispersion')

    # Construction

    def buildGraphSelector(self):
        # Tabs: the plot being edited is plain to see, on any theme
        self.graphTabs = QTabBar()
        self.graphTabs.setExpanding(True)
        self.graphTabs.setDocumentMode(True)
        self.graphKeys = list(GRAPHS)
        for index, (key, title) in enumerate(GRAPHS.items()):
            self.graphTabs.addTab(title)
            self.graphTabs.setTabToolTip(index, f'The style of the {title.lower()} plot')
        self.graphTabs.currentChanged.connect(lambda index: self.setGraph(self.graphKeys[index]))
        self.bodyLayout.insertWidget(0, self.graphTabs)

    def buildCurvesSection(self):
        self.curveComboBox = QComboBox()
        self.curveComboBox.setToolTip('The curves the changes apply to; clicking a curve in a plot selects it here')
        self.curveComboBox.activated.connect(self.onCurveChosen)

        self.patternComboBox = QComboBox()
        self.patternComboBox.addItems(PATTERNS)
        self.patternComboBox.currentIndexChanged.connect(lambda index: self.curveStyle().setCurveStyle(index))

        self.lineColorButton = ColorButton('Line color')
        self.lineColorButton.clicked.connect(lambda: self.editColor(
            'Line color', self.currentPen().color(), self.curveStyle().setCurveColor))

        self.lineWidthSpinBox = QSpinBox()
        self.lineWidthSpinBox.setRange(1, 10)
        self.lineWidthSpinBox.setSuffix(' px')
        self.lineWidthSpinBox.valueChanged.connect(lambda width: self.curveStyle().setCurveWidth(width))

        self.startHueButton = ColorButton('First curve')
        self.startHueButton.clicked.connect(lambda: self.editColor(
            'First color of the gradient', QColor.fromHsv(self.curveStyle().startHue, 255, 255),
            lambda color: self.setGradientHue('startHue', color)))
        self.endHueButton = ColorButton('Last curve')
        self.endHueButton.clicked.connect(lambda: self.editColor(
            'Last color of the gradient', QColor.fromHsv(self.curveStyle().endHue, 255, 255),
            lambda color: self.setGradientHue('endHue', color)))
        gradient = QHBoxLayout()
        gradient.addWidget(self.startHueButton)
        gradient.addWidget(QLabel('to'))
        gradient.addWidget(self.endHueButton)
        gradient.addStretch(1)
        self.gradientRow = QWidget()
        self.gradientRow.setLayout(gradient)
        gradient.setContentsMargins(0, 0, 0, 0)
        self.gradientRow.setToolTip('Color the curves along a range of hues, from the first to the last')

        form = formLayout()
        form.addRow('Apply to:', self.curveComboBox)
        form.addRow('Pattern:', self.patternComboBox)
        form.addRow('Color:', self.lineColorButton)
        form.addRow('Width:', self.lineWidthSpinBox)
        form.addRow('Gradient:', self.gradientRow)
        self.curvesForm = form
        self.curvesSection = self.addSection('Curves', form)

    def buildSymbolsSection(self):
        self.symbolComboBox = QComboBox()
        self.symbolComboBox.addItems(list(SYMBOLS.values()))
        self.symbolComboBox.currentIndexChanged.connect(lambda index: self.pointStyle().setPointSymbol(index))

        self.symbolSizeSpinBox = QSpinBox()
        self.symbolSizeSpinBox.setRange(0, 500)
        self.symbolSizeSpinBox.setSuffix(' px')
        self.symbolSizeSpinBox.valueChanged.connect(lambda size: self.pointStyle().setPointSize(size))

        self.varySymbolsButton = QPushButton('Different shape per curve')
        self.varySymbolsButton.setToolTip('Give each curve a shape of its own')
        self.varySymbolsButton.clicked.connect(lambda: self.pointStyle().setSymbolGradient())

        form = formLayout()
        form.addRow('Shape:', self.symbolComboBox)
        form.addRow('Size:', self.symbolSizeSpinBox)
        form.addRow(self.varySymbolsButton)
        self.symbolsForm = form
        self.symbolsSection = self.addSection('Symbols', form)

    def buildAxesSection(self):
        self.sameAxesCheckBox = QCheckBox('Same axes style for all plots')
        self.sameAxesCheckBox.setToolTip('Changes to the axes apply to the three plots')
        self.remember('sameAxes', self.sameAxesCheckBox)

        form = formLayout()
        form.addRow(self.sameAxesCheckBox)
        self.axesColorButtons, self.axesFontButtons = {}, {}
        for colorName, fontName, label in AXES_ELEMENTS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            button = ColorButton(f'{label} color')
            button.clicked.connect(lambda checked=False, name=colorName, label=label: self.editAxesColor(name, label))
            row.addWidget(button)
            self.axesColorButtons[colorName] = button
            if fontName is not None:
                fontButton = FontButton()
                fontButton.setToolTip(f'{label} font')
                fontButton.clicked.connect(lambda checked=False, name=fontName, label=label: self.editAxesFont(name, label))
                row.addWidget(fontButton)
                self.axesFontButtons[fontName] = fontButton
            if colorName == 'axesColor':
                self.axesWidthSpinBox = QSpinBox()
                self.axesWidthSpinBox.setRange(1, 10)
                self.axesWidthSpinBox.setSuffix(' px')
                self.axesWidthSpinBox.setToolTip('Width of the axes')
                self.axesWidthSpinBox.valueChanged.connect(self.setAxesWidth)
                row.addWidget(self.axesWidthSpinBox)
            row.addStretch(1)
            widget = QWidget()
            widget.setLayout(row)
            form.addRow(f'{label}:', widget)
        self.axesSection = self.addSection('Axes', form, expanded=False)

    def buildLegendSection(self):
        legend = self.styles['absorption'].legendStyle

        self.legendTextColorButton = ColorButton('Text color')
        self.legendTextColorButton.clicked.connect(lambda: self.editColor(
            'Legend text color', legend.textColor, legend.setTextColor))
        self.legendTextSizeSpinBox = QSpinBox()
        self.legendTextSizeSpinBox.setRange(1, 100)
        self.legendTextSizeSpinBox.setSuffix(' pt')
        self.legendTextSizeSpinBox.valueChanged.connect(legend.setTextSize)
        text = QHBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.addWidget(self.legendTextColorButton)
        text.addWidget(self.legendTextSizeSpinBox)
        text.addStretch(1)
        textRow = QWidget()
        textRow.setLayout(text)

        self.legendBackgroundButton = ColorButton('Background')
        self.legendBackgroundButton.clicked.connect(lambda: self.editColor(
            'Legend background', legend.backgroundColor or QColor('white'), legend.setBackgroundColor))
        self.legendNoBackgroundButton = QPushButton('None')
        self.legendNoBackgroundButton.setToolTip('No background: the plot shows through')
        self.legendNoBackgroundButton.clicked.connect(lambda: legend.setBackgroundColor(None))
        background = QHBoxLayout()
        background.setContentsMargins(0, 0, 0, 0)
        background.addWidget(self.legendBackgroundButton)
        background.addWidget(self.legendNoBackgroundButton)
        background.addStretch(1)
        backgroundRow = QWidget()
        backgroundRow.setLayout(background)

        self.legendBorderColorButton = ColorButton('Border color')
        self.legendBorderColorButton.clicked.connect(lambda: self.editColor(
            'Legend border color', legend.borderPen.color(), legend.setBorderColor))
        self.legendBorderPatternComboBox = QComboBox()
        self.legendBorderPatternComboBox.addItems(PATTERNS)
        self.legendBorderPatternComboBox.currentIndexChanged.connect(legend.setBorderStyle)
        self.legendBorderWidthSpinBox = QSpinBox()
        self.legendBorderWidthSpinBox.setRange(0, 10)
        self.legendBorderWidthSpinBox.setSuffix(' px')
        self.legendBorderWidthSpinBox.setToolTip('Width of the border (0: thinnest)')
        self.legendBorderWidthSpinBox.valueChanged.connect(legend.setBorderWidth)
        border = QHBoxLayout()
        border.setContentsMargins(0, 0, 0, 0)
        border.addWidget(self.legendBorderColorButton)
        border.addWidget(self.legendBorderPatternComboBox)
        border.addWidget(self.legendBorderWidthSpinBox)
        borderRow = QWidget()
        borderRow.setLayout(border)

        self.legendOffsetXSpinBox, self.legendOffsetYSpinBox = QSpinBox(), QSpinBox()
        offset = QHBoxLayout()
        offset.setContentsMargins(0, 0, 0, 0)
        for spinBox, setter, axis in ((self.legendOffsetXSpinBox, legend.setOffsetX, 'x'),
                                      (self.legendOffsetYSpinBox, legend.setOffsetY, 'y')):
            spinBox.setRange(0, 1000)
            spinBox.setPrefix(f'{axis} ')
            spinBox.setSuffix(' px')
            spinBox.valueChanged.connect(setter)
            offset.addWidget(spinBox)
        offset.addStretch(1)
        offsetRow = QWidget()
        offsetRow.setLayout(offset)

        form = formLayout()
        form.addRow('Text:', textRow)
        form.addRow('Background:', backgroundRow)
        form.addRow('Border:', borderRow)
        form.addRow('Position:', offsetRow)
        self.legendSection = self.addSection('Legend', form, expanded=False)

    def buildFillSection(self):
        bands = self.styles['bands']
        self.fillColorButton = ColorButton('Fill color')
        self.fillColorButton.clicked.connect(lambda: self.editColor('Fill color', bands.brush.color(),
                                                                    bands.setBrushColor))
        self.weightFactorSpinBox = QDoubleSpinBox()
        self.weightFactorSpinBox.setRange(0.0, 1000.0)
        self.weightFactorSpinBox.setToolTip('Scale of the width of the fill around the bands (exciton weights)')
        self.weightFactorSpinBox.valueChanged.connect(bands.setWeightFactor)
        form = formLayout()
        form.addRow('Color:', self.fillColorButton)
        form.addRow('Weight factor:', self.weightFactorSpinBox)
        self.fillSection = self.addSection('Fill', form)

    # The plot being edited

    def style(self):
        return self.styles[self.graph]

    def curveStyle(self):
        return self.style().curveStyle

    def pointStyle(self):
        return self.style().pointStyle

    @Slot(str)
    def setGraph(self, key):
        self.graph = key
        with blocked(self.graphTabs):
            self.graphTabs.setCurrentIndex(self.graphKeys.index(key))
        style = self.style()
        self.symbolsSection.setVisible(hasattr(style, 'pointStyle'))
        self.legendSection.setVisible(key == 'absorption')
        self.fillSection.setVisible(key == 'bands')
        self.refresh()
        self.graphChanged.emit(key)

    def currentPen(self):
        style = self.style()
        index = style.currentCurveIndex()
        if not style.applyToAllCurves() and 0 <= index < len(style.curveStyle.curvePens):
            return style.curveStyle.curvePens[index]
        return style.curveStyle.commonPen

    @Slot(int)
    def onCurveChosen(self, index):
        style = self.style()
        style.setApplyToAllCurves(index == 0)
        if index > 0:
            with blocked(style):
                style.setCurrentCurveIndex(index - 1)
        self.refresh()

    def onCurveClicked(self, key):
        """A curve clicked in a plot: edit its style."""
        style = self.styles[key]
        if not 0 <= style.currentCurveIndex() < style.common.numCurves:
            return
        style.setApplyToAllCurves(False)
        if key != self.graph:
            self.setGraph(key)
        else:
            self.refresh()

    # Editing

    @Slot()
    def scheduleRefresh(self, *args):
        self.refreshTimer.start()

    def editColor(self, title, current, apply, styles=None):
        """A color dialog that previews with `apply`; Cancel restores the styles."""
        dialog = self.colorDialog
        if self.colorSlot is not None:
            dialog.currentColorChanged.disconnect(self.colorSlot)
        dialog.setWindowTitle(title)
        with blocked(dialog):
            dialog.setCurrentColor(QColor(current) if current is not None else QColor('white'))
        self.colorSlot = apply
        dialog.currentColorChanged.connect(apply)
        openReverting(dialog, styles or list(self.styles.values()), self.refresh)

    def editAxesColor(self, name, label):
        current = getattr(self.style().axesStyle, name).getColor()
        self.editColor(f'{label} color', current,
                       lambda color: [getattr(style.axesStyle, name).setColor(color) for style in self.axesTargets()])

    def editAxesFont(self, name, label):
        dialog = self.fontDialog
        if self.fontSlot is not None:
            dialog.currentFontChanged.disconnect(self.fontSlot)
        dialog.setWindowTitle(f'{label} font')
        with blocked(dialog):
            dialog.setCurrentFont(getattr(self.style().axesStyle, name).getFont())
        self.fontSlot = lambda font: [getattr(style.axesStyle, name).setFont(font) for style in self.axesTargets()]
        dialog.currentFontChanged.connect(self.fontSlot)
        openReverting(dialog, list(self.styles.values()), self.refresh)

    def axesTargets(self):
        return list(self.styles.values()) if self.sameAxesCheckBox.isChecked() else [self.style()]

    @Slot(int)
    def setAxesWidth(self, width):
        for style in self.axesTargets():
            style.axesStyle.setAxesWidth(width)

    def setGradientHue(self, attribute, color):
        curves = self.curveStyle()
        setattr(curves, attribute, color.hue() if color.hue() >= 0 else 0)
        if curves.common.numCurves > 1:
            curves.setGradientPalette()
        else:
            self.scheduleRefresh()

    # Showing the values

    @Slot()
    def refresh(self):
        style = self.style()
        self.refreshCurves(style)
        if hasattr(style, 'pointStyle'):
            self.refreshSymbols(style)
        self.refreshAxes(style)
        if self.graph == 'absorption':
            self.refreshLegend(style.legendStyle)
        if self.graph == 'bands':
            with blocked(self.weightFactorSpinBox):
                self.weightFactorSpinBox.setValue(style.weightFactor)
            self.fillColorButton.setColor(style.brush.color())

    def refreshCurves(self, style):
        count = style.common.numCurves
        names = self.curveNames(self.graph, count)
        index = style.currentCurveIndex()
        single = not style.applyToAllCurves() and 0 <= index < count
        with blocked(self.curveComboBox):
            self.curveComboBox.clear()
            self.curveComboBox.addItem('All curves')
            self.curveComboBox.addItems(names)
            self.curveComboBox.setCurrentIndex(index + 1 if single else 0)
        if not single and not style.applyToAllCurves():
            style.setApplyToAllCurves(True)   # the curve chosen is gone

        pen = self.currentPen()
        with blocked(self.patternComboBox, self.lineWidthSpinBox):
            if pen.style() in PEN_STYLES:
                self.patternComboBox.setCurrentIndex(PEN_STYLES.index(pen.style()))
            self.lineWidthSpinBox.setValue(max(1, pen.width()))
        self.lineColorButton.setColor(pen.color())
        curves = style.curveStyle
        self.startHueButton.setColor(QColor.fromHsv(curves.startHue, 255, 255))
        self.endHueButton.setColor(QColor.fromHsv(curves.endHue, 255, 255))
        self.curvesForm.setRowVisible(self.gradientRow, not single)

    def refreshSymbols(self, style):
        points = style.pointStyle
        index = style.currentCurveIndex()
        single = not style.applyToAllCurves() and 0 <= index < len(points.pointSymbols)
        symbol = points.pointSymbols[index] if single else points.commonPointSymbol
        size = points.pointSizes[index] if single else points.commonPointSize
        with blocked(self.symbolComboBox, self.symbolSizeSpinBox):
            if symbol in points.symbols:
                self.symbolComboBox.setCurrentIndex(points.symbols.index(symbol))
            self.symbolSizeSpinBox.setValue(size)
        self.symbolsForm.setRowVisible(self.varySymbolsButton, not single)

    def refreshAxes(self, style):
        axes = style.axesStyle
        for name, button in self.axesColorButtons.items():
            button.setColor(getattr(axes, name).getColor())
        for name, button in self.axesFontButtons.items():
            button.setFontValue(getattr(axes, name).getFont())
        with blocked(self.axesWidthSpinBox):
            self.axesWidthSpinBox.setValue(axes.axesWidth)

    def refreshLegend(self, legend):
        self.legendTextColorButton.setColor(legend.textColor)
        self.legendBackgroundButton.setColor(legend.backgroundColor)
        self.legendNoBackgroundButton.setEnabled(legend.backgroundColor is not None)
        self.legendBorderColorButton.setColor(legend.borderPen.color())
        with blocked(self.legendTextSizeSpinBox, self.legendBorderPatternComboBox, self.legendBorderWidthSpinBox,
                     self.legendOffsetXSpinBox, self.legendOffsetYSpinBox):
            self.legendTextSizeSpinBox.setValue(legend.textSize)
            if legend.borderPen.style() in PEN_STYLES:
                self.legendBorderPatternComboBox.setCurrentIndex(PEN_STYLES.index(legend.borderPen.style()))
            self.legendBorderWidthSpinBox.setValue(legend.borderPen.width())
            self.legendOffsetXSpinBox.setValue(int(legend.offset[0]))
            self.legendOffsetYSpinBox.setValue(int(legend.offset[1]))
