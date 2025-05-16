# This Python file uses the following encoding: utf-8
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QSplitter
from dispersion_widget import DispersionWidget
from band_structure_widget import BandStructureWidget
from absorption_widget import AbsorptionWidget
from parameters_widget import ParametersWidget


class GraphsWidget(QWidget):
    def __init__(self, options, calculations, dispersionStyle, absorptionStyle, bandStructureStyle):
        QWidget.__init__(self)

        # Dispersion widget

        dispersionWidget = DispersionWidget(dispersionStyle)

        options.numQPointsChanged.connect(dispersionWidget.setSingleQPoint)

        calculations.qPathReady.connect(dispersionWidget.setXAxis)
        calculations.excitonDispersionRange.connect(dispersionWidget.setXYRange)
        calculations.excitonDispersionReady.connect(dispersionWidget.plotData)

        dispersionWidget.qPointSelected.connect(calculations.computeQPointAbsorptionSpectrum)
        dispersionWidget.qPointSelected.connect(calculations.getExcitonBandStructure)
        dispersionWidget.curveClicked.connect(dispersionStyle.setCurrentCurveIndex)

        # Band structure widget

        bandStructureWidget = BandStructureWidget(bandStructureStyle)

        calculations.qPathReady.connect(bandStructureWidget.setXAxis)
        calculations.excitonBandStructureReady.connect(bandStructureWidget.plotData)
        calculations.excitonBandStructureClear.connect(bandStructureWidget.clearData)

        bandStructureWidget.curveClicked.connect(bandStructureStyle.setCurrentCurveIndex)

        bandStructureStyle.weightFactorChanged.connect(calculations.setWeightFactor)

        # Absorption widget

        absorptionWidget = AbsorptionWidget(absorptionStyle)

        calculations.excitonAbsorptionReady.connect(absorptionWidget.plotData)
        calculations.excitonAbsorptionClear.connect(absorptionWidget.clearData)

        absorptionWidget.excitonsSelected.connect(calculations.getExcitonBandStructure)
        absorptionWidget.curveClicked.connect(absorptionStyle.setCurrentCurveIndex)

        absorptionStyle.legendStyle.textColorChanged.connect(absorptionWidget.setLegendTextColor)
        absorptionStyle.legendStyle.textSizeChanged.connect(absorptionWidget.setLegendTextSize)
        absorptionStyle.legendStyle.backgroundColorChanged.connect(absorptionWidget.setLegendBackgroundColor)
        absorptionStyle.legendStyle.borderPenChanged.connect(absorptionWidget.setLegendBorderPen)
        absorptionStyle.legendStyle.offsetChanged.connect(absorptionWidget.setLegendOffset)

        # Parameters widget

        self.parametersWidget = ParametersWidget(options)
        self.parametersWidget.calculateDispersionButton.clicked.connect(calculations.getExcitonDispersion)
        self.parametersWidget.showLabelsButton.clicked.connect(calculations.toggleExcitonLabelsVisibility)
        self.parametersWidget.absorptionParametersChanged.connect(calculations.recomputeAbsorptionSpectra)

        # Splitters

        vSplitter = QSplitter()
        vSplitter.setOrientation(Qt.Vertical)
        vSplitter.addWidget(dispersionWidget)
        vSplitter.addWidget(bandStructureWidget)

        hSplitter = QSplitter()
        hSplitter.setOrientation(Qt.Horizontal)
        hSplitter.addWidget(vSplitter)
        hSplitter.addWidget(absorptionWidget)

        v2Splitter = QSplitter()
        v2Splitter.setOrientation(Qt.Vertical)
        v2Splitter.addWidget(hSplitter)
        v2Splitter.addWidget(self.parametersWidget)
        v2Splitter.setStretchFactor(0, 2)
        v2Splitter.setStretchFactor(1, 1)

        # Layout

        vLayout = QVBoxLayout()
        vLayout.addWidget(v2Splitter)
        self.setLayout(vLayout)
