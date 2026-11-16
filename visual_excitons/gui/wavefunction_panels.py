"""
The exciton wave function: the 3D view, the analysis and their controls, each
shown in its own dock by the main window.
"""

from PySide6.QtCore import QObject, Slot
import numpy as np

from .exciton_wf_widget import ExcitonWfWidget
from .parameters_3d_widget import Parameters3DWidget
from .axes_3d_widget import AxisGizmo
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
from visual_excitons.core.cellshift import (detectLayer, shiftAtoms, shiftCrystal, snapShift, rollDensity,
                                            periodicAxes, seamAxes)
from visual_excitons.core.export import supercellAtoms
from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR

# Color of the bonds in uniform coloring mode
BOND_GREY = (0.6, 0.6, 0.6)


class WavefunctionPanels(QObject):
    def __init__(self, options: Options, calculations: Calculations, parent=None):
        super().__init__(parent)

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
        # Centered on what is shown when the supercell changes, and when a new
        # wave function is first shown (not one restored, with its own view)
        self.parameters3DWidget.supercellResized.connect(self.excitonWfWidget.centerView)
        # The origin of the cell shown (core/cellshift.py): everything moves together
        self.shiftCache = (None, None)
        self.parameters3DWidget.cellShiftChanged.connect(self.onCellShiftChanged)
        # The position as shown in the controls uses the same shift as the drawing
        self.parameters3DWidget.shiftProvider = self.shownShift
        self.calculations.wfComputed.connect(self.parameters3DWidget.updateShownPosition)
        self.calculations.wfComputed.connect(self.updateCellOriginNote)
        self.centerOnDisplay = False
        self.calculations.wfComputed.connect(
            lambda: setattr(self, 'centerOnDisplay', not self.calculations.restoringResults))
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

        # Analysis panel: its dock is shown and hidden with the Analysis
        # section's checkbox (see MainWindow.createPanels)
        self.analysisWidget = AnalysisWidget()
        self.radialResult = None   # of the current wave function, computed when first shown
        self.calculations.wfComputed.connect(self.onWfComputedForAnalysis)
        self.parameters3DWidget.analysisChanged.connect(self.updateAnalysis)
        self.parameters3DWidget.planeFromViewRequested.connect(self.setPlaneFromView)
        self.parameters3DWidget.colormapChanged.connect(self.analysisWidget.setColormap)

        self.inspector = self.parameters3DWidget

        self.persistence = PersistentState()
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
        """Update the analysis panel, if shown, and the plane in 3D."""
        parameters, calc = self.parameters3DWidget, self.calculations
        shown = parameters.showAnalysisCheckBox.isChecked()

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

        density = self.shownDensity()
        voxels = calc.wfVoxels()
        particle = self.shownFixedCartesian()
        particleLabel = 'hole' if calc.wfFixedParticle == 'h' else 'electron'
        lattice = np.asarray(calc.lattice.lat, dtype=float)

        normal = plane['normal'] / np.linalg.norm(plane['normal'])
        point = particle + plane['offset'] * normal
        cut = planeCut(density, voxels, point, normal, inPlane=plane['up'], latticeVectors=lattice)
        numbers, positions = self.shownSupercellAtoms()
        atoms = atomsNearPlane(positions, numbers, point, (cut['u'], cut['v'], cut['n']), plane['atoms'])
        self.analysisWidget.setColormap(parameters.colormap())
        self.analysisWidget.showCut(cut, atoms, particleLabel, plane['offset'])

        if self.radialResult is None:
            # Distances to the nearest image along the axes where the density repeats with its box
            self.radialResult = radialDistribution(density, voxels, particle,
                                                   periodic=periodicAxes(calc.wfSupercell, calc.kGrid()))
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
        self.shiftCache = (None, None)
        if found:
            ucell = self.calculations.unitCell()
            self.parameters3DWidget.setLayer(detectLayer(ucell['base_lattice_vectors'], ucell['atomic_positions'],
                                                         self.calculations.kGrid()))
            self.plotLattice()
            self.excitonWfWidget.centerView()

    # The origin of the cell shown

    def shownShift(self):
        """The shift of what is shown (fractions of a, b, c), on the grid of the wave function if there is one."""
        shift = self.parameters3DWidget.cellShift()
        calc = self.calculations
        if calc.waveFunction is not None and calc.wfGrid:
            shift = snapShift(shift, calc.wfGrid)
        return [float(value) for value in shift]

    def shownDensity(self):
        """The density as shown: shifted with the cell origin (the same array while nothing changes)."""
        calc = self.calculations
        density = calc.probabilityDensity()
        if density is None or not calc.wfGrid:
            return density
        shift = self.shownShift()
        key = (id(density), tuple(round(s * g) for s, g in zip(shift, calc.wfGrid)))
        if self.shiftCache[0] != key:
            self.shiftCache = (key, rollDensity(density, shift, calc.wfGrid))
        return self.shiftCache[1]

    def shownFixedCartesian(self):
        calc = self.calculations
        crystal = shiftCrystal(calc.wfFixedCrystal(), self.shownShift(), calc.wfSupercell)
        return np.asarray(calc.lattice.lat, dtype=float).T @ crystal

    def shownSupercellAtoms(self):
        calc = self.calculations
        cell = calc.unitCell()
        positions = np.asarray(cell['atomic_positions'], dtype=float)[:len(cell['atomic_numbers'])]
        return supercellAtoms(cell['base_lattice_vectors'], shiftAtoms(cell['base_lattice_vectors'], positions,
                                                                       self.shownShift()),
                              cell['atomic_numbers'], calc.wfSupercell)

    @Slot()
    def onCellShiftChanged(self):
        if not self.options.hasCell():
            return
        self.plotLattice()
        self.translateFixedParticle()
        self.radialResult = None
        if self.calculations.probabilityDensity() is not None:
            self.displayCache.clear()
            self.plotWf()
            self.updateAnalysis()
        self.updateCellOriginNote()
        self.excitonWfWidget.centerView()

    @Slot()
    def updateCellOriginNote(self):
        """Where the wave function, wrapped, shows a seam (cut by its supercell along a shifted axis)."""
        calc = self.calculations
        text = ''
        if calc.probabilityDensity() is not None and calc.wfSupercell:
            seams = seamAxes(calc.probabilityDensity(), self.shownShift(), calc.wfSupercell, calc.kGrid())
            if seams:
                axes = ', '.join('abc'[axis] for axis in seams)
                text = (f'Along {axes}, the wave function is cut by its supercell, and wrapping it with the shift '
                        f'shows a seam: a larger supercell along {axes} avoids it.')
        self.parameters3DWidget.showCellOriginNote(text)

    # Display resolution

    def displayDensity(self):
        """The density as displayed (upsampled if smoothing is on), and its grid-to-space transform."""
        density = self.shownDensity()
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
        density = self.shownDensity()
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
            if self.displayRequest is not request or self.shownDensity() is not density:
                return   # outdated: a newer request, or a newer wave function
            if factor > 1:
                self.displayCache.clear()   # one copy at a time
                self.displayCache[(id(density), factor)] = displayed
            self.showGeometry(plotType, geometry, transform)
            self.excitonWfWidget.showItem(self.parameters3DWidget.plotType())
            if self.centerOnDisplay:
                self.centerOnDisplay = False
                self.excitonWfWidget.centerView()

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
        density = self.shownDensity()
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

        ucell = dict(self.calculations.unitCell())
        shift = self.shownShift()
        if any(shift):
            positions = np.asarray(ucell['atomic_positions'], dtype=float)[:len(ucell['atomic_numbers'])]
            ucell['atomic_positions'] = shiftAtoms(ucell['base_lattice_vectors'], positions, shift)

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
        supercell = self.options.supercell()
        crystal = np.asarray(self.options.particlePosition(), dtype=float) + np.asarray(supercell) // 2
        crystal = shiftCrystal(crystal, self.shownShift(), supercell)
        self.excitonWfWidget.translateFixedParticle(np.asarray(self.options.cell, dtype=float).T @ crystal)
