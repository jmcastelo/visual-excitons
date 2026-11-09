from contextlib import ExitStack

from PySide6.QtCore import Signal, Slot, Qt, QSignalBlocker
from PySide6.QtWidgets import QColorDialog, QWidget, QLabel, QComboBox, QGroupBox, QRadioButton
from PySide6.QtWidgets import QPushButton, QSpinBox, QDoubleSpinBox, QVBoxLayout, QHBoxLayout, QGridLayout
from PySide6.QtWidgets import QStackedLayout, QSizePolicy, QTabWidget, QFontDialog

from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle, PEN_STYLES


def blocked(*widgets):
    """Context in which `widgets` emit no signals: showing a value must not apply it again."""
    stack = ExitStack()
    for widget in widgets:
        stack.enter_context(QSignalBlocker(widget))
    return stack


class ApplyCurveStyleWidget(QWidget):
    allCurvesSelected = Signal(bool)
    singleCurveSelected = Signal(bool)

    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        # Apply curve style widgets

        allCurvesRadio = QRadioButton("All Curves")
        allCurvesRadio.setChecked(True)
        allCurvesRadio.toggled.connect(self.toggleAllCurvesWidgets)
        allCurvesRadio.toggled.connect(self.allCurvesSelected)

        singleCurveRadio = QRadioButton("Single Curve")
        singleCurveRadio.toggled.connect(self.toggleSingleCurveWidgets)
        singleCurveRadio.toggled.connect(self.singleCurveSelected)

        styleLayout = QHBoxLayout()
        styleLayout.addWidget(allCurvesRadio)
        styleLayout.addWidget(singleCurveRadio)

        styleGroupBox = QGroupBox("Apply Changes to:")
        styleGroupBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        styleGroupBox.setLayout(styleLayout)

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(styleGroupBox)

        self.setLayout(mainLayout)

    @Slot()
    def toggleAllCurvesWidgets(self, checked):
        self.style.setApplyToAllCurves(True)

    @Slot()
    def toggleSingleCurveWidgets(self, checked):
        self.style.setApplyToAllCurves(False)


class ApplyGraphStyleWidget(QWidget):
    allGraphsSelected = Signal(bool)
    singleGraphSelected = Signal(bool)

    def __init__(self):
        QWidget.__init__(self)

        # Apply graph style widgets

        self.allGraphsRadio = QRadioButton("All Graphs")
        self.allGraphsRadio.clicked.connect(self.allGraphsSelected)

        self.singleGraphRadio = QRadioButton("Single Graph")
        self.singleGraphRadio.setChecked(True)
        self.singleGraphRadio.clicked.connect(self.singleGraphSelected)

        styleLayout = QHBoxLayout()
        styleLayout.addWidget(self.allGraphsRadio)
        styleLayout.addWidget(self.singleGraphRadio)

        styleGroupBox = QGroupBox("Apply Changes to:")
        styleGroupBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        styleGroupBox.setLayout(styleLayout)

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(styleGroupBox)

        self.setLayout(mainLayout)

    def setAllGraphs(self):
        if not self.allGraphsRadio.isChecked():
            self.allGraphsRadio.setChecked(True)

    def setSingleGraph(self):
        if not self.singleGraphRadio.isChecked():
            self.singleGraphRadio.setChecked(True)

