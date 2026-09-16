import numpy as np
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter

from .exciton_wf_widget import ExcitonWfWidget
from .parameters_3d_widget import Parameters3DWidget
from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations


class Graphs3DWidget(QWidget):
    def __init__(self, options: Options, calculations: Calculations):
        QWidget.__init__(self)

        self.options = options

        self.calculations = calculations
        self.calculations.wfComputed.connect(self.plotWf)

        self.excitonWfWidget = ExcitonWfWidget()

        self.parameters3DWidget = Parameters3DWidget(options, calculations)
        self.parameters3DWidget.plotTypeChanged.connect(self.plotWfIfMissing)
        self.parameters3DWidget.plotTypeChanged.connect(self.excitonWfWidget.showItem)
        self.parameters3DWidget.isoLevelChanged.connect(self.plotWfIso)
        self.parameters3DWidget.numIsoLevelsChanged.connect(self.plotWfIsoSet)
        self.parameters3DWidget.opacityChanged.connect(self.excitonWfWidget.setOpacity)
        self.parameters3DWidget.sliceDensityChanged.connect(self.plotWfVol)
        self.parameters3DWidget.signalReplotLattice.connect(self.plotLattice)
        self.parameters3DWidget.fixedParticlePosChanged.connect(self.translateFixedParticle)
        self.parameters3DWidget.centerViewClicked.connect(self.excitonWfWidget.centerView)
        self.parameters3DWidget.viewLatticeChanged.connect(self.excitonWfWidget.viewLattice)
        self.parameters3DWidget.viewBoundariesChanged.connect(self.excitonWfWidget.viewBoundaries)

        hSplitter = QSplitter()
        hSplitter.setOrientation(Qt.Orientation.Horizontal)
        hSplitter.addWidget(self.excitonWfWidget)
        hSplitter.addWidget(self.parameters3DWidget)
        hSplitter.setStretchFactor(0, 2)
        hSplitter.setStretchFactor(1, 1)

        layout = QVBoxLayout()
        layout.addWidget(hSplitter)

        self.setLayout(layout)

    @Slot()
    def plotWf(self):
        self.excitonWfWidget.clearWfItems()

        if self.parameters3DWidget.plotType() == 0:
            self.plotWfIso()
        elif self.parameters3DWidget.plotType() == 1:
            self.plotWfIsoSet()
        elif self.parameters3DWidget.plotType() == 2:
            self.plotWfVol()

    @Slot(int)
    def plotWfIfMissing(self, index: int):
        if not self.excitonWfWidget.itemExists(index):
            if index == 0:
                self.plotWfIso()
            elif index == 1:
                self.plotWfIsoSet()
            elif index == 2:
                self.plotWfVol()

    @Slot()
    def plotWfIso(self):
        if self.calculations.probabilityDensity() is not None:
            self.excitonWfWidget.plotWfIso(self.calculations.probabilityDensity(), self.options.isoLevel(), self.calculations.tr4x4.tolist(), self.options.opacity())

    @Slot()
    def plotWfIsoSet(self):
        if self.calculations.probabilityDensity() is not None:
            self.excitonWfWidget.plotWfIsoSet(self.calculations.probabilityDensity(), self.options.numIsoLevels(), self.calculations.tr4x4.tolist(), self.options.opacity())

    @Slot()
    def plotWfVol(self):
        if self.calculations.probabilityDensity() is not None:
            self.excitonWfWidget.plotWfVol(self.calculations.probabilityDensity(), self.options.sliceDensity(), self.calculations.tr4x4.tolist())

    @Slot()
    def plotLattice(self):
        self.excitonWfWidget.clearLatticeItems()
        self.excitonWfWidget.clearAtomNamesItems()
        self.excitonWfWidget.clearLatticeBoundaryItems()

        ucell = self.calculations.unitCell()

        self.excitonWfWidget.plotBaseLatticeVectors(ucell['base_lattice_vectors'])

        supercell = self.options.supercell()

        for i in range(supercell[0]):
            for j in range(supercell[1]):
                for k in range(supercell[2]):
                    offset = ucell['base_lattice_vectors'][0] * i + ucell['base_lattice_vectors'][1] * j + ucell['base_lattice_vectors'][2] * k
                    self.excitonWfWidget.plotUnitCellBoundaries(ucell['base_lattice_vectors'], offset)
                    self.excitonWfWidget.plotUnitCellAtoms(ucell['atomic_numbers'], ucell['atomic_positions'], offset)

    @Slot()
    def translateFixedParticle(self):
        self.excitonWfWidget.translateFixedParticle(self.options.particlePositionCartesian())