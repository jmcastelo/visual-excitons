from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget
import pyqtgraph.opengl as gl
import numpy as np

from .exciton_wf_widget import ExcitonWfWidget
from .parameters_3d_widget import Parameters3DWidget
from .axes_3d_widget import AxisGizmo
from .inspector import pageLayout
from .persistence import PersistentState
from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.bonds import findBonds, halfBonds
from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR

# Color of the bonds in uniform coloring mode
BOND_GREY = (0.6, 0.6, 0.6)


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
        self.parameters3DWidget.isoOpacityChanged.connect(self.excitonWfWidget.setIsoOpacity)
        self.parameters3DWidget.isoSetOpacityChanged.connect(self.excitonWfWidget.setIsoSetOpacity)
        self.parameters3DWidget.isoSetStyleChanged.connect(self.excitonWfWidget.setIsoSetStyle)
        self.parameters3DWidget.colormapChanged.connect(self.setColormap)
        self.parameters3DWidget.sliceDensityChanged.connect(self.plotWfVol)
        self.parameters3DWidget.volumeParametersChanged.connect(self.plotWfVol)
        self.parameters3DWidget.signalReplotLattice.connect(self.plotLattice)
        self.parameters3DWidget.fixedParticlePosChanged.connect(self.translateFixedParticle)
        self.parameters3DWidget.centerViewClicked.connect(self.excitonWfWidget.centerView)
        self.parameters3DWidget.viewDirChanged.connect(self.excitonWfWidget.setViewDirection)
        self.parameters3DWidget.projectionChanged.connect(self.excitonWfWidget.changeProjection)
        self.parameters3DWidget.viewLatticeChanged.connect(self.excitonWfWidget.viewLattice)
        self.parameters3DWidget.viewAtomNamesChanged.connect(self.excitonWfWidget.viewAtomNames)
        self.parameters3DWidget.viewBoundariesChanged.connect(self.excitonWfWidget.viewBoundaries)
        self.parameters3DWidget.viewBondsChanged.connect(self.excitonWfWidget.viewBonds)

        gizmo = AxisGizmo(target=self.excitonWfWidget, size=200)
        self.excitonWfWidget.attach_gizmo(gizmo, 10)

        self.parameters3DWidget.showCartesianAxesChanged.connect(gizmo.setShowCartesian)
        self.parameters3DWidget.showLatticeVectorsChanged.connect(gizmo.setShowLattice)
        self.parameters3DWidget.showReciprocalVectorsChanged.connect(self.excitonWfWidget.setShowReciprocalVectors)
        self.parameters3DWidget.showAxisLabelsChanged.connect(gizmo.setShowLabels)
        self.parameters3DWidget.showCellInfoChanged.connect(self.excitonWfWidget.setShowCellInfo)

        # Initial view from the view widgets' default state
        self.parameters3DWidget.applyView()

        self.inspector = self.parameters3DWidget
        layout = pageLayout(self.excitonWfWidget, self.inspector)
        self.setLayout(layout)

        # Size of the side panel, kept between sessions
        self.persistence = PersistentState()
        self.persistence.remember('page', layout.itemAt(0).widget())

    @Slot(bool)
    def setDarkTheme(self, dark: bool):
        self.excitonWfWidget.setDarkTheme(dark)

    @Slot(bool)
    def onDatasetChanged(self, found: bool):
        """Drop the wave function of the previous dataset and draw the new lattice."""
        self.excitonWfWidget.clearWfItems()
        if found:
            self.plotLattice()
            self.excitonWfWidget.centerView()

    @Slot(object)
    def setColormap(self, colormap):
        """Recolor the density: the shown plot now, the others when shown (see plotWfIfMissing)."""
        self.excitonWfWidget.colormap = colormap
        if self.calculations.probabilityDensity() is not None:
            self.plotWf()

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
            self.excitonWfWidget.plotWfIso(self.calculations.probabilityDensity(), self.options.isoLevel(), self.calculations.tr4x4.tolist(), self.options.isoOpacity())

    @Slot()
    def plotWfIsoSet(self):
        if self.calculations.probabilityDensity() is not None:
            self.excitonWfWidget.plotWfIsoSet(self.calculations.probabilityDensity(), self.options.numIsoLevels(), self.calculations.tr4x4.tolist(), self.options.isoSetOpacity())

    @Slot()
    def plotWfVol(self):
        if self.calculations.probabilityDensity() is not None:
            self.excitonWfWidget.plotWfVol(self.calculations.probabilityDensity(), self.options.sliceDensity(), self.calculations.tr4x4.tolist(),
                                           self.options.volumeOpacity(), self.options.volumeContrast())

    @Slot()
    def plotLattice(self):
        self.excitonWfWidget.clearLatticeItems()
        self.excitonWfWidget.clearAtomNamesItems()
        self.excitonWfWidget.clearLatticeBoundaryItems()

        # Nothing to draw before a SAVE database is loaded
        if not self.options.hasCell():
            return

        ucell = self.calculations.unitCell()

        self.excitonWfWidget.plotBaseLatticeVectors(ucell['base_lattice_vectors'])

        supercell = self.options.supercell()

        for i in range(supercell[0]):
            for j in range(supercell[1]):
                for k in range(supercell[2]):
                    offset = ucell['base_lattice_vectors'][0] * i + ucell['base_lattice_vectors'][1] * j + ucell['base_lattice_vectors'][2] * k
                    self.excitonWfWidget.plotUnitCellBoundaries(ucell['base_lattice_vectors'], offset)
                    self.excitonWfWidget.plotUnitCellAtoms(ucell['atomic_numbers'], ucell['atomic_positions'], offset,
                                                           self.options.atomScale())

        self.plotBonds(ucell, supercell)

    def plotBonds(self, ucell, supercell):
        lattice = ucell['base_lattice_vectors']
        numbers = np.asarray(ucell['atomic_numbers'], dtype=int)
        positions = np.asarray(ucell['atomic_positions'], dtype=float)[:len(numbers)]

        bonds = findBonds(lattice, positions, numbers, self.options.bondTolerance())
        starts, ends, atoms = halfBonds(lattice, positions, bonds, supercell)
        uniformColor = BOND_GREY if self.options.bondColoring() == 1 else None
        self.excitonWfWidget.plotBonds(starts, ends, numbers[atoms], self.options.bondRadius() * ANGSTROM_TO_BOHR,
                                       uniformColor)

    @Slot()
    def translateFixedParticle(self):
        if not self.options.hasCell():
            return
        self.excitonWfWidget.translateFixedParticle(self.options.particlePositionCartesian())