class CurveStyleWidget(QWidget):
    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        # Line style widgets

        lineStyleLabel = QLabel("Pattern")

        self.lineStyleComboBox = QComboBox()
        self.lineStyleComboBox.addItems(["Solid Line", "Dash Line", "Dot Line", "Dash-Dot Line", "Dash-Dot-Dot Line"])
        self.lineStyleComboBox.setCurrentIndex(0)
        self.lineStyleComboBox.currentIndexChanged.connect(self.style.curveStyle.setCurveStyle)

        # Line color widgets

        self.lineColorDialog = QColorDialog()
        self.lineColorDialog.setWindowTitle("Line Color")
        self.lineColorDialog.currentColorChanged.connect(self.style.curveStyle.setCurveColor)

        lineColorLabel = QLabel("Color")

        lineColorButton = QPushButton("Select")
        lineColorButton.clicked.connect(self.lineColorDialog.show)
        lineColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Line width widgets

        lineWidthLabel = QLabel("Width")

        self.lineWidthSpinBox = QSpinBox()
        self.lineWidthSpinBox.setRange(1, 7)
        self.lineWidthSpinBox.setValue(1)
        self.lineWidthSpinBox.valueChanged.connect(self.style.curveStyle.setCurveWidth)
        self.lineWidthSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Gradient style widgets

        self.startColorDialog = QColorDialog()
        self.startColorDialog.setWindowTitle("Start Color")
        self.startColorDialog.currentColorChanged.connect(self.pickStartColor)

        self.endColorDialog = QColorDialog()
        self.endColorDialog.setWindowTitle("End Color")
        self.endColorDialog.currentColorChanged.connect(self.pickEndColor)

        startColorButton = QPushButton("Start Color")
        startColorButton.clicked.connect(self.startColorDialog.show)
        startColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        endColorButton = QPushButton("End Color")
        endColorButton.clicked.connect(self.endColorDialog.show)
        endColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        gradientLayout = QHBoxLayout()
        gradientLayout.addWidget(startColorButton)
        gradientLayout.addWidget(endColorButton)

        self.gradientGroup = QGroupBox("Color Gradient")
        self.gradientGroup.setLayout(gradientLayout)

        # Main layout

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        mainLayout.addWidget(lineStyleLabel, 0, 0)
        mainLayout.addWidget(self.lineStyleComboBox, 0, 1)
        mainLayout.addWidget(lineColorLabel, 1, 0)
        mainLayout.addWidget(lineColorButton, 1, 1)
        mainLayout.addWidget(lineWidthLabel, 2, 0)
        mainLayout.addWidget(self.lineWidthSpinBox, 2, 1)
        mainLayout.addWidget(self.gradientGroup, 3, 0, 1, 2)

        self.setLayout(mainLayout)

    @Slot()
    def pickStartColor(self, color):
        self.style.curveStyle.startHue = color.hue()
        self.style.curveStyle.setGradientPalette()

    @Slot()
    def pickEndColor(self, color):
        self.style.curveStyle.endHue = color.hue()
        self.style.curveStyle.setGradientPalette()

    @Slot()
    def setWidgetsValues(self):
        if not self.style.applyToAllCurves():
            pen = self.style.curveStyle.curvePens[self.style.currentCurveIndex()]
        elif len(self.style.curveStyle.curvePens) > 0 and self.style.curveStyle.allCurvePensEqual():
            pen = self.style.curveStyle.curvePens[0]
        else:
            pen = None

        if pen is None and not self.style.curveStyle.curvePens:
            pen = self.style.curveStyle.commonPen   # no curves yet: the style they will get

        if pen is not None:
            with blocked(self.lineStyleComboBox, self.lineColorDialog, self.lineWidthSpinBox):
                if pen.style() in PEN_STYLES:
                    self.lineStyleComboBox.setCurrentIndex(PEN_STYLES.index(pen.style()))
                self.lineColorDialog.setCurrentColor(pen.color())
                self.lineWidthSpinBox.setValue(pen.width())

    @Slot()
    def showWidgets(self, checked):
        # self.plainStyleButton.show()
        self.gradientGroup.show()

    @Slot()
    def hideWidgets(self, checked):
        # self.plainStyleButton.hide()
        self.gradientGroup.hide()

    @Slot()
    def closeDialogs(self):
        self.lineColorDialog.close()
        self.startColorDialog.close()
        self.endColorDialog.close()


