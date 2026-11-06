from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QSplitter

from .dispersion_widget import DispersionWidget
from .band_structure_widget import BandStructureWidget
from .absorption_widget import AbsorptionWidget
from .parameters_widget import ParametersWidget
from .inspector import pageLayout
from .persistence import PersistentState
from .theme import PLOT_COLORS


class GraphsWidget(QWidget):
    def __init__(self, options, calculations, dispersionStyle, absorptionStyle, bandStructureStyle):
        QWidget.__init__(self)

        self.calculations = calculations
        self.styles = (dispersionStyle, absorptionStyle, bandStructureStyle)
        # Default color of the curves: black (the light theme's foreground)
        self.foreground = PLOT_COLORS[False]['foreground']

        # Dispersion widget

        dispersionWidget = DispersionWidget(dispersionStyle)

        options.numQPointsChanged.connect(dispersionWidget.setSingleQPoint)

        calculations.qPathReady.connect(dispersionWidget.setXAxis)
        calculations.excitonDispersionRange.connect(dispersionWidget.setXYRange)
        calculations.excitonDispersionReady.connect(dispersionWidget.plotData)

        dispersionWidget.qPointSelected.connect(calculations.computeQPointAbsorptionSpectrum)
        dispersionWidget.qPointSelected.connect(calculations.getExcitonBandStructure)
        dispersionWidget.qPointSelected.connect(calculations.selectDispersionExciton)
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
        absorptionWidget.excitonsSelected.connect(calculations.selectExciton)
        absorptionWidget.curveClicked.connect(absorptionStyle.setCurrentCurveIndex)

        absorptionStyle.legendStyle.textColorChanged.connect(absorptionWidget.setLegendTextColor)
        absorptionStyle.legendStyle.textSizeChanged.connect(absorptionWidget.setLegendTextSize)
        absorptionStyle.legendStyle.backgroundColorChanged.connect(absorptionWidget.setLegendBackgroundColor)
        absorptionStyle.legendStyle.borderPenChanged.connect(absorptionWidget.setLegendBorderPen)
        absorptionStyle.legendStyle.offsetChanged.connect(absorptionWidget.setLegendOffset)

        # Parameters widget

        self.parametersWidget = ParametersWidget(options, calculations, dispersionStyle, absorptionStyle, bandStructureStyle)
        self.parametersWidget.calculateDispersionButton.clicked.connect(calculations.getExcitonDispersion)
        self.parametersWidget.showLabelsCheckBox.toggled.connect(calculations.toggleExcitonLabelsVisibility)
        self.inspector = self.parametersWidget

        # Ring around the selected exciton, kept when the plots are redrawn
        # (connected after the plots, so it is placed on the new data)
        self.dispersionWidget = dispersionWidget
        self.absorptionWidget = absorptionWidget
        for signal in (calculations.excitonSelected, calculations.excitonDispersionReady,
                       calculations.excitonAbsorptionReady, calculations.excitonAbsorptionClear):
            signal.connect(self.updateHighlights)
        self.parametersWidget.absorptionParametersChanged.connect(calculations.recomputeAbsorptionSpectra)

        # Splitters

        vSplitter = QSplitter()
        vSplitter.setOrientation(Qt.Orientation.Vertical)
        vSplitter.addWidget(dispersionWidget)
        vSplitter.addWidget(bandStructureWidget)

        hSplitter = QSplitter()
        hSplitter.setOrientation(Qt.Orientation.Horizontal)
        hSplitter.addWidget(vSplitter)
        hSplitter.addWidget(absorptionWidget)

        layout = pageLayout(hSplitter, self.inspector)
        self.setLayout(layout)

        # Sizes of the plots and the side panel, kept between sessions
        self.persistence = PersistentState()
        for key, splitter in (('page', layout.itemAt(0).widget()), ('plots', hSplitter), ('leftPlots', vSplitter)):
            self.persistence.remember(key, splitter)

    @Slot()
    def updateHighlights(self, *args):
        positions = self.calculations.selectedExcitonPositions()
        self.dispersionWidget.setHighlight(positions['dispersion'])
        self.absorptionWidget.setHighlight(positions['absorption'])

    @Slot(bool)
    def setDarkTheme(self, dark: bool):
        """Plot colors for a dark or light theme (they can still be changed under Appearance)."""
        colors = PLOT_COLORS[dark]
        foreground, background = colors['foreground'], colors['background']
        for style in self.styles:
            axes = style.axesStyle
            for color in (axes.titleColor, axes.labelsColor, axes.ticksColor, axes.axesColor):
                color.setColor(foreground)
            axes.backgroundColor.setColor(background)
        self.styles[1].legendStyle.setTextColor(foreground)
        # Curves still in the default color follow the theme
        for style in self.styles:
            style.curveStyle.replaceColor(QColor('black'), foreground)
            style.curveStyle.replaceColor(self.foreground, foreground)
        self.foreground = foreground
        # Replot, for the items drawn in the foreground color
        if self.calculations.dispPoints:
            self.calculations.emitExcitonDispersionReady()
        if self.calculations.excAbsData:
            self.calculations.emitExcitonAbsorption()
