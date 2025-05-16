# This Python file uses the following encoding: utf-8
from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
from options import Options
from style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from calculations import Calculations
from options_widget import OptionsWidget
from dispersion_widget import DispersionWidget
from band_structure_widget import BandStructureWidget
from absorption_widget import AbsorptionWidget
from graphs_widget import GraphsWidget
from style_widget import StyleDialog

class MainWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        self.options = Options()

        self.calculations = Calculations(self.options)

        # Styles

        self.dispersionStyle = DispersionStyle()
        self.absorptionStyle = AbsorptionStyle()
        self.bandStructureStyle = BandStructureStyle()

        self.dispersionStyle.setLinkedStyles([self.absorptionStyle, self.bandStructureStyle])
        self.absorptionStyle.setLinkedStyles([self.dispersionStyle, self.bandStructureStyle])
        self.bandStructureStyle.setLinkedStyles([self.dispersionStyle, self.absorptionStyle])

        self.dispersionStyle.styleChanged.connect(self.calculations.emitExcitonDispersionReady)
        self.absorptionStyle.styleChanged.connect(self.calculations.emitExcitonAbsorption)
        self.bandStructureStyle.styleChanged.connect(self.calculations.emitExcitonBandStructure)

        self.calculations.excitonDispersionNumCurvesChanged.connect(self.dispersionStyle.setNumCurves)
        self.calculations.excitonDispersionInit.connect(self.dispersionStyle.applyDefaultStyle)

        self.calculations.excitonAbsorptionCurveAppended.connect(self.absorptionStyle.appendCurveStyle)
        self.calculations.excitonAbsorptionCurveRemoved.connect(self.absorptionStyle.removeCurveStyle)

        self.calculations.excitonBandStructureNumCurvesChanged.connect(self.bandStructureStyle.setNumCurves)
        self.calculations.excitonBandStructureInit.connect(self.bandStructureStyle.applyDefaultStyle)

        # Options widget
        self.optionsWidget = OptionsWidget(self.options)

        # Graphs widget
        self.graphsWidget = GraphsWidget(self.options, self.calculations, self.dispersionStyle, self.absorptionStyle, self.bandStructureStyle)

        self.tabWidget = QTabWidget()
        self.tabWidget.addTab(self.optionsWidget, 'Options')
        self.tabWidget.addTab(self.graphsWidget, 'Graphs')

        self.options.setSaveDir('/home/jmcastelo/users/jorge/calcs/save')
        self.options.setDiagoDir('/home/jmcastelo/users/jorge/calcs/diagos')
        #self.options.setSaveDir("/home/jmcastelo/yambopy-tutorial/run_calculations/bse/SAVE")
        #self.options.setDiagoDir("/home/jmcastelo/yambopy-tutorial/run_calculations/bse/yambo")

        mainVLayout = QVBoxLayout()
        mainVLayout.addWidget(self.tabWidget)
        self.setLayout(mainVLayout)

        # Style dialog

        self.styleDialog = StyleDialog(self.dispersionStyle, self.absorptionStyle, self.bandStructureStyle)

        self.graphsWidget.parametersWidget.toggleStyleDialog.connect(self.styleDialog.toggleVisibility)

        self.dispersionStyle.currentCurveIndexChanged.connect(self.styleDialog.dispersionStyleWidget.setWidgetsValues)
        self.absorptionStyle.currentCurveIndexChanged.connect(self.styleDialog.absorptionStyleWidget.setWidgetsValues)
        self.bandStructureStyle.currentCurveIndexChanged.connect(self.styleDialog.bandStructureStyleWidget.setWidgetsValues)

        self.dispersionStyle.styleChanged.connect(self.styleDialog.dispersionStyleWidget.setWidgetsValues)
        #self.bandStructureStyle.styleChanged.connect(self.styleDialog.bandStructureStyleWidget.setWidgetsValues)

        self.setWindowTitle('Visual Excitons');

    def closeEvent(self, event):
        self.styleDialog.close()
        event.accept()