class PointStyleWidget(QWidget):
    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        # Symbol shape widgets

        symbolStyleLabel = QLabel('Shape')

        self.symbolStyleComboBox = QComboBox()
        self.symbolStyleComboBox.addItems(['Circle', 'Square', 'Triangle Down', 'Triangle Up', 'Triangle Right', 'Triangle Left', 'Diamond', 'Plus', 'Pentagon', 'Hexagon', 'Star', 'Cross', 'Arrow Up', 'Arrow Right', 'Arrow Down', 'Arrow Left', 'Crosshair'])
        self.symbolStyleComboBox.setCurrentIndex(0)
        self.symbolStyleComboBox.currentIndexChanged.connect(self.style.pointStyle.setPointSymbol)

        self.symbolStyleGradientLabel = QLabel('Shape Gradient')

        self.symbolStyleGradientButton = QPushButton('Apply')
        self.symbolStyleGradientButton.clicked.connect(self.style.pointStyle.setSymbolGradient)
        self.symbolStyleGradientButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Symbol size

        symbolSizeLabel = QLabel('Size (px)')

        self.symbolSizeSpinBox = QSpinBox()
        self.symbolSizeSpinBox.setRange(0, 500)
        self.symbolSizeSpinBox.setValue(6)
        self.symbolSizeSpinBox.valueChanged.connect(self.style.pointStyle.setPointSize)
        self.symbolSizeSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Main layout

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        mainLayout.addWidget(symbolStyleLabel, 0, 0)
        mainLayout.addWidget(self.symbolStyleComboBox, 0, 1)
        mainLayout.addWidget(self.symbolStyleGradientLabel, 1, 0)
        mainLayout.addWidget(self.symbolStyleGradientButton, 1, 1)
        mainLayout.addWidget(symbolSizeLabel, 2, 0)
        mainLayout.addWidget(self.symbolSizeSpinBox, 2, 1)

        self.setLayout(mainLayout)

    @Slot()
    def setWidgetsValues(self):
        points = self.style.pointStyle
        symbolIndex, size = points.currentPointSymbolIndex(), points.currentPointSize()
        if not points.pointSymbols:   # no curves yet: the style they will get
            symbolIndex, size = points.symbols.index(points.commonPointSymbol), points.commonPointSize

        with blocked(self.symbolStyleComboBox, self.symbolSizeSpinBox):
            if symbolIndex is not None:
                self.symbolStyleComboBox.setCurrentIndex(symbolIndex)
            if size is not None:
                self.symbolSizeSpinBox.setValue(size)

    @Slot()
    def showWidgets(self, checked):
        self.symbolStyleGradientLabel.show()
        self.symbolStyleGradientButton.show()

    @Slot()
    def hideWidgets(self, checked):
        self.symbolStyleGradientLabel.hide()
        self.symbolStyleGradientButton.hide()


class LegendStyleWidget(QWidget):
    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        # Text color widgets

        self.textColorDialog = QColorDialog()
        self.textColorDialog.setWindowTitle('Text Color')
        self.textColorDialog.currentColorChanged.connect(self.style.legendStyle.setTextColor)

        textColorLabel = QLabel('Text Color')

        textColorButton = QPushButton('Select')
        textColorButton.clicked.connect(self.textColorDialog.show)
        textColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Text size widgets

        textSizeLabel = QLabel('Text Size')

        self.textSizeSpinBox = QSpinBox()
        self.textSizeSpinBox.setRange(1, 100)
        self.textSizeSpinBox.setValue(self.style.legendStyle.textSize)
        self.textSizeSpinBox.valueChanged.connect(self.style.legendStyle.setTextSize)
        self.textSizeSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Background color widgets

        self.backgroundColorDialog = QColorDialog()
        self.backgroundColorDialog.setWindowTitle('Background Color')
        self.backgroundColorDialog.currentColorChanged.connect(self.style.legendStyle.setBackgroundColor)

        backgroundColorLabel = QLabel('Background Color')

        backgroundColorButton = QPushButton('Select')
        backgroundColorButton.clicked.connect(self.backgroundColorDialog.show)
        backgroundColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Border style widgets

        borderStyleLabel = QLabel('Border Style')

        self.borderStyleComboBox = QComboBox()
        self.borderStyleComboBox.addItems(["Solid Line", "Dash Line", "Dot Line", "Dash-Dot Line", "Dash-Dot-Dot Line"])
        self.borderStyleComboBox.setCurrentIndex(0)
        self.borderStyleComboBox.currentIndexChanged.connect(self.style.legendStyle.setBorderStyle)

        # Border width widgets

        borderWidthLabel = QLabel('Border Width')

        self.borderWidthSpinBox = QSpinBox()
        self.borderWidthSpinBox.setRange(0, 7)
        self.borderWidthSpinBox.setValue(0)
        self.borderWidthSpinBox.valueChanged.connect(self.style.legendStyle.setBorderWidth)
        self.borderWidthSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Border color widgets

        self.borderColorDialog = QColorDialog()
        self.borderColorDialog.setWindowTitle('Border Color')
        self.borderColorDialog.currentColorChanged.connect(self.style.legendStyle.setBorderColor)

        borderColorLabel = QLabel('Border Color')

        borderColorButton = QPushButton('Select')
        borderColorButton.clicked.connect(self.borderColorDialog.show)
        borderColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Offset X widgets

        offsetXLabel = QLabel('Offset X')

        self.offsetXSpinBox = QSpinBox()
        self.offsetXSpinBox.setRange(0, 1000)
        self.offsetXSpinBox.setValue(30)
        self.offsetXSpinBox.valueChanged.connect(self.style.legendStyle.setOffsetX)
        self.offsetXSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Offset Y widgets

        offsetYLabel = QLabel('Offset Y')

        self.offsetYSpinBox = QSpinBox()
        self.offsetYSpinBox.setRange(0, 1000)
        self.offsetYSpinBox.setValue(30)
        self.offsetYSpinBox.valueChanged.connect(self.style.legendStyle.setOffsetY)
        self.offsetYSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Main layout

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        mainLayout.addWidget(textColorLabel, 0, 0)
        mainLayout.addWidget(textColorButton, 0, 1)
        mainLayout.addWidget(textSizeLabel, 1, 0)
        mainLayout.addWidget(self.textSizeSpinBox, 1, 1)
        mainLayout.addWidget(backgroundColorLabel, 2, 0)
        mainLayout.addWidget(backgroundColorButton, 2, 1)
        mainLayout.addWidget(borderStyleLabel, 3, 0)
        mainLayout.addWidget(self.borderStyleComboBox, 3, 1)
        mainLayout.addWidget(borderWidthLabel, 4, 0)
        mainLayout.addWidget(self.borderWidthSpinBox, 4, 1)
        mainLayout.addWidget(borderColorLabel, 5, 0)
        mainLayout.addWidget(borderColorButton, 5, 1)
        mainLayout.addWidget(offsetXLabel, 6, 0)
        mainLayout.addWidget(self.offsetXSpinBox, 6, 1)
        mainLayout.addWidget(offsetYLabel, 7, 0)
        mainLayout.addWidget(self.offsetYSpinBox, 7, 1)

        self.setLayout(mainLayout)

    @Slot()
    def setWidgetsValues(self):
        legend = self.style.legendStyle
        with blocked(self.textColorDialog, self.textSizeSpinBox, self.backgroundColorDialog, self.borderStyleComboBox,
                     self.borderWidthSpinBox, self.borderColorDialog, self.offsetXSpinBox, self.offsetYSpinBox):
            self.textColorDialog.setCurrentColor(legend.textColor)
            self.textSizeSpinBox.setValue(legend.textSize)
            if legend.backgroundColor is not None:
                self.backgroundColorDialog.setCurrentColor(legend.backgroundColor)
            if legend.borderPen.style() in PEN_STYLES:
                self.borderStyleComboBox.setCurrentIndex(PEN_STYLES.index(legend.borderPen.style()))
            self.borderWidthSpinBox.setValue(legend.borderPen.width())
            self.borderColorDialog.setCurrentColor(legend.borderPen.color())
            self.offsetXSpinBox.setValue(legend.offset[0])
            self.offsetYSpinBox.setValue(legend.offset[1])

    def closeDialogs(self):
        self.textColorDialog.close()
        self.backgroundColorDialog.close()
        self.borderColorDialog.close()


