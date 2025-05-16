# This Python file uses the following encoding: utf-8
from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QColor, QFont
import pyqtgraph as pg


class StyleCommon:
    def __init__(self):
        self.numCurves = 0
        self.currentCurveIndex = -1
        self.applyToAllCurves = True

    def decreaseNumCurves(self):
        self.numCurves -= 1
        if self.currentCurveIndex >= self.numCurves:
            self.currentCurveIndex = self.numCurves - 1


class CurveStyle(QObject):
    styleChanged = Signal()

    def __init__(self, common):
        super().__init__()

        self.common = common

        self.curvePens = []

        self.styles = [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine, Qt.PenStyle.DashDotDotLine]

        self.commonPen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = 1.0, color = QColor('white'))

        self.startHue = 0
        self.endHue = 300

    def allCurvePensEqual(self):
        return all(pen == self.curvePens[0] for pen in self.curvePens)

    def setCommonPalette(self):
        self.curvePens.clear()

        for i in range(self.common.numCurves):
            pen = pg.mkPen(style = self.commonPen.style(), width = self.commonPen.width(), color = self.commonPen.color())
            self.curvePens.append(pen)

    @Slot()
    def setGradientPalette(self):
        hueMin = min(self.startHue, self.endHue)
        hueMax = max(self.startHue, self.endHue)

        for i in range(self.common.numCurves):
            hue = hueMin + int((hueMax - hueMin) * float(i) / (self.common.numCurves - 1))
            color = QColor.fromHsv(hue, 255, 255)
            self.curvePens[i].setColor(color)

        self.styleChanged.emit()

    @Slot()
    def setCurveStyle(self, styleIndex):
        if self.common.applyToAllCurves:
            self.commonPen.setStyle(self.styles[styleIndex])
            for curvePen in self.curvePens:
                curvePen.setStyle(self.styles[styleIndex])
        elif self.common.currentCurveIndex >= 0:
            self.curvePens[self.common.currentCurveIndex].setStyle(self.styles[styleIndex])

        self.styleChanged.emit()

    @Slot()
    def setCurveColor(self, color):
        if self.common.applyToAllCurves:
            self.commonPen.setColor(color)
            for curvePen in self.curvePens:
                curvePen.setColor(color)
        elif self.common.currentCurveIndex >= 0:
            self.curvePens[self.common.currentCurveIndex].setColor(color)

        self.styleChanged.emit()

    @Slot()
    def setCurveWidth(self, width):
        if self.common.applyToAllCurves:
            self.commonPen.setWidth(width)
            for curvePen in self.curvePens:
                curvePen.setWidth(width)
        elif self.common.currentCurveIndex >= 0:
            self.curvePens[self.common.currentCurveIndex].setWidth(width)

        self.styleChanged.emit()


class PointStyle(QObject):
    styleChanged = Signal()

    def __init__(self, common):
        super().__init__()

        self.common = common

        self.pointSymbols = []
        self.pointSizes = []

        self.commonPointSymbol = 'o'
        self.commonPointSize = 6

        self.symbols = ['o', 's', 't', 't1', 't2', 't3', 'd', '+', 'p', 'h', 'star', 'x', 'arrow_up', 'arrow_right', 'arrow_down', 'arrow_left', 'crosshair']

    def allPointSymbolsEqual(self):
        return all(symbol == self.pointSymbols[0] for symbol in self.pointSymbols)

    def allPointSizesEqual(self):
        return all(size == self.pointSizes[0] for size in self.pointSizes)

    def setCommonStyle(self):
        self.pointSymbols.clear()
        self.pointSizes.clear()

        for i in range(self.common.numCurves):
            self.pointSymbols.append(self.commonPointSymbol)
            self.pointSizes.append(self.commonPointSize)

    @Slot()
    def setSymbolGradient(self):
        self.pointSymbols.clear()

        for i in range(self.common.numCurves):
            self.pointSymbols.append(self.symbols[i % len(self.symbols)])

        self.styleChanged.emit()

    @Slot()
    def setPointSymbol(self, symbolIndex):
        if self.common.applyToAllCurves:
            self.commonPointSymbol = self.symbols[symbolIndex]
            for i in range(len(self.pointSymbols)):
                self.pointSymbols[i] = self.symbols[symbolIndex]
        elif self.common.currentCurveIndex >= 0:
            self.pointSymbols[self.common.currentCurveIndex] = self.symbols[symbolIndex]

        self.styleChanged.emit()

    def currentPointSymbolIndex(self):
        if not self.common.applyToAllCurves:
            symbol = self.pointSymbols[self.common.currentCurveIndex]
            symbolIndex = self.symbols.index(symbol)
        elif len(self.pointSymbols) > 0 and self.allPointSymbolsEqual():
            symbol = self.pointSymbols[0]
            symbolIndex = self.symbols.index(symbol)
        else:
            symbolIndex = None

        return symbolIndex

    @Slot()
    def setPointSize(self, size):
        if self.common.applyToAllCurves:
            self.commonPointSize = size
            for i in range(len(self.pointSizes)):
                self.pointSizes[i] = size
        elif self.common.currentCurveIndex >= 0:
            self.pointSizes[self.common.currentCurveIndex] = size

        self.styleChanged.emit()

    def currentPointSize(self):
        if not self.common.applyToAllCurves:
            size = self.pointSizes[self.common.currentCurveIndex]
        elif len(self.pointSizes) > 0 and self.allPointSizesEqual():
            size = self.pointSizes[0]
        else:
            size = None

        return size


