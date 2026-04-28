from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout
import pyqtgraph as pg

from visual_excitons.core.options import Options
from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from visual_excitons.core.calculations import Calculations
from .options_widget import OptionsWidget
from .graphs_widget import GraphsWidget
from .graphs_3d_widget import Graphs3DWidget

class MainWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        self.options = Options()

        self.calculations = Calculations(self.options)

        # Styles

        pg.setConfigOption('foreground', 'k')
        pg.setConfigOption('background', 'w')

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

        # 2D Graphs widget

        self.graphsWidget = GraphsWidget(self.options, self.calculations, self.dispersionStyle, self.absorptionStyle, self.bandStructureStyle)

        # 3D Graphs widget

        self.graphs3dWidget = Graphs3DWidget(self.options, self.calculations)

        self.tabWidget = QTabWidget()
        self.tabWidget.addTab(self.optionsWidget, 'Options')
        self.tabWidget.addTab(self.graphsWidget, '2D Graphs')
        self.tabWidget.addTab(self.graphs3dWidget, '3D Graphs')

        # self.options.setSaveDir('./data/BiI3_8x8x8/save')
        # self.options.setDiagoDir('./data/BiI3_8x8x8/diagos')
        # self.options.setQPDir('./data/BiI3_8x8x8/qp')

        # self.options.setSaveDir('./data/Bi2S3/save')
        # self.options.setDiagoDir('./data/Bi2S3/diagos')
        # self.options.setQPDir('./data/Bi2S3/gw')

        # self.options.setSaveDir('./data/test/save')
        # self.options.setDiagoDir('./data/test/diagos')

        # self.options.setSaveDir('./data/BiI3_ML_18x18x1/save')
        # self.options.setDiagoDir('./data/BiI3_ML_18x18x1/diagos')
        # self.options.setQPDir('./data/BiI3_ML_18x18x1/qp')

        self.options.setSaveDir('./data/BiI3_Bulk_8x8x8/save')
        self.options.setDiagoDir('./data/BiI3_Bulk_8x8x8/diagos')
        self.options.setQPDir('./data/BiI3_Bulk_8x8x8/qp')

        mainVLayout = QVBoxLayout()
        mainVLayout.addWidget(self.tabWidget)
        self.setLayout(mainVLayout)

        self.setWindowTitle('Visual Excitons')

        self.graphs3dWidget.plotLattice()