class AxesStyleElement():
    def __init__(self, name, color, font):
        self.name = name
        self.color = color
        self.font = font


class AxesStyleWidget(QWidget):
    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        # Elements

        elementsLabel = QLabel('Style Elements')

        self.elements = [AxesStyleElement('Title', self.style.axesStyle.titleColor, self.style.axesStyle.titleFont), AxesStyleElement('Labels', self.style.axesStyle.labelsColor, self.style.axesStyle.labelsFont), AxesStyleElement('Ticks', self.style.axesStyle.ticksColor, self.style.axesStyle.ticksFont), AxesStyleElement('Axes', self.style.axesStyle.axesColor, None), AxesStyleElement('Background', self.style.axesStyle.backgroundColor, None)]

        self.elementsComboBox = QComboBox()
        for element in self.elements:
            self.elementsComboBox.addItem(element.name)
        self.elementsComboBox.currentIndexChanged.connect(self.selectElement)
        self.elementsComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Color and font dialogs

        self.colorDialog = QColorDialog()
        self.fontDialog = QFontDialog()

        # Color button

        self.colorButton = QPushButton('Color')
        self.colorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.colorButton.clicked.connect(self.colorDialog.show)

        # Font button

        self.fontButton = QPushButton('Font')
        self.fontButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.fontButton.clicked.connect(self.fontDialog.show)

        # Axes pen width widgets

        axesPenWidthLabel = QLabel('Axes Width')

        self.axesPenWidthSpinBox = QSpinBox()
        self.axesPenWidthSpinBox.setRange(1, 10)
        self.axesPenWidthSpinBox.setValue(self.style.axesStyle.axesWidth)
        self.axesPenWidthSpinBox.valueChanged.connect(self.style.axesStyle.setAxesWidth)
        self.axesPenWidthSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        # Width changed in another graph's style, when linked
        self.style.axesStyle.axesWidthChanged.connect(self.setWidgetsValues)

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        mainLayout.addWidget(elementsLabel, 0, 0)
        mainLayout.addWidget(self.elementsComboBox, 0, 1)
        mainLayout.addWidget(self.colorButton, 1, 0)
        mainLayout.addWidget(self.fontButton, 1, 1)
        mainLayout.addWidget(axesPenWidthLabel, 2, 0)
        mainLayout.addWidget(self.axesPenWidthSpinBox, 2, 1)

        self.setLayout(mainLayout)

        self.lastColorIndex = -1
        self.lastFontIndex = -1

        self.selectElement(0)

    @Slot()
    def setWidgetsValues(self, *args):
        element = self.elements[self.elementsComboBox.currentIndex()]
        with blocked(self.axesPenWidthSpinBox, self.colorDialog, self.fontDialog):
            self.axesPenWidthSpinBox.setValue(self.style.axesStyle.axesWidth)
            if element.color is not None:
                self.colorDialog.setCurrentColor(element.color.getColor())
            if element.font is not None:
                self.fontDialog.setCurrentFont(element.font.getFont())

    @Slot()
    def selectElement(self, index):
        if self.elements[index].color != None:
            self.colorButton.show()

            self.colorDialog.setWindowTitle(self.elements[index].name + ' Color')

            if self.lastColorIndex >= 0:
                self.colorDialog.currentColorChanged.disconnect(self.elements[self.lastColorIndex].color.setColor)

            self.colorDialog.setCurrentColor(self.elements[index].color.getColor())

            self.colorDialog.currentColorChanged.connect(self.elements[index].color.setColor)

            self.lastColorIndex = index
        else:
            self.colorButton.hide()
            self.colorDialog.close()

        if self.elements[index].font != None:
            self.fontButton.show()

            self.fontDialog.setWindowTitle(self.elements[index].name + ' Font')

            if self.lastFontIndex >= 0:
                self.fontDialog.currentFontChanged.disconnect(self.elements[self.lastFontIndex].font.setFont)

            self.fontDialog.setCurrentFont(self.elements[index].font.getFont())

            self.fontDialog.currentFontChanged.connect(self.elements[index].font.setFont)

            self.lastFontIndex = index
        else:
            self.fontButton.hide()
            self.fontDialog.close()

    @Slot()
    def closeDialogs(self):
        self.colorDialog.close()
        self.fontDialog.close()


