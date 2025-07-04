from PySide6.QtCore import Signal, Slot, Qt
import pyqtgraph as pg


class AbsorptionWidget(pg.GraphicsLayoutWidget):
    excitonsSelected = Signal(list, bool)
    curveClicked = Signal(int)

    def __init__(self, style, parent = None):
        pg.GraphicsLayoutWidget.__init__(self, parent)

        self.absorption = self.addPlot(0, 0)

        self.title = 'Excitonic Absorption'
        self.absorption.setTitle(self.title)

        self.absorption.showAxes(True)

        self.xLabel = 'Energy'
        self.yLabel = 'Intensity'

        self.xUnits = 'eV'
        self.yUnits = 'Arb. Units'

        self.absorption.setLabel('bottom', text = self.xLabel, units = self.xUnits)
        self.absorption.setLabel('left', text = self.yLabel, units = self.yUnits)

        self.absorption.addLegend()
        self.legend = self.absorption.addLegend()

        self.excitonsLayout = self.addLayout(1, 0)

        self.excitonPlots = []

        self.ci.layout.setRowStretchFactor(0, 7)
        self.ci.layout.setRowStretchFactor(1, 1)
        self.ci.layout.setRowMaximumHeight(1, 200)

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
    def plotData(self, excAbsData, showLabels):
        self.absorption.clear()
        self.curveItems.clear()

        for plot in self.excitonPlots:
            self.excitonsLayout.removeItem(plot)

        self.excitonPlots.clear()

        if len(excAbsData) > 0:
            # Line graphs with absorption

            curvePens = self.style.curveStyle.curvePens
            pointSymbols = self.style.pointStyle.pointSymbols
            pointSizes = self.style.pointStyle.pointSizes

            for i, data in enumerate(excAbsData):
                dataItem = pg.PlotDataItem(data['energy'], data['absorption'], symbol = None, pen = curvePens[i], name = "q = %d"%(data['q']))
                dataItem.curve.setClickable(True)
                dataItem.sigClicked.connect(self.curveSelected)

                self.absorption.addItem(dataItem)
                self.curveItems.append(dataItem)

                scatterPlotItem = pg.ScatterPlotItem(x = data['brightExcEnergy'], y = data['brightExcAbsorption'], data = data['data'], symbol = pointSymbols[i], size = pointSizes[i])
                scatterPlotItem.sigClicked.connect(self.getSelectedExcitons)
                self.absorption.addItem(scatterPlotItem)

                if showLabels:
                    for i in range(len(data['brightExcIndices'])):
                        textItem = pg.TextItem("(%d, %.3f)"%(data['brightExcIndices'][i], data['brightExcIntensities'][i]), anchor = (0.5, 1.0))
                        textItem.setPos(data['brightExcEnergy'][i], data['brightExcAbsorption'][i])
                        self.absorption.addItem(textItem)

            # Bar graphs with excitons
            for i, data in enumerate(excAbsData):
                row = i + 1
                plot = self.excitonsLayout.addPlot(row, 0)
                plot.setXLink(self.absorption)
                plot.showAxes(False)
                plot.hideButtons()
                plot.addItem(pg.BarGraphItem(x = data['brightExcEnergy'], width = 0.00001, height = 1.0, pen = curvePens[i].color(), brush = curvePens[i].color()))
                plot.addItem(pg.BarGraphItem(x = data['darkExcEnergy'], width = 0.00001, height = 1.0, pen = 'gray', brush = 'gray'))
                self.excitonPlots.append(plot)
        else:
            self.absorption.setRange(xRange = (0.0, 1.0), yRange = (0.0, 1.0), disableAutoRange = False)

    @Slot()
    def clearData(self):
        self.absorption.clear()
        self.absorption.setRange(xRange = (0.0, 1.0), yRange = (0.0, 1.0), disableAutoRange = False)

        for plot in self.excitonPlots:
            self.excitonsLayout.removeItem(plot)

        self.excitonPlots.clear()

    @Slot()
    def getSelectedExcitons(self, item, points, ev):
        self.excitonsSelected.emit(points, True)

    @Slot()
    def curveSelected(self, item, ev):
        self.curveClicked.emit(self.curveItems.index(item))

    @Slot()
    def setAxesColor(self, color):
        pen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = self.style.axesStyle.axesWidth, color = color)

        self.absorption.getAxis('bottom').setPen(pen)
        self.absorption.getAxis('left').setPen(pen)
        self.absorption.getAxis('top').setPen(pen)
        self.absorption.getAxis('right').setPen(pen)

        self.setLabelsColor(self.style.axesStyle.labelsColor.color)

    @Slot()
    def setAxesWidth(self, width):
        pen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = width, color = self.style.axesStyle.axesColor.color)

        self.absorption.getAxis('bottom').setPen(pen)
        self.absorption.getAxis('left').setPen(pen)
        self.absorption.getAxis('top').setPen(pen)
        self.absorption.getAxis('right').setPen(pen)

        self.setLabelsColor(self.style.axesStyle.labelsColor.color)

    @Slot()
    def setTicksColor(self, color):
        pen = pg.mkPen(style = Qt.PenStyle.SolidLine, width = 1.0, color = color)

        self.absorption.getAxis('bottom').setTextPen(pen)
        self.absorption.getAxis('left').setTextPen(pen)
        self.absorption.getAxis('top').setTextPen(pen)
        self.absorption.getAxis('right').setTextPen(pen)

        self.setLabelsColor(self.style.axesStyle.labelsColor.color)

    @Slot()
    def setTitleColor(self, color):
        self.absorption.titleLabel.setText(self.title, color = color)

    @Slot()
    def setLabelsColor(self, color):
        labelStyle = {'color': color.name()}

        self.absorption.setLabel('bottom', text = self.xLabel, units = self.xUnits, **labelStyle)
        self.absorption.setLabel('left', text = self.yLabel, units = self.yUnits, **labelStyle)

    @Slot()
    def setTicksFont(self, font):
        self.absorption.getAxis('bottom').setTickFont(font)
        self.absorption.getAxis('left').setTickFont(font)

    @Slot()
    def setTitleFont(self, font):
        self.absorption.titleLabel.item.setFont(font)
        self.absorption.setTitle(self.title, size = "{}pt".format(font.pointSize()), bold = font.bold(), italic = font.italic())

    @Slot()
    def setLabelsFont(self, font):
        self.absorption.getAxis('bottom').label.setFont(font)
        self.absorption.getAxis('left').label.setFont(font)

        self.absorption.getAxis('bottom').showLabel(True)
        self.absorption.getAxis('left').showLabel(True)

    @Slot()
    def setBackgroundColor(self, color):
        self.setBackground(color)

    @Slot()
    def setLegendTextColor(self, color):
        self.legend.setLabelTextColor(color)

    @Slot()
    def setLegendTextSize(self, size):
        self.legend.setLabelTextSize("{}pt".format(size))

    @Slot()
    def setLegendBackgroundColor(self, color):
        self.legend.setBrush(color)

    @Slot()
    def setLegendBorderPen(self, pen):
        self.legend.setPen(pen)

    @Slot()
    def setLegendOffset(self, offset):
        self.legend.setOffset(offset)
