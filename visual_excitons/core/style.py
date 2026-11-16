"""
Styles of the 2D plots: pens and symbols of the curves (for all of them and
each one), axes, legend and fill. `state()` and `setState()` turn them into
JSON-able dicts and back, to keep them between sessions and in session files.
"""

from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtGui import QColor, QFont
import pyqtgraph as pg

# Color modes of the curves (see CurveStyle.colorMode)
PALETTE, COMMON, GRADIENT = 'palette', 'common', 'gradient'

# Distinct colors, readable on light and dark backgrounds and in print
# (Matplotlib's tab10)
PALETTE_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
                  '#bcbd22', '#17becf']


def paletteColor(key):
    return QColor(PALETTE_COLORS[int(key) % len(PALETTE_COLORS)])


def gradientColor(start, end, t):
    """The color a fraction `t` of the way from `start` to `end`, in HSV (hue the shorter way round)."""
    h1, s1, v1, a1 = QColor(start).getHsvF()
    h2, s2, v2, a2 = QColor(end).getHsvF()
    h1 = h2 if h1 < 0 else h1                # greys have no hue: take the other one
    h2 = h1 if h2 < 0 else h2
    h1, h2 = max(h1, 0.0), max(h2, 0.0)
    dh = h2 - h1
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    return QColor.fromHsvF((h1 + t * dh) % 1.0, s1 + t * (s2 - s1), v1 + t * (v2 - v1), a1 + t * (a2 - a1))


PEN_STYLES = [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine,
              Qt.PenStyle.DashDotDotLine]


def penState(pen):
    style = pen.style()
    return {'color': pen.color().name(QColor.NameFormat.HexArgb),
            'width': pen.widthF(), 'style': PEN_STYLES.index(style) if style in PEN_STYLES else 0}


def setPen(pen, state):
    pen.setColor(QColor(state['color']))
    pen.setWidthF(float(state['width']))
    pen.setStyle(PEN_STYLES[int(state['style'])])


def fontState(font):
    return font.toString()


