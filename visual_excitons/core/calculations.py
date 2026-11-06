from PySide6.QtCore import QObject, Signal, Slot
from yambopy import YamboLatticeDB, ExcitonDispersion, YamboExcitonDB, YamboBSEAbsorptionSpectra, YamboQPDB
from yambopy import YamboElectronsDB, YamboWFDB, ex_wf2Real
import numpy as np

from .tasks import TaskRunner, databaseAccess
from .export import supercellAtoms, writeDensity
from .atomic_data import BOHR_TO_ANGSTROM



class PointData:
    def __init__(self, i, j):
        self.i = i
        self.j = j


# Calculations proper. They run in the worker thread (see tasks.py): they only
# use their arguments, never the state shared with the GUI.

def computeDispersion(context, saveDir, diagoDir, nExcitons, qBZ, nQpoints):
    context.stage('Loading the lattice')
    lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')

    # One exciton database per Q-point (counted by the progress hooks)
    context.stage('Loading the excitons of each Q-point', nQpoints)
    excitonDispersion = ExcitonDispersion(lattice, nExcitons, diagoDir)

    context.stage('Interpolating along the Q-path')
    collinearQPoints, qIndices, x = qBZ.find_collinear_grid(lattice)
    y = excitonDispersion.exc_energies[qIndices]

    if nQpoints > 1:
        xInter, yInter = excitonDispersion.interpolate_dispersion(qBZ)
    else:
        xInter, yInter = [], []

    return {
        'lattice': lattice,
        'excitonDispersion': excitonDispersion,
        'collinearQPoints': collinearQPoints,
        'qIndices': qIndices,
        'points': [[[x[i], y[i][j]] for i in range(len(x))] for j in range(y.shape[1])],
        'pointsData': [[PointData(i, j + 1) for i in range(len(x))] for j in range(y.shape[1])],
        'xInter': xInter,
        'yInter': yInter,
        'xRange': (min(x), max(x)),
        'yRange': (np.array(y).min(), np.array(y).max()),
        'specialPoints': qBZ.special_kpoints_distances(merge_sections=True),
        'labels': qBZ.path_labels_list(merge_sections=True),
    }


# Broadening of the absorption spectra (yambopy's default), and the margin of
# the automatic range around the exciton energies: five broadenings, where the
# Lorentzian peaks have fallen to 4% of their height
ABSORPTION_BROADENING = 0.1
ABSORPTION_AUTO_MARGIN = 5 * ABSORPTION_BROADENING


def automaticAbsorptionRange(excitonEnergies, margin=ABSORPTION_AUTO_MARGIN):
    """Energy range covering all the excitons plus `margin`, rounded outwards to 0.1 eV."""
    energies = np.asarray(excitonEnergies, dtype=float)
    low = max(0.0, np.floor((energies.min() - margin) * 10) / 10)
    high = np.ceil((energies.max() + margin) * 10) / 10
    return float(low), float(high)


def computeAbsorption(lattice, diagoDir, qPointIndex, index, energyStep, energyMin, energyMax, minIntensity,
                      autoRange=False):
    filename = "ndb.BS_diago_Q%d" % (qPointIndex + 1)
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename=filename, folder=diagoDir)
    if autoRange:
        energyMin, energyMax = automaticAbsorptionRange(excitonDB.eigenvalues.real)

    energyRange, epsilon = excitonDB.get_chi(estep=energyStep, emin=energyMin, emax=energyMax,
                                             broad=ABSORPTION_BROADENING)

    excitonAbsorption = YamboBSEAbsorptionSpectra(excitonDB)
    allExcitons = np.array(excitonAbsorption.get_excitons(min_intensity=0.0, max_energy=energyMax)).real

    brightExcitons = np.empty((0, 3))
    darkExcitons = np.empty((0, 3))
    brightExcAbsInterp = []
    pointsData = []

    if len(allExcitons) > 0:
        brightExcitons = allExcitons[(allExcitons[:, 1] >= minIntensity)]
        darkExcitons = allExcitons[(allExcitons[:, 1] < minIntensity)]
        brightExcAbsInterp = np.interp(brightExcitons[:, 0], energyRange, epsilon.imag)
        pointsData = [PointData(index, int(j)) for j in brightExcitons[:, 2]]

    return {'q': qPointIndex, 'index': index, 'energy': energyRange, 'absorption': epsilon.imag,
            'brightExcEnergy': brightExcitons[:, 0], 'brightExcAbsorption': brightExcAbsInterp,
            'brightExcIntensities': brightExcitons[:, 1], 'brightExcIndices': brightExcitons[:, 2],
            'darkExcEnergy': darkExcitons[:, 0], 'data': pointsData, 'range': (energyMin, energyMax)}


