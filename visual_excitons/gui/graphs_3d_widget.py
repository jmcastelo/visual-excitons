from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QSplitter
import pyqtgraph.opengl as gl
import numpy as np

from .exciton_wf_widget import ExcitonWfWidget
from .parameters_3d_widget import Parameters3DWidget
from .axes_3d_widget import AxisGizmo
from .inspector import pageLayout
from .analysis_widget import AnalysisWidget
from visual_excitons.core.analysis import (planeCut, atomsNearPlane, radialDistribution, planeSupercellPolygon,
                                           upsampleDensity)
from visual_excitons.core.tasks import TaskContext
from .wf_geometry import isoMesh, isoSetMesh, volumeColors

# Below this many grid points (times surfaces), plots are prepared inline:
# fast enough not to show (e.g. while dragging the iso level slider)
INLINE_DISPLAY_WORK = 3_000_000
from .persistence import PersistentState, DATASET
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
        # Display upsampling (see displayDensity), cleared with each new wave function
        self.smoothing = 1
        self.displayCache = {}
        self.displayRequest = None
        self.calculations.wfComputed.connect(self.displayCache.clear)
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
        self.parameters3DWidget.smoothingChanged.connect(self.setSmoothing)
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

        # Analysis panel, below the 3D view
        self.analysisWidget = AnalysisWidget()
        self.analysisWidget.setVisible(False)
        self.radialResult = None   # of the current wave function, computed when first shown
        self.calculations.wfComputed.connect(self.onWfComputedForAnalysis)
        self.parameters3DWidget.analysisChanged.connect(self.updateAnalysis)
        self.parameters3DWidget.planeFromViewRequested.connect(self.setPlaneFromView)
        self.parameters3DWidget.colormapChanged.connect(self.analysisWidget.setColormap)

        self.viewSplitter = QSplitter(Qt.Orientation.Vertical)
        self.viewSplitter.addWidget(self.excitonWfWidget)
        self.viewSplitter.addWidget(self.analysisWidget)
        self.viewSplitter.setCollapsible(0, False)
        self.viewSplitter.setStretchFactor(0, 3)
        self.viewSplitter.setStretchFactor(1, 2)

        self.inspector = self.parameters3DWidget
        layout = pageLayout(self.viewSplitter, self.inspector)
        self.setLayout(layout)

        # Sizes of the side panel and of the analysis panel, kept between sessions
        self.persistence = PersistentState()
        self.persistence.remember('page', layout.itemAt(0).widget())
        self.persistence.remember('analysis', self.viewSplitter)
        # The camera, with each dataset: restored after its lattice is drawn and
        # centered (which a preference, restored earlier, would not survive)
        self.persistence.remember('camera', scope=DATASET, get=self.excitonWfWidget.cameraState,
                                  set=self.excitonWfWidget.setCameraState)

    @Slot(bool)
    def setDarkTheme(self, dark: bool):
        self.excitonWfWidget.setDarkTheme(dark)
        self.analysisWidget.setDarkTheme(dark)

    # Analysis

    @Slot()
    def onWfComputedForAnalysis(self):
        self.radialResult = None
        self.updateAnalysis()

    @Slot()
    def setPlaneFromView(self):
        toViewer, up = self.excitonWfWidget.cameraAxes()
        self.parameters3DWidget.setPlaneFromView(toViewer, up)

    @Slot()
    def updateAnalysis(self):
        """Show or hide the analysis panel, and update it and the plane in 3D."""
        parameters, calc = self.parameters3DWidget, self.calculations
        shown = parameters.showAnalysisCheckBox.isChecked()
        self.analysisWidget.setVisible(shown)

        if not shown or calc.probabilityDensity() is None or calc.wfSupercell is None:
            self.excitonWfWidget.setCutPlane(None)
            if calc.probabilityDensity() is None:
                self.analysisWidget.clear()
            return

        try:
            plane = parameters.planeSettings()
        except ValueError as error:
            parameters.showPlaneStatus(str(error))
            return
        parameters.showPlaneStatus('')

        density = calc.probabilityDensity()
        voxels = calc.wfVoxels()
        particle = calc.wfFixedCartesian()
        particleLabel = 'hole' if calc.wfFixedParticle == 'h' else 'electron'
        lattice = np.asarray(calc.lattice.lat, dtype=float)

        normal = plane['normal'] / np.linalg.norm(plane['normal'])
        point = particle + plane['offset'] * normal
        cut = planeCut(density, voxels, point, normal, inPlane=plane['up'], latticeVectors=lattice)
        numbers, positions = calc.wfSupercellAtoms()
        atoms = atomsNearPlane(positions, numbers, point, (cut['u'], cut['v'], cut['n']), plane['atoms'])
        self.analysisWidget.setColormap(parameters.colormap())
        self.analysisWidget.showCut(cut, atoms, particleLabel, plane['offset'])

        if self.radialResult is None:
            self.radialResult = radialDistribution(density, voxels, particle)
        self.analysisWidget.showRadial(self.radialResult, particleLabel)

        supercellVectors = lattice * np.asarray(calc.wfSupercell)[:, None]
        polygon = planeSupercellPolygon(supercellVectors, point, normal) if plane['show3D'] else None
        self.excitonWfWidget.setCutPlane(polygon)

    @Slot(bool)
    def onDatasetChanged(self, found: bool):
        """Drop the wave function of the previous dataset and draw the new lattice."""
        self.excitonWfWidget.clearWfItems()
        self.excitonWfWidget.setCutPlane(None)
        self.radialResult = None
        self.displayCache.clear()
        self.analysisWidget.clear()
        if found:
            self.plotLattice()
            self.excitonWfWidget.centerView()

    # Display resolution

    def displayDensity(self):
        """The density as displayed (upsampled if smoothing is on), and its grid-to-space transform."""
        density = self.calculations.probabilityDensity()
        transform = np.array(self.calculations.tr4x4, dtype=float)
        if self.smoothing == 1:
            return density, transform.tolist()
        key = (id(density), self.smoothing)
        if key not in self.displayCache:
            self.displayCache.clear()   # one copy at a time
            self.displayCache[key] = upsampleDensity(density, self.smoothing)
        transform[:3, :3] /= self.smoothing
        return self.displayCache[key], transform.tolist()

    @Slot(int)
    def setSmoothing(self, factor):
        self.smoothing = factor
        if self.calculations.probabilityDensity() is not None:
            self.plotWf()

    @Slot(object)
    def setColormap(self, colormap):
        """Recolor the density: the shown plot now, the others when shown (see plotWfIfMissing)."""
        self.excitonWfWidget.colormap = colormap
        if self.calculations.probabilityDensity() is not None:
            self.plotWf()

    @Slot()
    def plotWf(self):
        # The other plot types are redone when shown (plotWfIfMissing); the shown
        # one stays until its replacement is ready
        view, plotType = self.excitonWfWidget, self.parameters3DWidget.plotType()
        for index, clear in enumerate((view.clearWfMeshItem, view.clearWfMeshItemSet, view.clearWfVolItem)):
            if index != plotType:
                clear()

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

    # Plots of the density: geometry prepared inline when light, in the worker
    # thread when heavy (fine grids, smoothing, many levels), then uploaded

    def prepareDisplay(self, plotType, message, makeGeometry, work):
        """
        Compute `makeGeometry(density, context)` on the displayed density
        (upsampling it first if needed) and show it with plot type `plotType`'s
        show method; inline if `work` (grid points times surfaces) is small.
        """
        calc = self.calculations
        density = calc.probabilityDensity()
        if density is None:
            return
        factor = self.smoothing
        transform = np.array(calc.tr4x4, dtype=float)
        transform[:3, :3] /= factor
        transform = transform.tolist()
        cached = self.displayCache.get((id(density), factor)) if factor > 1 else density
        # Only the latest request is shown: an earlier one still being prepared
        # (other smoothing, level, colormap...) is outdated
        request = self.displayRequest = object()

        def compute(context):
            displayed = cached
            if displayed is None:
                context.stage('Smoothing the density')
                displayed = upsampleDensity(density, factor)
            return displayed, makeGeometry(displayed, context)

        def apply(result):
            displayed, geometry = result
            if self.displayRequest is not request or calc.probabilityDensity() is not density:
                return   # outdated: a newer request, or a newer wave function
            if factor > 1:
                self.displayCache.clear()   # one copy at a time
                self.displayCache[(id(density), factor)] = displayed
            self.showGeometry(plotType, geometry, transform)
            self.excitonWfWidget.showItem(self.parameters3DWidget.plotType())

        # Upsampling always takes a while: only work on a grid at hand runs inline
        if cached is not None and work * factor ** 3 <= INLINE_DISPLAY_WORK:
            calc.tasks.dropPending('display')
            apply(compute(TaskContext()))
        else:
            calc.tasks.submit(message, compute, apply, key='display')

    def showGeometry(self, plotType, geometry, transform):
        view = self.excitonWfWidget
        if plotType == 0:
            view.showIsoMesh(geometry, self.options.isoLevel(), transform, self.options.isoOpacity())
        elif plotType == 1:
            view.showIsoSetMesh(geometry, transform)
        else:
            view.showVolume(geometry, self.options.sliceDensity(), transform)

    def gridPoints(self):
        density = self.calculations.probabilityDensity()
        return 0 if density is None else density.size

    @Slot()
    def plotWfIso(self):
        level = self.options.isoLevel()
        self.prepareDisplay(0, 'Preparing the isosurface…', lambda density, context: isoMesh(density, level),
                            self.gridPoints())

    @Slot()
    def plotWfIsoSet(self):
        numLevels, opacity = self.options.numIsoLevels(), self.options.isoSetOpacity()
        colormap = self.excitonWfWidget.colormap
        self.prepareDisplay(1, 'Preparing the isosurfaces…',
                            lambda density, context: isoSetMesh(density, numLevels, colormap, opacity, context),
                            self.gridPoints() * numLevels)

    @Slot()
    def plotWfVol(self):
        colormap, sliceDensity = self.excitonWfWidget.colormap, self.options.sliceDensity()
        opacity, contrast = self.options.volumeOpacity(), self.options.volumeContrast()
        self.prepareDisplay(2, 'Preparing the volume…',
                            lambda density, context: volumeColors(density, colormap, opacity, contrast, sliceDensity),
                            self.gridPoints())

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