def makeFont(state):
    font = QFont()
    font.fromString(state)
    return font


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

        self.commonPen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = 1.0, color = QColor('black'))

        # How the curves get their colors, also those added later (e.g. a new
        # absorption spectrum): PALETTE (one of a set each), COMMON (the color
        # chosen for all), GRADIENT (from startColor to endColor, in order)
        self.colorMode = COMMON
        # What identifies each curve for its palette color (e.g. the Q-point of a
        # spectrum: its color stays as others come and go); None: its position
        self.paletteKeys = None
        self.startColor = QColor.fromHsv(0, 255, 255)
        self.endColor = QColor.fromHsv(300, 255, 255)

    @property
    def startHue(self):
        return max(0, self.startColor.hsvHue())

    @property
    def endHue(self):
        return max(0, self.endColor.hsvHue())

    def curveColor(self, index, count):
        """The color of curve `index` of `count` in the current color mode."""
        if self.colorMode == PALETTE:
            keys = self.paletteKeys
            return paletteColor(keys[index] if keys is not None and index < len(keys) else index)
        if self.colorMode == GRADIENT:
            return gradientColor(self.startColor, self.endColor, index / (count - 1) if count > 1 else 0.0)
        return QColor(self.commonPen.color())

    def newCurvePen(self, index, count):
        """The pen of a curve added: the width and pattern for all, the color of its color mode."""
        pen = pg.mkPen(style=self.commonPen.style(), width=self.commonPen.widthF(), color=self.curveColor(index, count))
        return pen

    def replaceColor(self, old, new):
        """
        Give the pens of color `old` (e.g. the default foreground of the previous
        theme) the color `new`, leaving the colors chosen by the user alone.
        """
        for pen in [self.commonPen] + self.curvePens:
            if pen.color().rgb() == QColor(old).rgb():
                pen.setColor(QColor(new))

    def allCurvePensEqual(self):
        return all(pen == self.curvePens[0] for pen in self.curvePens)

    def state(self):
        return {'pen': penState(self.commonPen), 'curves': [penState(pen) for pen in self.curvePens],
                'gradient': [self.startHue, self.endHue], 'colorMode': self.colorMode,
                'gradientColors': [self.startColor.name(), self.endColor.name()]}

    def setState(self, state, curves=False):
        setPen(self.commonPen, state['pen'])
        if 'gradientColors' in state:
            self.startColor, self.endColor = (QColor(color) for color in state['gradientColors'][:2])
        elif 'gradient' in state:           # saved before: hues only
            self.startColor, self.endColor = (QColor.fromHsv(int(hue), 255, 255) for hue in state['gradient'][:2])
        if state.get('colorMode') in (PALETTE, COMMON, GRADIENT):
            self.colorMode = state['colorMode']
        if curves and len(state.get('curves', [])) == len(self.curvePens):
            for pen, penState in zip(self.curvePens, state['curves']):
                setPen(pen, penState)

    def setCommonPalette(self):
        """A pen per curve, in the common width and pattern and the color of the color mode."""
        count = self.common.numCurves
        self.curvePens[:] = [self.newCurvePen(i, count) for i in range(count)]

    @Slot()
    def setGradientPalette(self):
        """Color the curves from startColor (the first) to endColor (the last)."""
        self.colorMode = GRADIENT
        count = len(self.curvePens)
        for i, pen in enumerate(self.curvePens):
            pen.setColor(self.curveColor(i, count))
        self.styleChanged.emit()

    @Slot()
    def setPaletteColors(self):
        """A color of its own for each curve, from a set of distinct colors."""
        self.colorMode = PALETTE
        count = len(self.curvePens)
        for i, pen in enumerate(self.curvePens):
            pen.setColor(self.curveColor(i, count))
        self.styleChanged.emit()

    def setGradientColors(self, start=None, end=None):
        if start is not None:
            self.startColor = QColor(start)
        if end is not None:
            self.endColor = QColor(end)
        self.setGradientPalette()

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
            self.colorMode = COMMON
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

    def state(self):
        return {'symbol': self.commonPointSymbol, 'size': self.commonPointSize,
                'symbols': list(self.pointSymbols), 'sizes': list(self.pointSizes)}

    def setState(self, state, curves=False):
        if state['symbol'] in self.symbols:
            self.commonPointSymbol = state['symbol']
        self.commonPointSize = int(state['size'])
        symbols, sizes = state.get('symbols', []), state.get('sizes', [])
        if curves and len(symbols) == len(self.pointSymbols) and len(sizes) == len(self.pointSizes):
            self.pointSymbols[:] = [symbol if symbol in self.symbols else 'o' for symbol in symbols]
            self.pointSizes[:] = [int(size) for size in sizes]

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

        self.titleColor = Color(QColor('black'))
        self.labelsColor = Color(QColor('black'))
        self.ticksColor = Color(QColor('black'))
        self.axesColor = Color(QColor('black'))
        self.backgroundColor = Color(QColor('white'))

        self.titleFont = Font(QFont())
        self.labelsFont = Font(QFont())
        self.ticksFont = Font(QFont())

        self.axesWidth = 1

    COLORS = ('titleColor', 'labelsColor', 'ticksColor', 'axesColor', 'backgroundColor')
    FONTS = ('titleFont', 'labelsFont', 'ticksFont')

    @Slot()
    def setAxesWidth(self, width):
        self.axesWidth = width
        self.axesWidthChanged.emit(self.axesWidth)

    def state(self):
        state = {name: getattr(self, name).getColor().name(QColor.NameFormat.HexArgb) for name in self.COLORS}
        state.update({name: fontState(getattr(self, name).getFont()) for name in self.FONTS})
        state['width'] = self.axesWidth
        return state

    def setState(self, state):
        for name in self.COLORS:
            if name in state:
                getattr(self, name).setColor(QColor(state[name]))
        for name in self.FONTS:
            if name in state:
                getattr(self, name).setFont(makeFont(state[name]))
        if 'width' in state:
            self.setAxesWidth(int(state['width']))