def computeBandStructure(context, lattice, diagoDir, gw, qpDir, saveDir, qBZ, excitonIndices):
    context.stage('Loading the databases')
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename='ndb.BS_diago_Q1', folder=diagoDir)
    if gw:
        energies = YamboQPDB.from_db(folder=qpDir)
    else:
        energies = YamboElectronsDB.from_db_file(folder=saveDir)

    context.stage('Interpolating the bands')
    excitonBands = excitonDB.interpolate(energies=energies, excitons=excitonIndices, bz=qBZ, lpratio=5, verbose=True)

    return {'k': qBZ.kpoints_distances(), 'bands': np.transpose(excitonBands.bands),
            'weights': np.transpose(excitonBands.weights)}


def computeWaveFunction(context, lattice, saveDir, diagoDir, q_index, exc_index, fixed_particle, fixed_position,
                        cutoff_ry, supercell, cache=None):
    """
    Real-space probability density of exciton `exc_index` (1-based) at Q-point
    `q_index` (0-based, the file ndb.BS_diago_Q<q_index + 1>), with the effective
    parameters actually used (see below).

    `cache`, a dict, keeps the wave-function database between calls: loading it
    is the slowest step, and it is the same for all the excitons of a dataset.
    """
    if lattice is None:
        context.stage('Loading the lattice')
        lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')

    context.stage('Loading the exciton')
    filename = 'ndb.BS_diago_Q%d' % (q_index + 1)
    # Load the states up to the requested one, plus a margin for the states
    # degenerate with it
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename=filename, folder=diagoDir, neigs=exc_index + 20)
    numStates = len(excitonDB.eigenvalues)
    if exc_index > numStates:
        raise ValueError(f'Exciton {exc_index} does not exist: {filename} has {numStates} excitons')

    # Loading the wave functions and the real-space calculation report their own
    # stages and progress (tqdm hooks)
    bandsRange = [int(np.min(excitonDB.table[:, 1])) - 1, int(np.max(excitonDB.table[:, 2]))]
    key = (saveDir, tuple(bandsRange))
    if cache is not None and key in cache:
        wavefunctionDB = cache[key]
    else:
        wavefunctionDB = YamboWFDB(path=saveDir, save='.', latdb=lattice, bands_range=bandsRange)
        if cache is not None:
            # One database at a time: they are large
            cache.clear()
            cache[key] = wavefunctionDB

    degen_states = np.array(excitonDB.get_degenerate(exc_index, eps=1e-2)) - 1
    Akcv = excitonDB.get_Akcv()[degen_states]
    Qpt = wavefunctionDB.ydb.lat @ excitonDB.car_qpoint

    # ex_wf2Real increases even supercell sizes by 1 (modifying the list in place),
    # moves the fixed particle to the nearest point of the real-space grid and then
    # to the central cell of the supercell; its final position is returned as the
    # last atomic position (Cartesian)
    supercell = list(supercell)
    sc_latvecs, atom_nums, atomPositions, real_wfc = ex_wf2Real(
        Akcv, Qpt, wavefunctionDB, [np.min(excitonDB.table[:, 1]), np.max(excitonDB.table[:, 2])],
        fixed_position=list(fixed_position), fix_particle=fixed_particle, supercell=supercell,
        wfcCutoffRy=cutoff_ry, block_size=256)

    context.stage('Computing the probability density')
    density = np.sum(np.abs(real_wfc) ** 2, axis=(0, 1, 2, 3))
    waveFunction = np.clip(np.array(density / np.max(np.abs(density)), dtype=float), 0.0, 1.0)

    tr4x4 = np.eye(4, dtype=float)
    tr4x4[0:3, 0:3] = lattice.lat.T * supercell / waveFunction.shape

    # Effective parameters: supercell actually used, grid points per unit cell, and
    # fixed particle position in crystal coordinates of the unit cell (as given)
    crystal = np.linalg.solve(lattice.lat.T, atomPositions[-1])
    return {
        'lattice': lattice,
        'waveFunction': waveFunction,
        'atomPositions': atomPositions,
        'tr4x4': tr4x4,
        'fixedParticle': fixed_particle,
        'supercell': list(supercell),
        'grid': [int(n) // s for n, s in zip(waveFunction.shape, supercell)],
        'fixedPosition': np.round(crystal - np.array(supercell) // 2, 10).tolist(),
        'qIndex': q_index,
        'excIndex': exc_index,
    }



class Calculations(QObject):
    qPathReady = Signal(list, list)

    excitonDispersionReady = Signal(list, list, list, list)
    excitonDispersionRange = Signal(tuple, tuple)
    excitonDispersionNumCurvesChanged = Signal(int)
    excitonDispersionInit = Signal()

    excitonBandStructureReady = Signal(list, list, list)
    excitonBandStructureClear = Signal()
    excitonBandStructureNumCurvesChanged = Signal(int)
    excitonBandStructureInit = Signal()

    excitonAbsorptionReady = Signal(list, bool)
    excitonAbsorptionClear = Signal()
    excitonAbsorptionCurveAppended = Signal(int)
    excitonAbsorptionCurveRemoved = Signal(int)

    wfComputed = Signal()
    densityExported = Signal(str)   # file written

    # Exciton chosen in the spectra, shared with the wave-function page:
    # Q-point index (0-based, as in ndb.BS_diago_Q<index + 1>), exciton index (1-based), energy (eV)
    excitonSelected = Signal(int, int, float)

    # Progress and errors of the background calculations (see tasks.py)
    busyStarted = Signal(str)          # a task starts: its message
    busyFinished = Signal()            # a task finished, failed or was cancelled
    busyChanged = Signal(bool)         # whether any task is running or queued
    progressChanged = Signal(int, int, str)  # done, total (0: unknown), stage
    taskCancelled = Signal(str)
    errorOccurred = Signal(str, str)   # title, message

    def __init__(self, options, synchronous=False):
        """`synchronous`: run the calculations in the calling thread (tests)."""
        super().__init__()

        self.options = options

        self.tasks = TaskRunner(synchronous, self)
        self.tasks.started.connect(self.busyStarted)
        self.tasks.finished.connect(self.busyFinished)
        self.tasks.busyChanged.connect(self.busyChanged)
        self.tasks.progress.connect(self.progressChanged)
        self.tasks.cancelled.connect(self.taskCancelled)
        self.tasks.failed.connect(self.errorOccurred)
        # Calculations on the previous dataset are pointless: stop them before it changes
        self.options.datasetAboutToChange.connect(self.tasks.reset)

        self.dispPoints = []
        self.dispPointsData = []
        self.dispXInter = []
        self.dispYInter = []

        self.excAbsData = []
        self.showExcitonLabels = False

        self.k = []
        self.bands = []
        self.weights = []
        self.weightFactor = 1.0

        self.lattice = None
        self.excitonDispersion = None
        self.collinear_qpoints = None
        self.qIndices = None

        self.waveFunction = None
        self.wfAtomPositions = None
        # Effective parameters of the last wave function (see computeWaveFunction)
        self.wfFixedParticle = None
        self.wfFixedPosition = None
        self.wfSupercell = None
        self.wfGrid = None
        self.wfExciton = None  # (q index, exciton index)
        self.tr4x4 = np.eye(4, dtype=float)

        self.selectedExciton = None  # (q index, exciton index, energy)

        # Wave-function database kept between calculations (see computeWaveFunction);
        # only used from the worker thread
        self.wavefunctionCache = {}

    # Tasks

    @Slot()
    def cancel(self):
        """Stop the running calculation and drop the queued ones."""
        self.tasks.cancelAll()

    def isBusy(self):
        return self.tasks.isBusy()

    def _reject(self, message, reason):
        title = message[:-1] if message.endswith('…') else message
        self.errorOccurred.emit(f'{title} failed', reason)

    @Slot()
    def resetDataset(self):
        """Forget everything computed from the previous dataset."""
        self.tasks.reset()
        self.lattice = None
        self.excitonDispersion = None
        self.collinear_qpoints = None
        self.qIndices = None
        self.excAbsData = []
        self.waveFunction = None
        self.wfAtomPositions = None
        self.selectedExciton = None
        # A new dict: a task still running on the old dataset keeps the old one
        self.wavefunctionCache = {}

    @Slot(list, bool)
    def selectExciton(self, points, dummy=None):
        """Select the exciton of the first clicked point of an absorption spectrum (energy along x)."""
        if points:
            self._select(points[0], float(points[0].pos().x()))

    @Slot(list, bool)
    def selectDispersionExciton(self, points, dummy=None):
        """Select the exciton of the first clicked point of the dispersion (energy along y)."""
        if points:
            self._select(points[0], float(points[0].pos().y()))

    def _select(self, point, energy):
        if self.qIndices is None:
            return
        qIndex = int(self.qIndices[point.data().i])
        excIndex = int(point.data().j)
        self.selectedExciton = (qIndex, excIndex, energy)
        self.excitonSelected.emit(qIndex, excIndex, energy)

    def selectedExcitonPositions(self):
        """
        Where the selected exciton is drawn: points (x, y) in the dispersion
        (at each path point of its Q-point, if it is one of the excitons
        plotted) and in the absorption spectra (if it is bright there).
        """
        positions = {'dispersion': [], 'absorption': []}
        if self.selectedExciton is None or self.qIndices is None:
            return positions
        qIndex, excIndex, _ = self.selectedExciton

        if 1 <= excIndex <= len(self.dispPoints):
            curve = self.dispPoints[excIndex - 1]
            positions['dispersion'] = [tuple(curve[i]) for i, q in enumerate(self.qIndices) if q == qIndex]

        for data in self.excAbsData:
            if data['q'] == qIndex:
                for energy, height, index in zip(data['brightExcEnergy'], data['brightExcAbsorption'], data['brightExcIndices']):
                    if int(index) == excIndex:
                        positions['absorption'].append((float(energy), float(height)))
        return positions

    # Dispersion

    @Slot()
    def getExcitonDispersion(self):
        message = 'Computing the excitonic dispersion…'
        options = self.options
        if options.qBZ is None:
            return self._reject(message, 'No Q-path: set one on the System page first.')
        if not options.diagoDir:
            return self._reject(message, 'No BSE directory: choose one on the System page first.')

        arguments = dict(saveDir=options.saveDir, diagoDir=options.diagoDir, nExcitons=options.nExcitons,
                         qBZ=options.qBZ, nQpoints=options.nQpoints)
        self.tasks.submit(message, lambda context: computeDispersion(context, **arguments),
                          self._applyDispersion, key='dispersion')

    def _applyDispersion(self, result):
        self.lattice = result['lattice']
        self.excitonDispersion = result['excitonDispersion']
        self.collinear_qpoints = result['collinearQPoints']
        self.qIndices = result['qIndices']
        self.dispPoints = result['points']
        self.dispPointsData = result['pointsData']
        self.dispXInter = result['xInter']
        self.dispYInter = result['yInter']
        self.excAbsData = []

        self.qPathReady.emit(result['specialPoints'], result['labels'])
        self.excitonDispersionRange.emit(result['xRange'], result['yRange'])
        self.excitonDispersionNumCurvesChanged.emit(len(self.dispYInter))
        self.excitonDispersionInit.emit()

        self.excitonBandStructureClear.emit()
        self.excitonAbsorptionClear.emit()

    @Slot()
    def emitExcitonDispersionReady(self):
        self.excitonDispersionReady.emit(self.dispPoints, self.dispPointsData, self.dispXInter, self.dispYInter)

    # Absorption

    def absorptionParameters(self):
        """Snapshot of the inputs of the absorption spectra."""
        o = self.options
        return dict(lattice=self.lattice, diagoDir=o.diagoDir, energyStep=o.energyStep, energyMin=o.energyMin,
                    energyMax=o.energyMax, minIntensity=o.excMinIntensity, autoRange=o.absorptionAutoRange)

    def computeAbsorptionSpectrum(self, index, qPointIndex, parameters):
        return computeAbsorption(qPointIndex=qPointIndex, index=index, **parameters)

    @Slot()
    def computeQPointAbsorptionSpectrum(self, points, toggleCurve):
        index = points[0].data().i
        qPointIndex = int(self.qIndices[index])

        if self.absorptionCurveIndex(qPointIndex) >= 0:
            # Already computed: only show, keep or drop it
            self._updateAbsorptionCurves(qPointIndex, toggleCurve, None)
            return

        parameters = self.absorptionParameters()
        self.tasks.submit('Computing the absorption spectrum…',
                          lambda context: self.computeAbsorptionSpectrum(index, qPointIndex, parameters),
                          lambda data: self._updateAbsorptionCurves(qPointIndex, toggleCurve, data))

    def _updateAbsorptionCurves(self, qPointIndex, toggleCurve, data):
        """Curves after a click on Q-point `qPointIndex`, with its spectrum `data` if newly computed."""
        curveIndex = self.absorptionCurveIndex(qPointIndex)

        if curveIndex < 0:
            if data is None:
                return
            data['fixed'] = toggleCurve
            self.excAbsData.append(data)
            self.excitonAbsorptionCurveAppended.emit(data['q'])
        elif toggleCurve:
            if self.excAbsData[curveIndex]['fixed']:
                self.excAbsData.pop(curveIndex)
                self.excitonAbsorptionCurveRemoved.emit(curveIndex)
            else:
                self.excAbsData[curveIndex]['fixed'] = True

        # Drop the curves that were not kept (Ctrl-click), except the one just
        # clicked. Going backwards, the index of each curve is still valid when
        # it is removed, here and in the curve styles (excitonAbsorptionCurveRemoved)
        for curveIndex in reversed(range(len(self.excAbsData))):
            curveData = self.excAbsData[curveIndex]
            if curveData['q'] != qPointIndex and not curveData['fixed']:
                self.excAbsData.pop(curveIndex)
                self.excitonAbsorptionCurveRemoved.emit(curveIndex)

        self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

    @Slot()
    def recomputeAbsorptionSpectra(self):
        curves = [(data['index'], data['q']) for data in self.excAbsData]
        if not curves:
            return
        parameters = self.absorptionParameters()

        def compute(context):
            context.stage('Absorption spectra', len(curves))
            spectra = {}
            for index, q in curves:
                spectra[q] = self.computeAbsorptionSpectrum(index, q, parameters)
                context.advance()
            return spectra

        self.tasks.submit('Computing the absorption spectra…', compute, self._applyRecomputedSpectra,
                          key='absorption-recompute')

    def _applyRecomputedSpectra(self, spectra):
        # Curves may have been added or dropped meanwhile: update those still shown
        for i, data in enumerate(self.excAbsData):
            if data['q'] in spectra:
                newData = spectra[data['q']]
                newData['fixed'] = data['fixed']
                self.excAbsData[i] = newData
        self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

    @Slot()
    def emitExcitonAbsorption(self):
        self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

    def absorptionCurveIndex(self, q):
        for i, curveData in enumerate(self.excAbsData):
            if curveData['q'] == q:
                return i
        return -1

    # Band structure

    @Slot()
    def getExcitonBandStructure(self, points, dummy):
        if not np.all(self.collinear_qpoints[points[0].data().i] == [0.0, 0.0, 0.0]):
            self._applyBandStructure({'k': [], 'bands': [], 'weights': []})
            return

        o = self.options
        arguments = dict(lattice=self.lattice, diagoDir=o.diagoDir, gw=o.gw, qpDir=o.qpDir, saveDir=o.saveDir,
                         qBZ=o.qBZ, excitonIndices=tuple(point.data().j for point in points))
        self.tasks.submit('Interpolating the excitonic band structure…',
                          lambda context: computeBandStructure(context, **arguments),
                          self._applyBandStructure, key='band-structure')

    def _applyBandStructure(self, result):
        self.k, self.bands, self.weights = result['k'], result['bands'], result['weights']
        self.excitonBandStructureNumCurvesChanged.emit(len(self.bands))
        self.excitonBandStructureInit.emit()
        self.emitExcitonBandStructure()

    @Slot()
    def setWeightFactor(self, factor):
        self.weightFactor = factor
        if len(self.k) > 0:
            self.excitonBandStructureReady.emit(self.k, self.bands, self.weights * self.weightFactor)

    @Slot()
    def emitExcitonBandStructure(self):
        scaledWeights = []
        if len(self.weights) > 0:
            scaledWeights = self.weights * self.weightFactor

        self.excitonBandStructureReady.emit(self.k, self.bands, scaledWeights)

    @Slot()
    def toggleExcitonLabelsVisibility(self, visible):
        self.showExcitonLabels = visible
        self.excitonAbsorptionReady.emit(self.excAbsData, visible)

    # Wave function

    def computeExcitonWaveFunction(self, q_index=0, exc_index=1, fixed_particle='h', fixed_position=None, cutoff_ry=-1,
                                   supercell=None):
        """
        Compute, in the background, the real-space wave function of exciton
        `exc_index` (1-based) at Q-point `q_index` (0-based, the file
        ndb.BS_diago_Q<q_index + 1>); wfComputed is emitted when it is ready.
        """
        arguments = dict(lattice=self.lattice, saveDir=self.options.saveDir, diagoDir=self.options.diagoDir,
                         q_index=q_index, exc_index=exc_index, fixed_particle=fixed_particle,
                         fixed_position=list(fixed_position if fixed_position is not None else [0, 0, 0]),
                         cutoff_ry=cutoff_ry, supercell=list(supercell if supercell is not None else [1, 1, 1]),
                         cache=self.wavefunctionCache)
        self.tasks.submit('Computing the exciton wave function…',
                          lambda context: computeWaveFunction(context, **arguments),
                          self._applyWaveFunction, key='wave-function')

    def _applyWaveFunction(self, result):
        self.lattice = result['lattice']
        self.waveFunction = result['waveFunction']
        self.wfAtomPositions = result['atomPositions']
        self.tr4x4 = result['tr4x4']
        self.wfFixedParticle = result['fixedParticle']
        self.wfSupercell = result['supercell']
        self.wfGrid = result['grid']
        self.wfFixedPosition = result['fixedPosition']
        self.wfExciton = (result['qIndex'], result['excIndex'])
        self.wfComputed.emit()

    def exportDensity(self, filename):
        """
        Save the probability density with the atoms of the supercell (format
        from the extension: .cube or .xsf), in the background.
        """
        message = 'Saving the probability density…'
        if self.waveFunction is None:
            return self._reject(message, 'No wave function: compute one first.')

        cell = self.unitCell()
        numbers, positions = supercellAtoms(cell['base_lattice_vectors'], cell['atomic_positions'],
                                            cell['atomic_numbers'], self.wfSupercell)
        lattice = np.asarray(self.lattice.lat, dtype=float)
        fixedCrystal = np.asarray(self.wfFixedPosition) + np.asarray(self.wfSupercell) // 2
        fixedAngstrom = lattice.T @ fixedCrystal * BOHR_TO_ANGSTROM
        particle = 'hole' if self.wfFixedParticle == 'h' else 'electron'
        qIndex, excIndex = self.wfExciton
        comment = (f'Exciton {excIndex} at Q-point {qIndex + 1}, {particle} fixed at crystal coordinates '
                   f'{" ".join(f"{x:.4f}" for x in fixedCrystal)} of the supercell '
                   f'({" ".join(f"{x:.4f}" for x in fixedAngstrom)} A); '
                   f'supercell {"x".join(map(str, self.wfSupercell))}; values relative to the maximum')
        arguments = dict(density=self.waveFunction, lattice=lattice, supercell=list(self.wfSupercell),
                         atomicNumbers=numbers, atomPositions=positions, comment=comment)

        def compute(context):
            context.stage('Writing ' + str(filename).rsplit('/', 1)[-1])
            writeDensity(filename, **arguments)
            return filename

        self.tasks.submit(message, compute, self.densityExported.emit)

    def probabilityDensity(self):
        return self.waveFunction

    def unitCell(self):
        if self.lattice is None:
            with databaseAccess():
                self.lattice = YamboLatticeDB.from_db(self.options.saveDir + '/ns.db1')

        return {
            'atomic_numbers': self.lattice.atomic_numbers,
            'atomic_positions': self.lattice.car_atomic_positions,
            'base_lattice_vectors': self.lattice.lat
        }

    def atomPositions(self):
        return self.wfAtomPositions