class FillStyleWidget(QWidget):
    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        # Weights color widgets

        self.weightsColorDialog = QColorDialog()
        self.weightsColorDialog.setWindowTitle('Fill Color')
        self.weightsColorDialog.setCurrentColor(self.style.brush.color())
        self.weightsColorDialog.currentColorChanged.connect(self.style.setBrushColor)

        weightsColorLabel = QLabel('Fill Color')

        weightsColorButton = QPushButton('Select')
        weightsColorButton.clicked.connect(self.weightsColorDialog.show)
        weightsColorButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Weight factor widgets

        weightFactorLabel = QLabel('Weight Factor')

        self.weightFactorSpin = QDoubleSpinBox()
        self.weightFactorSpin.setMinimum(0.0)
        self.weightFactorSpin.setMaximum(1000.0)
        self.weightFactorSpin.setValue(self.style.weightFactor)
        self.weightFactorSpin.valueChanged.connect(self.style.setWeightFactor)
        self.weightFactorSpin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        mainLayout.addWidget(weightsColorLabel, 0, 0)
        mainLayout.addWidget(weightsColorButton, 0, 1)
        mainLayout.addWidget(weightFactorLabel, 1, 0)
        mainLayout.addWidget(self.weightFactorSpin, 1, 1)

        self.setLayout(mainLayout)

    @Slot()
    def setWidgetsValues(self):
        with blocked(self.weightsColorDialog, self.weightFactorSpin):
            self.weightsColorDialog.setCurrentColor(self.style.brush.color())
            self.weightFactorSpin.setValue(self.style.weightFactor)

    def closeDialogs(self):
        self.weightsColorDialog.close()


