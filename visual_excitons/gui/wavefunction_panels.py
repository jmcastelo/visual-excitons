"""
The exciton wave function: the 3D view, the analysis and their controls, each
shown in its own dock by the main window.
"""

from PySide6.QtCore import QObject, Slot
import numpy as np

from .wavefunction_view import WavefunctionView
from .wavefunction_controls import WavefunctionControls
from .axis_gizmo import AxisGizmo
from .analysis_panel import AnalysisPanel
from visual_excitons.core.analysis import (planeCut, atomsNearPlane, radialDistribution, planeSupercellPolygon,
                                           voxelVectors,
                                           upsampleDensity)
from visual_excitons.core.tasks import TaskContext
from .wf_geometry import isoMesh, isoSetMesh, volumeColors

# Below this many grid points (times surfaces), plots are prepared inline:
# fast enough not to show (e.g. while dragging the iso level slider)
INLINE_DISPLAY_WORK = 3_000_000
from .persistence import PersistentState, DATASET
from visual_excitons.core.dataset import Dataset
from visual_excitons.core.parameters import WavefunctionParameters
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.bonds import findBonds, halfBonds
from visual_excitons.core.cellshift import (detectLayer, shiftAtoms, shiftCrystal, snapShift, rollDensity,
                                            periodicAxes, seamAxes)
from visual_excitons.core.export import supercellAtoms
from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR
from .colormaps import makeColormap

# Color of the bonds in uniform coloring mode
BOND_GREY = (0.6, 0.6, 0.6)


class ParticleDensityDisplay:
    """
    The fixed particle's own density in the 3D view (Calculations.particleDensity,
    on the unit-cell grid of the wave function), relative to its largest value:
    repeated exactly over the supercell drawn (it is periodic with the lattice),
    shifted with the cell origin, and drawn in its own layer with its own
    settings (WavefunctionParameters.display['particle']).
    """

    def __init__(self, panels):
        self.panels = panels
        self.sourceKey, self.sourceDensity = None, None
        self.upsampled = {}
        self.request = None

    @property
    def settings(self):
        return self.panels.parameters.display['particle']

    @property
    def layer(self):
        return self.panels.view.layers['particle']

    def source(self):
        """The density over the supercell drawn, shifted, and its grid-to-space transform; None if there is none."""
        panels = self.panels
        d = panels.calculations.particleDensity
        if d is None or not panels.dataset.hasCell():
            return None
        density = d['density']
        grid = density.shape
        supercell = [int(n) for n in panels.parameters.supercell]
        shift = snapShift(panels.controls.cellShift(), grid)
        key = (id(density), tuple(supercell), tuple(round(s * g) for s, g in zip(shift, grid)))
        if key != self.sourceKey:
            top = float(np.max(density)) or 1.0
            tiled = np.tile(np.asarray(density, dtype=float) / top, supercell)
            if any(shift):
                tiled = rollDensity(tiled, shift, grid)
            self.sourceKey, self.sourceDensity = key, tiled
            self.upsampled = {}
        transform = np.eye(4)
        transform[:3, :3] = np.asarray(panels.dataset.cell, dtype=float).T * np.asarray(supercell) / np.asarray(
            self.sourceDensity.shape)
        return self.sourceDensity, transform

    def plot(self, onlyIfMissing=False):
        """Draw the plot type set (the others are drawn again when chosen); nothing while switched off."""
        source = self.source()
        if source is None:
            self.layer.clear()
            return
        s = self.settings
        self.layer.setShown(s.shown)
        if not s.shown:
            return
        plotType = s.plotType
        if onlyIfMissing and self.layer.itemExists(plotType):
            self.layer.showItem(plotType)
            return
        density, transform = source
        colormap = makeColormap(s.colormap, s.reversed)
        self.layer.colormap = colormap
        if plotType == 0:
            level = s.isoLevel
            make, work, message = (lambda d, c: isoMesh(d, level)), density.size, 'Preparing the isosurface…'
        elif plotType == 1:
            levels, opacity = s.numIsoLevels, s.isoSetOpacity
            make = lambda d, c: isoSetMesh(d, levels, colormap, opacity, c)
            work, message = density.size * levels, 'Preparing the isosurfaces…'
        else:
            opacity, contrast, slices = s.volumeOpacity, s.volumeContrast, s.sliceDensity
            make = lambda d, c: volumeColors(d, colormap, opacity, contrast, slices)
            work, message = density.size, 'Preparing the volume…'
        factor = s.smoothing
        transform = transform.copy()
        transform[:3, :3] /= factor
        cached = density if factor == 1 else self.upsampled.get(factor)
        request = self.request = object()

        def compute(context):
            displayed = cached
            if displayed is None:
                context.stage('Smoothing the density')
                displayed = upsampleDensity(density, factor)
            return displayed, make(displayed, context)

        def apply(result):
            if self.request is not request or self.sourceDensity is not density:
                return                       # outdated: a newer request, or another density
            displayed, geometry = result
            if factor > 1:
                self.upsampled = {factor: displayed}
            for index, clear in enumerate((self.layer.clearMesh, self.layer.clearMeshSet, self.layer.clearVolume)):
                if index != plotType:
                    clear()
            matrix = transform.tolist()
            if plotType == 0:
                self.layer.showIsoMesh(geometry, s.isoLevel, matrix, s.isoOpacity)
            elif plotType == 1:
                self.layer.setIsoSetStyle(s.isoSetStyle)
                self.layer.showIsoSetMesh(geometry, matrix)
            else:
                self.layer.showVolume(geometry, s.sliceDensity, matrix)
            self.layer.showItem(plotType)

        tasks = self.panels.calculations.tasks
        if cached is not None and work * factor ** 3 <= INLINE_DISPLAY_WORK:
            tasks.dropPending('display-particle')
            apply(compute(TaskContext()))
        else:
            tasks.submit(message, compute, apply, key='display-particle')

    def onSettingChanged(self, key):
        """A display setting of the particle density changed: what it affects, drawn again."""
        s, layer = self.settings, self.layer
        if key == 'show':
            if s.shown:
                self.plot(onlyIfMissing=True)
            else:
                layer.setShown(False)
        elif key == 'plotType':
            self.plot(onlyIfMissing=True)
        elif key == 'isoOpacity':
            layer.setIsoOpacity(s.isoOpacity, s.isoLevel)
        elif key == 'isoSetOpacity':
            layer.setIsoSetOpacity(s.isoSetOpacity)
        elif key == 'isoSetStyle':
            layer.setIsoSetStyle(s.isoSetStyle)
        else:                                 # colormap, smoothing, levels, volume: everything drawn again
            layer.clear()
            self.plot()

    def redraw(self):
        """The density, supercell or cell origin changed."""
        self.layer.clear()
        self.plot()


