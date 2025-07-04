from PySide6.QtCore import Signal, Slot, Qt
import pyqtgraph as pg


class BandStructureWidget(pg.PlotWidget):
    curveClicked = Signal(int)

    def __init__(self, style, parent = None):
        pg.PlotWidget.__init__(self, parent)

        self.title = 'Excitonic Band Structure'
        self.setTitle(self.title)

        self.showAxes(True)

        self.xLabel = 'K-Path'
        self.yLabel = 'Energy'

        self.xUnits = None
        self.yUnits = 'eV'

        self.setLabel('bottom', text = self.xLabel, units = self.xUnits)
        self.setLabel('left', text = self.yLabel, units = self.yUnits)

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

        self.dataItemHighs = []
        self.dataItemLows = []

    @Slot()
    def plotData(self, x, y, w):
        self.clear()
        self.dataItemHighs.clear()
        self.dataItemLows.clear()

        yMin = []
        yMax = []

        curvePens = self.style.curveStyle.curvePens

        for i in range(len(w)):
            dataItemHigh = pg.PlotDataItem(x, y[i] + w[i], pen = curvePens[i], symbol = None)
            dataItemHigh.curve.setClickable(True)
            dataItemHigh.sigClicked.connect(self.curveSelected)

            dataItemLow = pg.PlotDataItem(x, y[i] - w[i], pen = curvePens[i], symbol = None)
            dataItemLow.curve.setClickable(True)
            dataItemLow.sigClicked.connect(self.curveSelected)

            fillBetweenItem = pg.FillBetweenItem(curve1 = dataItemHigh, curve2 = dataItemLow, pen = None, brush = self.style.brush)

            self.addItem(fillBetweenItem)
            self.addItem(dataItemHigh)
            self.addItem(dataItemLow)

            self.dataItemHighs.append(dataItemHigh)
            self.dataItemLows.append(dataItemLow)

            yMin.append(min(y[i]))
            yMax.append(max(y[i]))

    @Slot()
    def curveSelected(self, item, ev):
        if item in self.dataItemHighs:
            self.curveClicked.emit(self.dataItemHighs.index(item))
        elif item in self.dataItemLows:
            self.curveClicked.emit(self.dataItemLows.index(item))

    @Slot()
    def clearData(self):
        self.clear()
        self.setRange(xRange = (self.xMin, self.xMax), yRange = (-1.0, -1.0), disableAutoRange = False)

    @Slot()
    def setXAxis(self, x, labels):
        xAxis = pg.AxisItem('bottom', text = 'K-Path')
        xAxis.setTicks([list(zip(x, labels))])
        xAxis.setGrid(128)

        self.setAxisItems({'bottom': xAxis})

        self.xMin = min(x)
        self.xMax = max(x)

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