class Color(QObject):
    changed = Signal(object)

    def __init__(self, color):
        super().__init__()

        self.color = color

    @Slot()
    def setColor(self, color):
        self.color = color
        self.changed.emit(color)

    def getColor(self):
        return self.color


class Font(QObject):
    changed = Signal(object)

    def __init__(self, font):
        super().__init__()

        self.font= font

    @Slot()
    def setFont(self, font):
        self.font= font
        self.changed.emit(font)

    def getFont(self):
        return self.font


class AxesStyle(QObject):
    axesWidthChanged = Signal(object)

    def __init__(self):
        super().__init__()

        self.titleColor = Color(QColor('lightgray'))
        self.labelsColor = Color(QColor('lightgray'))
        self.ticksColor = Color(QColor('lightgray'))
        self.axesColor = Color(QColor('lightgray'))
        self.backgroundColor = Color(QColor('black'))

        self.titleFont = Font(QFont())
        self.labelsFont = Font(QFont())
        self.ticksFont = Font(QFont())

        self.axesWidth = 1

    @Slot()
    def setAxesWidth(self, width):
        self.axesWidth = width
        self.axesWidthChanged.emit(self.axesWidth)


class LegendStyle(QObject):
    textColorChanged = Signal(object)
    textSizeChanged = Signal(object)
    backgroundColorChanged = Signal(object)
    borderPenChanged = Signal(object)
    offsetChanged = Signal(object)

    def __init__(self):
        super().__init__()

        self.textColor = QColor('lightgray')
        self.textSize = 9
        self.backgroundColor = None
        self.borderPen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = 0.0, color = QColor('black'))
        self.offset = [30, 30]

        self.styles = [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine, Qt.PenStyle.DashDotDotLine]

    @Slot()
    def setTextColor(self, color):
        self.textColor = color
        self.textColorChanged.emit(color)

    @Slot()
    def setTextSize(self, size):
        self.textSize = size
        self.textSizeChanged.emit(size)

    @Slot()
    def setBackgroundColor(self, color):
        self.backgroundColor = color
        self.backgroundColorChanged.emit(color)

    @Slot()
    def setBorderStyle(self, styleIndex):
        self.borderPen.setStyle(self.styles[styleIndex])
        self.borderPenChanged.emit(self.borderPen)

    @Slot()
    def setBorderWidth(self, width):
        self.borderPen.setWidth(width)
        self.borderPenChanged.emit(self.borderPen)

    @Slot()
    def setBorderColor(self, color):
        self.borderPen.setColor(color)
        self.borderPenChanged.emit(self.borderPen)

    @Slot()
    def setOffsetX(self, x):
        self.offset[0] = x
        self.offsetChanged.emit(self.offset)

    @Slot()
    def setOffsetY(self, y):
        self.offset[1] = y
        self.offsetChanged.emit(self.offset)