class LegendStyle(QObject):
    textColorChanged = Signal(object)
    textSizeChanged = Signal(object)
    backgroundColorChanged = Signal(object)
    borderPenChanged = Signal(object)
    offsetChanged = Signal(object)

    def __init__(self):
        super().__init__()

        self.textColor = QColor('black')
        self.textSize = 9
        self.backgroundColor = None
        self.borderPen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = 0.0, color = QColor('black'))
        self.offset = [30, 30]

        self.styles = [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine, Qt.PenStyle.DashDotDotLine]

    def state(self):
        return {'textColor': QColor(self.textColor).name(QColor.NameFormat.HexArgb), 'textSize': self.textSize,
                'backgroundColor': None if self.backgroundColor is None
                else QColor(self.backgroundColor).name(QColor.NameFormat.HexArgb),
                'border': penState(self.borderPen), 'offset': list(self.offset)}

    def setState(self, state):
        self.setTextColor(QColor(state['textColor']))
        self.setTextSize(int(state['textSize']))
        background = state.get('backgroundColor')
        self.setBackgroundColor(None if background is None else QColor(background))
        setPen(self.borderPen, state['border'])
        self.borderPenChanged.emit(self.borderPen)
        self.offset[:] = [int(value) for value in state['offset']]
        self.offsetChanged.emit(self.offset)

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
        # The lines of the curves (dispersion: interpolated, or joining the
        # points; absorption: the spectra; band structure: the edges of the fill)
        self.showLines = True

    @Slot(bool)
    def setShowLines(self, show):
        self.showLines = bool(show)
        self.styleChanged.emit()

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

    def state(self):
        """The style as a JSON-able dict, with the style of each curve."""
        state = {'axes': self.axesStyle.state(), 'curve': self.curveStyle.state(), 'lines': self.showLines}
        if hasattr(self, 'pointStyle'):
            state['point'] = self.pointStyle.state()
        return state

    def setState(self, state, curves=False):
        """
        Set a style from state(); the style of each curve too if `curves` and
        there are as many curves as when it was saved. Missing or invalid parts
        are left as they are.
        """
        if isinstance(state.get('lines'), bool):
            self.showLines = state['lines']
        for key, part in (('axes', self.axesStyle), ('curve', getattr(self, 'curveStyle', None)),
                          ('point', getattr(self, 'pointStyle', None))):
            if part is None or key not in state:
                continue
            try:
                part.setState(state[key]) if key == 'axes' else part.setState(state[key], curves)
            except (KeyError, TypeError, ValueError, IndexError):
                pass
        self.styleChanged.emit()

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
        # Each spectrum in a color of its own (that of its Q-point), until a color is chosen for all
        self.curveStyle.colorMode = PALETTE
        self.curveStyle.paletteKeys = []

        self.pointStyle = PointStyle(self.common)
        self.pointStyle.styleChanged.connect(self.styleChanged)

        self.legendStyle = LegendStyle()

    def state(self):
        return {**super().state(), 'legend': self.legendStyle.state()}

    def setState(self, state, curves=False):
        if 'legend' in state:
            try:
                self.legendStyle.setState(state['legend'])
            except (KeyError, TypeError, ValueError, IndexError):
                pass
        super().setState(state, curves)

    @Slot()
    def appendCurveStyle(self, index):
        """A new spectrum: the style for all, its color from the color mode (a gradient spread again)."""
        curves = self.curveStyle
        count = len(curves.curvePens) + 1
        curves.paletteKeys.append(int(index))      # the Q-point: its palette color
        curves.curvePens.append(curves.newCurvePen(count - 1, count))
        if curves.colorMode == GRADIENT:
            for i, pen in enumerate(curves.curvePens):
                pen.setColor(curves.curveColor(i, count))
        self.pointStyle.pointSymbols.append(self.pointStyle.commonPointSymbol)
        self.pointStyle.pointSizes.append(self.pointStyle.commonPointSize)

        self.common.numCurves += 1

        self.styleChanged.emit()

    @Slot()
    def removeCurveStyle(self, index):
        self.curveStyle.curvePens.pop(index)
        if index < len(self.curveStyle.paletteKeys):
            self.curveStyle.paletteKeys.pop(index)
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
        self.weightFactor = 1.0

    def state(self):
        return {**super().state(), 'fill': self.brush.color().name(QColor.NameFormat.HexArgb),
                'weightFactor': self.weightFactor}

    def setState(self, state, curves=False):
        if 'fill' in state:
            self.brush = pg.mkBrush(QColor(state['fill']))
        if 'weightFactor' in state:
            self.setWeightFactor(float(state['weightFactor']))
        super().setState(state, curves)

    @Slot(float)
    def setWeightFactor(self, factor):
        self.weightFactor = factor
        self.weightFactorChanged.emit(factor)

    @Slot()
    def applyDefaultStyle(self):
        self.curveStyle.setCommonPalette()

    @Slot()
    def setBrushColor(self, color):
        self.brush = pg.mkBrush(color)
        self.styleChanged.emit()