class WavefunctionPanels(QObject):
    def __init__(self, dataset: Dataset, parameters: WavefunctionParameters, calculations: Calculations, parent=None):
        super().__init__(parent)

        self.dataset = dataset
        self.parameters = parameters

        self.calculations = calculations
        # Display upsampling (see displayDensity), cleared with each new wave function
        self.smoothing = 1
        self.displayCache = {}
        self.displayRequest = None
        self.calculations.wfComputed.connect(self.displayCache.clear)
        self.calculations.wfComputed.connect(self.plotWf)

        self.view = WavefunctionView()

        self.controls = WavefunctionControls(dataset, parameters, calculations)
        self.controls.plotTypeChanged.connect(self.plotWfIfMissing)
        self.controls.plotTypeChanged.connect(self.view.showItem)
        self.controls.isoLevelChanged.connect(self.plotWfIso)
        self.controls.numIsoLevelsChanged.connect(self.plotWfIsoSet)
        self.controls.isoOpacityChanged.connect(self.view.setIsoOpacity)
        self.controls.isoSetOpacityChanged.connect(self.view.setIsoSetOpacity)
        self.controls.isoSetStyleChanged.connect(self.view.setIsoSetStyle)
        self.controls.colormapChanged.connect(self.setColormap)
        self.controls.smoothingChanged.connect(self.setSmoothing)
        self.controls.sliceDensityChanged.connect(self.plotWfVol)
        self.controls.volumeParametersChanged.connect(self.plotWfVol)
        self.controls.signalReplotLattice.connect(self.plotLattice)
        # Centered on what is shown when the supercell changes, and when a new
        # wave function is first shown (not one restored, with its own view)
        self.controls.supercellResized.connect(self.view.centerView)
        # The origin of the cell shown (core/cellshift.py): everything moves together
        self.shiftCache = {}
        self.controls.cellShiftChanged.connect(self.onCellShiftChanged)
        # The position as shown in the controls uses the same shift as the drawing
        self.controls.shiftProvider = self.shownShift
        self.calculations.wfComputed.connect(self.controls.updateShownPosition)
        self.calculations.wfComputed.connect(self.updateCellOriginNote)
        self.centerOnDisplay = False
        self.calculations.wfComputed.connect(
            lambda: setattr(self, 'centerOnDisplay', not self.calculations.restoringResults))
        self.controls.fixedParticlePosChanged.connect(self.translateFixedParticle)
        self.controls.centerViewClicked.connect(self.view.centerView)
        self.controls.viewDirChanged.connect(self.view.setViewDirection)
        self.controls.projectionChanged.connect(self.view.changeProjection)
        self.controls.viewLatticeChanged.connect(self.view.viewLattice)
        self.controls.viewAtomNamesChanged.connect(self.view.viewAtomNames)
        self.controls.viewBoundariesChanged.connect(self.view.viewBoundaries)
        self.controls.viewBondsChanged.connect(self.view.viewBonds)

        gizmo = AxisGizmo(target=self.view, size=200)
        self.view.attach_gizmo(gizmo, 10)

        self.controls.showCartesianAxesChanged.connect(gizmo.setShowCartesian)
        self.controls.showLatticeVectorsChanged.connect(gizmo.setShowLattice)
        self.controls.showReciprocalVectorsChanged.connect(self.view.setShowReciprocalVectors)
        self.controls.showAxisLabelsChanged.connect(gizmo.setShowLabels)
        self.controls.showCellInfoChanged.connect(self.view.setShowCellInfo)
        self.controls.showCaptionChanged.connect(self.view.setShowCaption)
        # The maxima selected in the placing list, marked in the view as the fixed particle is drawn
        self.markedMaxima = []
        self.controls.maximaMarkersChanged.connect(self.markMaxima)
        self.calculations.wfComputed.connect(self.updateCaption)

        # The fixed particle's own density, drawn in its own layer (see ParticleDensityDisplay)
        self.particleDisplay = ParticleDensityDisplay(self)
        self.controls.displayChanged.connect(self.onDisplayChanged)
        self.calculations.particleDensityReady.connect(lambda density: self.particleDisplay.redraw())
        self.calculations.particleDensityReady.connect(self.updateCaption)
        self.controls.supercellResized.connect(self.particleDisplay.redraw)

        # Initial view from the view widgets' default state
        self.controls.applyView()

        # Analysis panel: its dock is shown and hidden with the Analysis
        # section's checkbox (see MainWindow.createPanels)
        self.analysis = AnalysisPanel()
        self.radialResult = None   # of the current wave function, computed when first shown
        self.calculations.wfComputed.connect(self.onWfComputedForAnalysis)
        self.controls.analysisChanged.connect(self.updateAnalysis)
        self.controls.planeFromViewRequested.connect(self.setPlaneFromView)
        # The colormap of the density cut
        self.controls.colormapChanged.connect(self.updateCutColormap)
        # A cut of the particle density follows it, and the particle as set
        self.calculations.particleDensityReady.connect(lambda density: self.updateAnalysisOf('particle'))
        self.controls.fixedParticlePosChanged.connect(lambda: self.updateAnalysisOf('particle'))
        self.controls.supercellResized.connect(lambda: self.updateAnalysisOf('particle'))

        self.persistence = PersistentState()
        # The camera, with each dataset: restored after its lattice is drawn and
        # centered (which a preference, restored earlier, would not survive)
        self.persistence.remember('camera', scope=DATASET, get=self.view.cameraState,
                                  set=self.view.setCameraState)

    @Slot(bool)
    def setDarkTheme(self, dark: bool):
        self.view.setDarkTheme(dark)
        self.analysis.setDarkTheme(dark)

    # Analysis

    @Slot()
    def onWfComputedForAnalysis(self):
        self.radialResult = None
        self.updateAnalysis()

    @Slot()
    def setPlaneFromView(self):
        toViewer, up = self.view.cameraAxes()
        self.controls.setPlaneFromView(toViewer, up)

    @Slot()
    @Slot()
    def updateCutColormap(self, *args):
        self.analysis.setColormap(self.controls.colormap(self.controls.cutLayer()))

    def updateAnalysisOf(self, layer):
        """Update the analysis if its plane cut shows the density `layer`."""
        if self.controls.cutLayer() == layer:
            self.updateAnalysis()

    def updateAnalysis(self):
        """Update the analysis panel, if shown, and the plane in 3D."""
        if self.controls.cutLayer() == 'particle':
            return self.updateParticleCut()
        parameters, calc = self.controls, self.calculations
        shown = parameters.showAnalysisCheckBox.isChecked()

        if not shown or calc.probabilityDensity() is None or calc.wfSupercell is None:
            self.view.setCutPlane(None)
            if calc.probabilityDensity() is None:
                self.analysis.clear()
            return

        try:
            plane = parameters.planeSettings()
        except ValueError as error:
            parameters.showPlaneStatus(str(error))
            return
        parameters.showPlaneStatus('')

        # In the frame of the analysis (see analysisShift): no seams, distances right
        shift = self.analysisShift()
        density = self.shiftedDensity(shift)
        voxels = calc.wfVoxels()
        particle = self.shownFixedCartesian(shift)
        particleLabel = 'hole' if calc.wfFixedParticle == 'h' else 'electron'
        lattice = np.asarray(calc.lattice.lat, dtype=float)

        normal = plane['normal'] / np.linalg.norm(plane['normal'])
        point = particle + plane['offset'] * normal
        cut = planeCut(density, voxels, point, normal, inPlane=plane['up'], latticeVectors=lattice)
        numbers, positions = self.shownSupercellAtoms(shift)
        atoms = atomsNearPlane(positions, numbers, point, (cut['u'], cut['v'], cut['n']), plane['atoms'])
        self.analysis.setColormap(parameters.colormap())
        self.analysis.showCut(cut, atoms, particleLabel, plane['offset'])

        if self.radialResult is None:
            # Distances to the nearest image along the axes where the density repeats with its box
            self.radialResult = radialDistribution(density, voxels, particle,
                                                   periodic=periodicAxes(calc.wfSupercell, calc.kGrid()))
        self.analysis.showRadial(self.radialResult, particleLabel)

        # The plane in the 3D view: through the particle as shown there
        supercellVectors = lattice * np.asarray(calc.wfSupercell)[:, None]
        shownPoint = self.shownFixedCartesian() + plane['offset'] * normal
        polygon = planeSupercellPolygon(supercellVectors, shownPoint, normal) if plane['show3D'] else None
        self.view.setCutPlane(polygon)

    def updateParticleCut(self):
        """
        The plane cut of the fixed particle's own density: through the particle
        as set (it may not have a wave function yet), over the supercell drawn;
        the distances stay those of the wave function, if there is one.
        """
        controls, calc = self.controls, self.calculations
        d = calc.particleDensity
        source = self.particleDisplay.source()
        if not controls.showAnalysisCheckBox.isChecked() or source is None:
            self.view.setCutPlane(None)
            if d is None:
                self.analysis.clear('Compute the particle\'s density (Placing the fixed particle) to see it on the plane.')
            return
        try:
            plane = controls.planeSettings()
        except ValueError as error:
            controls.showPlaneStatus(str(error))
            return
        controls.showPlaneStatus('')
        density, transform = source
        lattice = np.asarray(self.dataset.cell, dtype=float)
        supercell = [int(n) for n in self.parameters.supercell]
        shift = snapShift(controls.cellShift(), d['density'].shape)
        crystal = shiftCrystal(np.asarray(self.parameters.position(), dtype=float) + np.asarray(supercell) // 2, shift,
                               supercell)
        particle = lattice.T @ crystal
        normal = plane['normal'] / np.linalg.norm(plane['normal'])
        point = particle + plane['offset'] * normal
        cut = planeCut(density, voxelVectors(lattice, supercell, density.shape), point, normal, inPlane=plane['up'],
                       latticeVectors=lattice)
        cell = calc.unitCell()
        positions = np.asarray(cell['atomic_positions'], dtype=float)[:len(cell['atomic_numbers'])]
        numbers, atoms = supercellAtoms(lattice, shiftAtoms(lattice, positions, shift), cell['atomic_numbers'], supercell)
        near = atomsNearPlane(atoms, numbers, point, (cut['u'], cut['v'], cut['n']), plane['atoms'])
        self.analysis.setColormap(controls.colormap('particle'))
        self.analysis.showCut(cut, near, 'hole' if d['particle'] == 'h' else 'electron', plane['offset'])
        if calc.probabilityDensity() is not None and calc.wfSupercell is not None:
            if self.radialResult is None:
                self.radialResult = radialDistribution(self.shiftedDensity(self.analysisShift()), calc.wfVoxels(),
                                                       self.shownFixedCartesian(self.analysisShift()),
                                                       periodic=periodicAxes(calc.wfSupercell, calc.kGrid()))
            self.analysis.showRadial(self.radialResult, 'hole' if calc.wfFixedParticle == 'h' else 'electron')
        else:
            self.analysis.clearDistances('The distances are those of the wave function: compute one to see them.')
        polygon = planeSupercellPolygon(lattice * np.asarray(supercell)[:, None], point, normal) if plane['show3D'] else None
        self.view.setCutPlane(polygon)

    @Slot(str, str)
    def onDisplayChanged(self, layer, key):
        """A display setting changed: the particle density's go to it; the wave function's own signals do the rest."""
        if layer == 'particle':
            self.particleDisplay.onSettingChanged(key)
            if key in ('colormap', 'colormapReversed') and self.controls.cutLayer() == 'particle':
                self.updateCutColormap()
        elif key == 'show':
            self.view.layers['wf'].setShown(self.parameters.display['wf'].shown)
        if key == 'show':
            self.updateCaption()

    @Slot(bool)
    def updateCaption(self, *args):
        """Say in the view what it shows: the density of which particle, of which exciton, the other fixed where."""
        calc, display = self.calculations, self.parameters.display

        def which(exc, states):
            states = states or [exc]
            return f'exciton {exc}' if len(states) == 1 else f'excitons {states[0]}–{states[-1]}'
        lines = []
        if calc.waveFunction is not None and display['wf'].shown:
            fixed, free = ('hole', 'Electron') if calc.wfFixedParticle == 'h' else ('electron', 'Hole')
            q, exc = calc.wfExciton
            position = ', '.join(f'{float(x) % 1.0 + 0.0:.4f}' for x in calc.wfFixedPosition)
            lines.append(f'{free} density of {which(exc, calc.wfStates)} at Q{q + 1}<br>{fixed} fixed at ({position})')
        d = calc.particleDensity
        if d is not None and display['particle'].shown:
            name = 'Hole' if d['particle'] == 'h' else 'Electron'
            lines.append(f'{name} density of {which(d["excIndex"], d["states"])} at Q{d["qIndex"] + 1}')
        self.view.setCaption('<br>'.join(lines) or None)

    def onDatasetChanged(self, found: bool):
        """Drop the wave function of the previous dataset and draw the new lattice."""
        self.view.clearWfItems()
        self.view.layers['particle'].clear()
        self.view.setCutPlane(None)
        self.view.setCaption(None)
        self.markMaxima([])
        self.radialResult = None
        self.displayCache.clear()
        self.analysis.clear()
        self.shiftCache = {}
        if found:
            ucell = self.calculations.unitCell()
            self.controls.setLayer(detectLayer(ucell['base_lattice_vectors'], ucell['atomic_positions'],
                                                         self.calculations.kGrid()))
            self.plotLattice()
            self.view.centerView()
        else:
            self.plotLattice()      # clears the structure

    # The origin of the cell shown

    def shownShift(self):
        """The shift of what is shown (fractions of a, b, c), on the grid of the wave function if there is one."""
        shift = self.controls.cellShift()
        calc = self.calculations
        if calc.waveFunction is not None and calc.wfGrid:
            shift = snapShift(shift, calc.wfGrid)
        return [float(value) for value in shift]

    def analysisShift(self):
        """
        The shift of the analysis: that shown along the axes where wrapping the
        density is exact (its box spans whole periods of the k-point grid, e.g.
        the vacuum axis of a monolayer), none along the others. There, wrapping
        joins faces whose densities do not match: a seam in the plane cut, and
        distances measured to the wrong side of the box.
        """
        calc = self.calculations
        periodic = periodicAxes(calc.wfSupercell, calc.kGrid())
        return [s if exact else 0.0 for s, exact in zip(self.shownShift(), periodic)]

    def shownDensity(self):
        """The density as shown: shifted with the cell origin (the same array while nothing changes)."""
        return self.shiftedDensity(self.shownShift())

    def shiftedDensity(self, shift):
        """The density shifted by `shift` (the same array while neither changes)."""
        calc = self.calculations
        density = calc.probabilityDensity()
        if density is None or not calc.wfGrid:
            return density
        key = (id(density), tuple(round(s * g) for s, g in zip(shift, calc.wfGrid)))
        if key not in self.shiftCache:
            # Those of the view and of the analysis (see analysisShift), kept together
            self.shiftCache = {k: v for k, v in self.shiftCache.items() if k[0] == key[0]}
            if len(self.shiftCache) >= 2:
                self.shiftCache.pop(next(iter(self.shiftCache)))
            self.shiftCache[key] = rollDensity(density, shift, calc.wfGrid)
        return self.shiftCache[key]

    def shownFixedCartesian(self, shift=None):
        """The fixed particle, shifted with the cell origin (or by `shift`)."""
        calc = self.calculations
        crystal = shiftCrystal(calc.wfFixedCrystal(), self.shownShift() if shift is None else shift, calc.wfSupercell)
        return np.asarray(calc.lattice.lat, dtype=float).T @ crystal

    def shownSupercellAtoms(self, shift=None):
        """The atoms of the supercell, shifted with the cell origin (or by `shift`)."""
        calc = self.calculations
        cell = calc.unitCell()
        positions = np.asarray(cell['atomic_positions'], dtype=float)[:len(cell['atomic_numbers'])]
        shift = self.shownShift() if shift is None else shift
        return supercellAtoms(cell['base_lattice_vectors'], shiftAtoms(cell['base_lattice_vectors'], positions, shift),
                              cell['atomic_numbers'], calc.wfSupercell)

    @Slot()
    def onCellShiftChanged(self):
        if not self.dataset.hasCell():
            return
        self.plotLattice()
        self.translateFixedParticle()
        self.particleDisplay.redraw()
        self.updateAnalysisOf('particle')
        self.radialResult = None
        if self.calculations.probabilityDensity() is not None:
            self.displayCache.clear()
            self.plotWf()
            self.updateAnalysis()
        self.updateCellOriginNote()
        self.view.centerView()

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
        self.controls.showCellOriginNote(text)

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
        self.view.colormap = colormap
        if self.calculations.probabilityDensity() is not None:
            self.plotWf()

    @Slot()
    def plotWf(self):
        # The other plot types are redone when shown (plotWfIfMissing); the shown
        # one stays until its replacement is ready
        view, plotType = self.view, self.controls.plotType()
        for index, clear in enumerate((view.clearWfMeshItem, view.clearWfMeshItemSet, view.clearWfVolItem)):
            if index != plotType:
                clear()

        if self.controls.plotType() == 0:
            self.plotWfIso()
        elif self.controls.plotType() == 1:
            self.plotWfIsoSet()
        elif self.controls.plotType() == 2:
            self.plotWfVol()

    @Slot(int)
    def plotWfIfMissing(self, index: int):
        if not self.view.itemExists(index):
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
            self.view.showItem(self.controls.plotType())
            if self.centerOnDisplay:
                self.centerOnDisplay = False
                self.view.centerView()

        # Upsampling always takes a while: only work on a grid at hand runs inline
        if cached is not None and work * factor ** 3 <= INLINE_DISPLAY_WORK:
            calc.tasks.dropPending('display')
            apply(compute(TaskContext()))
        else:
            calc.tasks.submit(message, compute, apply, key='display')

    def showGeometry(self, plotType, geometry, transform):
        view = self.view
        if plotType == 0:
            view.showIsoMesh(geometry, self.parameters.isoLevel, transform, self.parameters.isoOpacity)
        elif plotType == 1:
            view.showIsoSetMesh(geometry, transform)
        else:
            view.showVolume(geometry, self.parameters.sliceDensity, transform)

    def gridPoints(self):
        density = self.shownDensity()
        return 0 if density is None else density.size

    @Slot()
    def plotWfIso(self):
        level = self.parameters.isoLevel
        self.prepareDisplay(0, 'Preparing the isosurface…', lambda density, context: isoMesh(density, level),
                            self.gridPoints())

    @Slot()
    def plotWfIsoSet(self):
        numLevels, opacity = self.parameters.numIsoLevels, self.parameters.isoSetOpacity
        colormap = self.view.colormap
        self.prepareDisplay(1, 'Preparing the isosurfaces…',
                            lambda density, context: isoSetMesh(density, numLevels, colormap, opacity, context),
                            self.gridPoints() * numLevels)

    @Slot()
    def plotWfVol(self):
        colormap, sliceDensity = self.view.colormap, self.parameters.sliceDensity
        opacity, contrast = self.parameters.volumeOpacity, self.parameters.volumeContrast
        self.prepareDisplay(2, 'Preparing the volume…',
                            lambda density, context: volumeColors(density, colormap, opacity, contrast, sliceDensity),
                            self.gridPoints())

    @Slot()
    def plotLattice(self):
        self.view.clearLatticeItems()
        self.view.clearAtomNamesItems()
        self.view.clearLatticeBoundaryItems()

        # Nothing to draw before a SAVE database is loaded, or once it is closed
        if not self.dataset.hasCell():
            self.view.plotBaseLatticeVectors(None)
            return

        ucell = dict(self.calculations.unitCell())
        shift = self.shownShift()
        if any(shift):
            positions = np.asarray(ucell['atomic_positions'], dtype=float)[:len(ucell['atomic_numbers'])]
            ucell['atomic_positions'] = shiftAtoms(ucell['base_lattice_vectors'], positions, shift)

        self.view.plotBaseLatticeVectors(ucell['base_lattice_vectors'])

        supercell = self.parameters.supercell

        for i in range(supercell[0]):
            for j in range(supercell[1]):
                for k in range(supercell[2]):
                    offset = ucell['base_lattice_vectors'][0] * i + ucell['base_lattice_vectors'][1] * j + ucell['base_lattice_vectors'][2] * k
                    self.view.plotUnitCellBoundaries(ucell['base_lattice_vectors'], offset)
                    self.view.plotUnitCellAtoms(ucell['atomic_numbers'], ucell['atomic_positions'], offset,
                                                           self.parameters.atomScale)

        self.plotBonds(ucell, supercell)

    def plotBonds(self, ucell, supercell):
        lattice = ucell['base_lattice_vectors']
        numbers = np.asarray(ucell['atomic_numbers'], dtype=int)
        positions = np.asarray(ucell['atomic_positions'], dtype=float)[:len(numbers)]

        bonds = findBonds(lattice, positions, numbers, self.parameters.bondTolerance)
        starts, ends, atoms = halfBonds(lattice, positions, bonds, supercell)
        uniformColor = BOND_GREY if self.parameters.bondColoring == 1 else None
        self.view.plotBonds(starts, ends, numbers[atoms], self.parameters.bondRadius * ANGSTROM_TO_BOHR,
                                       uniformColor)

    @Slot()
    def markMaxima(self, positions):
        """Mark maxima of the particle density (crystal coordinates of the unit cell) where the particle would be."""
        self.markedMaxima = list(positions)
        self.updateMarkers()

    def updateMarkers(self):
        if not self.markedMaxima or not self.dataset.hasCell():
            self.view.setMarkers([])
            return
        supercell, shift = self.parameters.supercell, self.shownShift()
        cell = np.asarray(self.dataset.cell, dtype=float)
        self.view.setMarkers([cell.T @ shiftCrystal(np.asarray(p, dtype=float) + np.asarray(supercell) // 2, shift,
                                                    supercell) for p in self.markedMaxima])

    def translateFixedParticle(self):
        self.updateMarkers()
        if not self.dataset.hasCell():
            return
        supercell = self.parameters.supercell
        crystal = np.asarray(self.parameters.position(), dtype=float) + np.asarray(supercell) // 2
        crystal = shiftCrystal(crystal, self.shownShift(), supercell)
        self.view.translateFixedParticle(np.asarray(self.dataset.cell, dtype=float).T @ crystal)