class BandStructureStyleWidget(QWidget):
    allGraphs = Signal()
    singleGraph = Signal()

    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        self.curveStyleWidget = CurveStyleWidget(self.style)
        self.fillStyleWidget = FillStyleWidget(self.style)
        self.axesStyleWidget = AxesStyleWidget(style)
        applyCurveStyleWidget = ApplyCurveStyleWidget(self.style)
        self.applyGraphStyleWidget = ApplyGraphStyleWidget()

        applyCurveStyleWidget.allCurvesSelected.connect(self.curveStyleWidget.showWidgets)
        applyCurveStyleWidget.singleCurveSelected.connect(self.curveStyleWidget.hideWidgets)

        self.applyGraphStyleWidget.allGraphsSelected.connect(self.setConnectStyles)
        self.applyGraphStyleWidget.singleGraphSelected.connect(self.unsetConnectStyles)
        self.applyGraphStyleWidget.allGraphsSelected.connect(self.allGraphs)
        self.applyGraphStyleWidget.singleGraphSelected.connect(self.singleGraph)

        mainTabWidget = QTabWidget()
        mainTabWidget.addTab(self.curveStyleWidget, 'Lines')
        mainTabWidget.addTab(self.fillStyleWidget, 'Fill')
        mainTabWidget.addTab(self.axesStyleWidget, 'Axes')
        mainTabWidget.currentChanged.connect(self.setApplyStyleWidget)
        mainTabWidget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.stackedLayout = QStackedLayout()
        self.stackedLayout.addWidget(applyCurveStyleWidget)
        self.stackedLayout.addWidget(self.applyGraphStyleWidget)
        self.stackedLayout.setCurrentIndex(0)

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(mainTabWidget)
        mainLayout.addLayout(self.stackedLayout)

        self.setLayout(mainLayout)

    @Slot()
    def setWidgetsValues(self):
        self.curveStyleWidget.setWidgetsValues()

    def refresh(self):
        """Show the values of the style (e.g. once restored)."""
        self.curveStyleWidget.setWidgetsValues()
        self.fillStyleWidget.setWidgetsValues()
        self.axesStyleWidget.setWidgetsValues()

    @Slot()
    def setApplyStyleWidget(self, tabIndex):
        if tabIndex == 0:
            self.stackedLayout.setCurrentIndex(0)
            self.stackedLayout.currentWidget().show()
        elif tabIndex == 1:
            self.stackedLayout.currentWidget().hide()
        elif tabIndex == 2:
            self.stackedLayout.setCurrentIndex(1)
            self.stackedLayout.currentWidget().show()

    @Slot()
    def setConnectStyles(self):
        self.style.setConnectStyles(True)
        self.style.linkStyles()

    @Slot()
    def unsetConnectStyles(self):
        self.style.unlinkStyles()
        self.style.setConnectStyles(False)

    @Slot()
    def setAllGraphs(self):
        self.applyGraphStyleWidget.setAllGraphs()

    @Slot()
    def setSingleGraph(self):
        self.applyGraphStyleWidget.setSingleGraph()

    def connectWidgets(self, widgets):
        for i in range(len(widgets)):
            self.allGraphs.connect(widgets[i].setAllGraphs)
            self.singleGraph.connect(widgets[i].setSingleGraph)

    def closeDialogs(self):
        self.curveStyleWidget.closeDialogs()
        self.fillStyleWidget.closeDialogs()
        self.axesStyleWidget.closeDialogs()


