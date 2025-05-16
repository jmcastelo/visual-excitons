# This Python file uses the following encoding: utf-8
from PySide6.QtCore import Signal, Slot, Qt
import pyqtgraph as pg


class DispersionWidget(pg.PlotWidget):
    qPointSelected = Signal(list, bool)
    curveClicked = Signal(int)

    def __init__(self, style, parent = None):
        pg.PlotWidget.__init__(self, parent)

        self.title = 'Excitonic Dispersion'
        self.setTitle(self.title)

        self.showAxes(True)

        xAxis = pg.AxisItem('bottom')
        yAxis = pg.AxisItem('left')
        x2Axis = pg.AxisItem('top', showValues = False, maxTickLength = 0)
        y2Axis = pg.AxisItem('right', showValues = False)

        self.setAxisItems({'bottom': xAxis, 'left': yAxis, 'top': x2Axis, 'right': y2Axis})

        self.xLabel = 'Q-Path'
        self.yLabel = 'Energy'

        self.xUnits = None
        self.yUnits = 'eV'

        self.setLabel('bottom', text = self.xLabel, units = self.xUnits)
        self.setLabel('left', text = self.yLabel, units = self.yUnits)

        self.singleQPoint = False

        self.style = style

        self.style.axesStyle.titleColor.changed.connect(self.setTitleColor)
        self.style.axesStyle.labelsColor.changed.connect(self.setLabelsColor)
        self.style.axesStyle.ticksColor.changed.connect(self.setTicksColor)
        self.style.axesStyle.axesColor.changed.connect(self.setAxesColor)
        self.style.axesStyle.backgroundColor.changed.connect(self.setBackgroundColor)

        self.style.axesStyle.titleFont.changed.connect(self.setTitleFont)
        self.style.axesStyle.labelsFont.changed.connect(self.setLabelsFont)
        self.style.axesStyle.ticksFont.changed.connect(self.setTicksFont)

        self.style.axesStyle.axesWidthChanged.connect(self.setAxesWidth)

        self.curveItems = []

    @Slot()
    def plotData(self, points, pointsData, xInter, yInter):
        self.clear()
        self.curveItems.clear()

        curvePens = self.style.curveStyle.curvePens
        pointSymbols = self.style.pointStyle.pointSymbols
        pointSizes = self.style.pointStyle.pointSizes

        for i in range(len(yInter)):
            dataItem = pg.PlotDataItem(xInter, yInter[i], pen = curvePens[i], symbol = None)
            dataItem.curve.setClickable(True)
            dataItem.sigClicked.connect(self.curveSelected)

            self.addItem(dataItem)
            self.curveItems.append(dataItem)

        if self.singleQPoint:
            for i, y in enumerate(np.array(points)[:, 1]):
                line = pg.InfiniteLine(pos = y, angle = 0, movable = False, pen = 'w')
                self.addItem(line)

        for i in range(len(points)):
            scatterPlotItem = pg.ScatterPlotItem(pos = points[i], data = pointsData[i], symbol = pointSymbols[i], pxMode = True, size = pointSizes[i])
            scatterPlotItem.sigClicked.connect(self.getSelectedQPoints)
            self.addItem(scatterPlotItem)

    @Slot()
    def getSelectedQPoints(self, item, points, ev):
        self.qPointSelected.emit(points, ev.modifiers() == Qt.ControlModifier)

    @Slot()
    def curveSelected(self, item, ev):
        self.curveClicked.emit(self.curveItems.index(item))

    @Slot()
    def setSingleQPoint(self, nQPoints):
        self.singleQPoint = nQPoints == 1

    @Slot()
    def setXYRange(self, xRange, yRange):
        self.setRange(xRange = xRange, yRange = yRange, disableAutoRange = False)

    @Slot()
    def setXAxis(self, x, labels):
        if not self.singleQPoint:
            self.getAxis('bottom').setTicks([list(zip(x, labels))])
            self.getAxis('bottom').setGrid(128)
        else:
            self.getAxis('bottom').setTicks([[(0.0, 'Gamma')]])

    @Slot()
    def setAxesColor(self, color):
        pen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = self.style.axesStyle.axesWidth, color = color)

        self.getAxis('bottom').setPen(pen)
        self.getAxis('left').setPen(pen)
        self.getAxis('top').setPen(pen)
        self.getAxis('right').setPen(pen)

        self.setLabelsColor(self.style.axesStyle.labelsColor.color)

    @Slot()
    def setAxesWidth(self, width):
        pen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = width, color = self.style.axesStyle.axesColor.color)

        self.getAxis('bottom').setPen(pen)
        self.getAxis('left').setPen(pen)
        self.getAxis('top').setPen(pen)
        self.getAxis('right').setPen(pen)

        self.setLabelsColor(self.style.axesStyle.labelsColor.color)

    @Slot()
    def setTicksColor(self, color):
        pen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = 1.0, color = color)

        self.getAxis('bottom').setTextPen(pen)
        self.getAxis('left').setTextPen(pen)
        self.getAxis('top').setTextPen(pen)
        self.getAxis('right').setTextPen(pen)

        self.setLabelsColor(self.style.axesStyle.labelsColor.color)

    @Slot()
    def setTitleColor(self, color):
        self.getPlotItem().titleLabel.setText(self.title, color = color)

    @Slot()
    def setLabelsColor(self, color):
        labelStyle = {'color': color.name()}

        self.setLabel('bottom', text = self.xLabel, units = self.xUnits, **labelStyle)
        self.setLabel('left', text = self.yLabel, units = self.yUnits, **labelStyle)

    @Slot()
    def setTicksFont(self, font):
        self.getAxis('bottom').setTickFont(font)
        self.getAxis('left').setTickFont(font)

    @Slot()
    def setTitleFont(self, font):
        self.getPlotItem().titleLabel.item.setFont(font)
        self.setTitle(self.title, size = "{}pt".format(font.pointSize()), bold = font.bold(), italic = font.italic())

    @Slot()
    def setLabelsFont(self, font):
        self.getAxis('bottom').label.setFont(font)
        self.getAxis('left').label.setFont(font)

        self.getAxis('bottom').showLabel(True)
        self.getAxis('left').showLabel(True)

    @Slot()
    def setBackgroundColor(self, color):
        self.setBackground(color)