class BaseStyle(QObject):
    styleChanged = Signal()
    currentCurveIndexChanged = Signal()

    def __init__(self):
        super().__init__()

        self.common = StyleCommon()
        self.axesStyle = AxesStyle()

        self.linkedStyles = []
        self.connectStyles = False

    def setLinkedStyles(self, styles):
        self.linkedStyles = styles

    def setConnectStyles(self, conn):
        self.connectStyles = conn
        for i in range(len(self.linkedStyles)):
            self.linkedStyles[i].connectStyles = conn

    def linkStyles(self):
        if self.connectStyles:
            for i in range(len(self.linkedStyles)):
                self.axesStyle.axesColor.changed.connect(self.linkedStyles[i].axesStyle.axesColor.setColor)
                self.axesStyle.axesWidthChanged.connect(self.linkedStyles[i].axesStyle.setAxesWidth)
                self.axesStyle.backgroundColor.changed.connect(self.linkedStyles[i].axesStyle.backgroundColor.setColor)
                self.axesStyle.labelsColor.changed.connect(self.linkedStyles[i].axesStyle.labelsColor.setColor)
                self.axesStyle.labelsFont.changed.connect(self.linkedStyles[i].axesStyle.labelsFont.setFont)
                self.axesStyle.ticksColor.changed.connect(self.linkedStyles[i].axesStyle.ticksColor.setColor)
                self.axesStyle.ticksFont.changed.connect(self.linkedStyles[i].axesStyle.ticksFont.setFont)
                self.axesStyle.titleColor.changed.connect(self.linkedStyles[i].axesStyle.titleColor.setColor)
                self.axesStyle.titleFont.changed.connect(self.linkedStyles[i].axesStyle.titleFont.setFont)

    def unlinkStyles(self):
        if self.connectStyles:
            for i in range(len(self.linkedStyles)):
                self.axesStyle.axesColor.changed.disconnect(self.linkedStyles[i].axesStyle.axesColor.setColor)
                self.axesStyle.axesWidthChanged.disconnect(self.linkedStyles[i].axesStyle.setAxesWidth)
                self.axesStyle.backgroundColor.changed.disconnect(self.linkedStyles[i].axesStyle.backgroundColor.setColor)
                self.axesStyle.labelsColor.changed.disconnect(self.linkedStyles[i].axesStyle.labelsColor.setColor)
                self.axesStyle.labelsFont.changed.disconnect(self.linkedStyles[i].axesStyle.labelsFont.setFont)
                self.axesStyle.ticksColor.changed.disconnect(self.linkedStyles[i].axesStyle.ticksColor.setColor)
                self.axesStyle.ticksFont.changed.disconnect(self.linkedStyles[i].axesStyle.ticksFont.setFont)
                self.axesStyle.titleColor.changed.disconnect(self.linkedStyles[i].axesStyle.titleColor.setColor)
                self.axesStyle.titleFont.changed.disconnect(self.linkedStyles[i].axesStyle.titleFont.setFont)

    def currentCurveIndex(self):
        return self.common.currentCurveIndex

    @Slot()
    def setCurrentCurveIndex(self, index):
        self.common.currentCurveIndex = index
        self.currentCurveIndexChanged.emit()

    @Slot()
    def setNumCurves(self, numCurves):
        self.common.numCurves = numCurves

    def applyToAllCurves(self):
        return self.common.applyToAllCurves

    def setApplyToAllCurves(self, apply):
        self.common.applyToAllCurves = apply


class DispersionStyle(BaseStyle):
    def __init__(self):
        super().__init__()

        self.curveStyle = CurveStyle(self.common)
        self.curveStyle.styleChanged.connect(self.styleChanged)

        self.pointStyle = PointStyle(self.common)
        self.pointStyle.styleChanged.connect(self.styleChanged)

    @Slot()
    def applyDefaultStyle(self):
        self.curveStyle.setCommonPalette()
        self.pointStyle.setCommonStyle()
        self.styleChanged.emit()


class AbsorptionStyle(BaseStyle):
    def __init__(self):
        super().__init__()

        self.curveStyle = CurveStyle(self.common)
        self.curveStyle.styleChanged.connect(self.styleChanged)

        self.pointStyle = PointStyle(self.common)
        self.pointStyle.styleChanged.connect(self.styleChanged)

        self.legendStyle = LegendStyle()

    @Slot()
    def appendCurveStyle(self, index):
        self.curveStyle.curvePens.append(pg.mkPen(index))
        self.pointStyle.pointSymbols.append('o')
        self.pointStyle.pointSizes.append(6)

        self.common.numCurves += 1

        self.styleChanged.emit()

    @Slot()
    def removeCurveStyle(self, index):
        self.curveStyle.curvePens.pop(index)
        self.pointStyle.pointSymbols.pop(index)
        self.pointStyle.pointSizes.pop(index)

        self.common.decreaseNumCurves()

        self.styleChanged.emit()


class BandStructureStyle(BaseStyle):
    weightFactorChanged = Signal(float)

    def __init__(self):
        super().__init__()

        self.curveStyle = CurveStyle(self.common)
        self.curveStyle.styleChanged.connect(self.styleChanged)

        self.brush = pg.mkBrush('orange')

    @Slot()
    def applyDefaultStyle(self):
        self.curveStyle.setCommonPalette()

    @Slot()
    def setBrushColor(self, color):
        self.brush = pg.mkBrush(color)
        self.styleChanged.emit()