class DispersionStyleWidget(QWidget):
    allGraphs = Signal()
    singleGraph = Signal()

    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        self.curveStyleWidget = CurveStyleWidget(style)
        self.pointStyleWidget = PointStyleWidget(style)
        self.axesStyleWidget = AxesStyleWidget(style)
        applyCurveStyleWidget = ApplyCurveStyleWidget(style)
        self.applyGraphStyleWidget = ApplyGraphStyleWidget()

        applyCurveStyleWidget.allCurvesSelected.connect(self.curveStyleWidget.showWidgets)
        applyCurveStyleWidget.allCurvesSelected.connect(self.pointStyleWidget.showWidgets)
        applyCurveStyleWidget.singleCurveSelected.connect(self.curveStyleWidget.hideWidgets)
        applyCurveStyleWidget.singleCurveSelected.connect(self.pointStyleWidget.hideWidgets)

        self.applyGraphStyleWidget.allGraphsSelected.connect(self.setConnectStyles)
        self.applyGraphStyleWidget.singleGraphSelected.connect(self.unsetConnectStyles)
        self.applyGraphStyleWidget.allGraphsSelected.connect(self.allGraphs)
        self.applyGraphStyleWidget.singleGraphSelected.connect(self.singleGraph)

        mainTabWidget = QTabWidget()
        mainTabWidget.addTab(self.curveStyleWidget, 'Lines')
        mainTabWidget.addTab(self.pointStyleWidget, 'Symbols')
        mainTabWidget.addTab(self.axesStyleWidget, 'Axes')
        mainTabWidget.currentChanged.connect(self.setApplyStyleWidget)
        mainTabWidget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.stackedLayout = QStackedLayout()
        self.stackedLayout.addWidget(applyCurveStyleWidget)
        self.stackedLayout.addWidget(self.applyGraphStyleWidget)
        self.stackedLayout.setCurrentIndex(0)

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(mainTabWidget)
        mainLayout.addLayout(self.stackedLayout)

        self.setLayout(mainLayout)

    @Slot()
    def setWidgetsValues(self):
        self.curveStyleWidget.setWidgetsValues()
        self.pointStyleWidget.setWidgetsValues()

    def refresh(self):
        """Show the values of the style (e.g. once restored)."""
        self.setWidgetsValues()
        self.axesStyleWidget.setWidgetsValues()

    @Slot()
    def setApplyStyleWidget(self, tabIndex):
        if tabIndex == 2:
            self.stackedLayout.setCurrentIndex(1)
        else:
            self.stackedLayout.setCurrentIndex(0)

    @Slot()
    def setConnectStyles(self):
        self.style.setConnectStyles(True)
        self.style.linkStyles()

    @Slot()
    def unsetConnectStyles(self):
        self.style.unlinkStyles()
        self.style.setConnectStyles(False)

    @Slot()
    def setAllGraphs(self):
        self.applyGraphStyleWidget.setAllGraphs()

    @Slot()
    def setSingleGraph(self):
        self.applyGraphStyleWidget.setSingleGraph()

    def connectWidgets(self, widgets):
        for i in range(len(widgets)):
            self.allGraphs.connect(widgets[i].setAllGraphs)
            self.singleGraph.connect(widgets[i].setSingleGraph)

    def closeDialogs(self):
        self.curveStyleWidget.closeDialogs()
        self.axesStyleWidget.closeDialogs()


class AbsorptionStyleWidget(QWidget):
    allGraphs = Signal()
    singleGraph = Signal()

    def __init__(self, style):
        QWidget.__init__(self)

        self.style = style

        self.curveStyleWidget = CurveStyleWidget(style)
        self.pointStyleWidget = PointStyleWidget(style)
        self.axesStyleWidget = AxesStyleWidget(style)
        self.legendStyleWidget = LegendStyleWidget(style)
        applyCurveStyleWidget = ApplyCurveStyleWidget(style)
        self.applyGraphStyleWidget = ApplyGraphStyleWidget()

        applyCurveStyleWidget.allCurvesSelected.connect(self.curveStyleWidget.showWidgets)
        applyCurveStyleWidget.allCurvesSelected.connect(self.pointStyleWidget.showWidgets)
        applyCurveStyleWidget.singleCurveSelected.connect(self.curveStyleWidget.hideWidgets)
        applyCurveStyleWidget.singleCurveSelected.connect(self.pointStyleWidget.hideWidgets)

        self.applyGraphStyleWidget.allGraphsSelected.connect(self.setConnectStyles)
        self.applyGraphStyleWidget.singleGraphSelected.connect(self.unsetConnectStyles)
        self.applyGraphStyleWidget.allGraphsSelected.connect(self.allGraphs)
        self.applyGraphStyleWidget.singleGraphSelected.connect(self.singleGraph)

        mainTabWidget = QTabWidget()
        mainTabWidget.addTab(self.curveStyleWidget, 'Lines')
        mainTabWidget.addTab(self.pointStyleWidget, 'Symbols')
        mainTabWidget.addTab(self.axesStyleWidget, 'Axes')
        mainTabWidget.addTab(self.legendStyleWidget, 'Legend')
        mainTabWidget.currentChanged.connect(self.setApplyStyleWidget)
        mainTabWidget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.stackedLayout = QStackedLayout()
        self.stackedLayout.addWidget(applyCurveStyleWidget)
        self.stackedLayout.addWidget(self.applyGraphStyleWidget)
        self.stackedLayout.setCurrentIndex(0)

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(mainTabWidget)
        mainLayout.addLayout(self.stackedLayout)

        self.setLayout(mainLayout)

    @Slot()
    def setWidgetsValues(self):
        self.curveStyleWidget.setWidgetsValues()
        self.pointStyleWidget.setWidgetsValues()

    def refresh(self):
        """Show the values of the style (e.g. once restored)."""
        self.setWidgetsValues()
        self.axesStyleWidget.setWidgetsValues()
        self.legendStyleWidget.setWidgetsValues()

    @Slot()
    def setApplyStyleWidget(self, tabIndex):
        if tabIndex == 2:
            self.stackedLayout.setCurrentIndex(1)
        else:
            self.stackedLayout.setCurrentIndex(0)

    @Slot()
    def setConnectStyles(self):
        self.style.setConnectStyles(True)
        self.style.linkStyles()

    @Slot()
    def unsetConnectStyles(self):
        self.style.unlinkStyles()
        self.style.setConnectStyles(False)

    @Slot()
    def setAllGraphs(self):
        self.applyGraphStyleWidget.setAllGraphs()

    @Slot()
    def setSingleGraph(self):
        self.applyGraphStyleWidget.setSingleGraph()

    def connectWidgets(self, widgets):
        for i in range(len(widgets)):
            self.allGraphs.connect(widgets[i].setAllGraphs)
            self.singleGraph.connect(widgets[i].setSingleGraph)

    def closeDialogs(self):
        self.curveStyleWidget.closeDialogs()
        self.axesStyleWidget.closeDialogs()
        self.legendStyleWidget.closeDialogs()


class StyleWidget(QWidget):
    def __init__(self, dispersionStyle: DispersionStyle, absorptionStyle: AbsorptionStyle, bandStructureStyle: BandStructureStyle):
        QWidget.__init__(self)

        # Graph style widgets

        self.dispersionStyleWidget = DispersionStyleWidget(dispersionStyle)
        self.absorptionStyleWidget = AbsorptionStyleWidget(absorptionStyle)
        self.bandStructureStyleWidget = BandStructureStyleWidget(bandStructureStyle)

        self.dispersionStyleWidget.connectWidgets([self.absorptionStyleWidget, self.bandStructureStyleWidget])
        self.absorptionStyleWidget.connectWidgets([self.dispersionStyleWidget, self.bandStructureStyleWidget])
        self.bandStructureStyleWidget.connectWidgets([self.dispersionStyleWidget, self.absorptionStyleWidget])

        self.stackedLayout = QStackedLayout()
        self.stackedLayout.addWidget(self.dispersionStyleWidget)
        self.stackedLayout.addWidget(self.absorptionStyleWidget)
        self.stackedLayout.addWidget(self.bandStructureStyleWidget)
        self.stackedLayout.setCurrentIndex(0)

        # Graph selector widgets

        graphSelector = QComboBox()
        graphSelector.addItems(["Dispersion", "Absorption", "Band Structure"])
        graphSelector.setCurrentIndex(0)
        graphSelector.currentIndexChanged.connect(self.switchStyleWidget)
        graphSelector.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(graphSelector)
        mainLayout.addLayout(self.stackedLayout)

        self.setLayout(mainLayout)

        # Connections

        dispersionStyle.currentCurveIndexChanged.connect(self.dispersionStyleWidget.setWidgetsValues)
        absorptionStyle.currentCurveIndexChanged.connect(self.absorptionStyleWidget.setWidgetsValues)
        bandStructureStyle.currentCurveIndexChanged.connect(self.bandStructureStyleWidget.setWidgetsValues)

        dispersionStyle.styleChanged.connect(self.dispersionStyleWidget.setWidgetsValues)
        # bandStructureStyle.styleChanged.connect(self.bandStructureStyleWidget.setWidgetsValues)

    def refresh(self):
        """Show the values of the three styles (e.g. once restored)."""
        for widget in (self.dispersionStyleWidget, self.absorptionStyleWidget, self.bandStructureStyleWidget):
            widget.refresh()

    @Slot()
    def switchStyleWidget(self, index):
        # Previous style widget

        previousStyleWidget = self.stackedLayout.currentWidget()

        previousStyleWidget.closeDialogs()
        previousStyleWidget.style.unlinkStyles()

        # Next style widget

        self.stackedLayout.setCurrentIndex(index)

        nextStyleWidget = self.stackedLayout.currentWidget()

        nextStyleWidget.style.linkStyles()

    def closeEvent(self, event):
        currentStyleWidget = self.stackedLayout.currentWidget()
        currentStyleWidget.closeDialogs()
        event.accept()
