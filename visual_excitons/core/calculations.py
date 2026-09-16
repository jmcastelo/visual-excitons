from PySide6.QtCore import QObject, Signal, Slot
from yambopy import YamboLatticeDB, ExcitonDispersion, YamboExcitonDB, YamboBSEAbsorptionSpectra, YamboQPDB
from yambopy import YamboElectronsDB, YamboWFDB, ex_wf2Real
#from yambopy.tools.skw import SkwInterpolator
import numpy as np



class PointData:
    def __init__(self, i, j):
        self.i = i
        self.j = j



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

    def __init__(self, options):
        super().__init__()

        self.options = options

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
        self.tr4x4 = np.eye(4, dtype=float)

    @Slot()
    def getExcitonDispersion(self):
        self.lattice = YamboLatticeDB.from_db(self.options.saveDir + '/ns.db1')
        self.excitonDispersion = ExcitonDispersion(self.lattice, self.options.nExcitons, self.options.diagoDir)

        self.collinear_qpoints, self.qIndices, x = self.options.qBZ.find_collinear_grid(self.lattice)

        y = self.excitonDispersion.exc_energies[self.qIndices]

        self.dispPoints = [[[x[i], y[i][j]] for i in range(len(x))] for j in range(y.shape[1])]
        self.dispPointsData = [[PointData(i, j + 1) for i in range(len(x))] for j in range(y.shape[1])]

        if self.options.nQpoints > 1:
            self.dispXInter, self.dispYInter = self.excitonDispersion.interpolate_dispersion(self.options.qBZ)
        else:
            self.dispXInter = []
            self.dispYInter = []

        self.excAbsData = []

        self.qPathReady.emit(self.options.qBZ.special_kpoints_distances(merge_sections=True), self.options.qBZ.path_labels_list(merge_sections=True))

        xRange = (min(x), max(x))
        yRange = (np.array(y).min(), np.array(y).max())

        self.excitonDispersionRange.emit(xRange, yRange)
        self.excitonDispersionNumCurvesChanged.emit(len(self.dispYInter))
        self.excitonDispersionInit.emit()

        self.excitonBandStructureClear.emit()
        self.excitonAbsorptionClear.emit()

    """
    def interpolateDispersion(self):
        lpratio = 10
        fermie = 0
        nelect = 0

        ibz_nkpoints = self.lattice.ibz_nkpoints
        ibz_kpoints = np.zeros([ibz_nkpoints, 3])
        for idx_bz, idx_ibz in enumerate(self.lattice.kpoints_indexes):
            ibz_kpoints[idx_ibz] = self.lattice.red_kpoints[idx_bz]

        ibz_energies = self.excitonDispersion.exc_energies

        na = np.newaxis

        cell = (self.lattice.lat, self.lattice.red_atomic_positions, self.lattice.atomic_numbers)

        symrel = [sym for sym, trev in zip(self.lattice.sym_rec_red, self.lattice.time_rev_list) if trev == False ]
        time_rev = False

        skw = SkwInterpolator(lpratio, ibz_kpoints, ibz_energies[na, :, :], fermie, nelect, cell, symrel, time_rev, verbose=False)

        energies = skw.interp_kpts(self.options.qBZ.kpoints()).eigens

        return self.options.qBZ.kpoints_distances(), np.transpose(energies[0])
    """

    @Slot()
    def emitExcitonDispersionReady(self):
        self.excitonDispersionReady.emit(self.dispPoints, self.dispPointsData, self.dispXInter, self.dispYInter)

    def computeAbsorptionSpectrum(self, index):
        # qPointIndex = self.dispersionData['qindices'][index]
        qPointIndex = self.qIndices[index]

        filename = "ndb.BS_diago_Q%d"%(qPointIndex + 1)

        excitonDB = YamboExcitonDB.from_db_file(self.lattice, filename = filename, folder = self.options.diagoDir)

        energyRange, epsilon = excitonDB.get_chi(estep = self.options.energyStep, emin = self.options.energyMin, emax = self.options.energyMax)

        # excitonAbsorption = YamboBSEAbsorptionSpectra(excitonDB, qpt = qPointIndex + 1, path = self.options.parentDir, job_string = self.options.jobString, save = self.options.saveDir)
        excitonAbsorption = YamboBSEAbsorptionSpectra(excitonDB)

        allExcitons = excitonAbsorption.get_excitons(min_intensity = 0.0, max_energy = self.options.energyMax)
        allExcitons = np.array(allExcitons).real

        brightExcitons = []
        darkExcitons = []
        brightExcAbsInterp = []
        pointsData = []

        if len(allExcitons) > 0:
            brightExcitons = allExcitons[(allExcitons[:, 1] >= self.options.excMinIntensity)]
            darkExcitons = allExcitons[(allExcitons[:, 1] < self.options.excMinIntensity)]

            brightExcAbsInterp = np.interp(brightExcitons[:, 0], energyRange, epsilon.imag)

            pointsData = [PointData(index, int(j)) for j in brightExcitons[:, 2]]

        return {'q': qPointIndex, 'index': index, 'energy': energyRange, 'absorption': epsilon.imag, 'brightExcEnergy': brightExcitons[:, 0], 'brightExcAbsorption': brightExcAbsInterp, 'brightExcIntensities': brightExcitons[:, 1], 'brightExcIndices': brightExcitons[:, 2], 'darkExcEnergy': darkExcitons[:, 0], 'data': pointsData}

    @Slot()
    def computeQPointAbsorptionSpectrum(self, points, toggleCurve):
        index = points[0].data().i
        # qPointIndex = self.dispersionData['qindices'][index]
        qPointIndex = self.qIndices[index]

        curveIndex = self.absorptionCurveIndex(qPointIndex)

        if curveIndex < 0:
            data = self.computeAbsorptionSpectrum(index)
            data['fixed'] = toggleCurve
            self.excAbsData.append(data)
            self.excitonAbsorptionCurveAppended.emit(data['q'])
        elif toggleCurve:
            if self.excAbsData[curveIndex]['fixed']:
                self.excAbsData.pop(curveIndex)
                self.excitonAbsorptionCurveRemoved.emit(curveIndex)
            else:
                self.excAbsData[curveIndex]['fixed'] = True

        for curveData in self.excAbsData:
            if curveData['q'] != qPointIndex and not curveData['fixed']:
                self.excAbsData.remove(curveData)
                self.excitonAbsorptionCurveRemoved.emit(self.absorptionCurveIndex(curveData['q']))

        self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

    @Slot()
    def recomputeAbsorptionSpectra(self):
        newExcAbsData = []

        for curveData in self.excAbsData:
            index = curveData['index']
            newData = self.computeAbsorptionSpectrum(index)
            newData['fixed'] = curveData['fixed']
            newExcAbsData.append(newData)

        self.excAbsData = newExcAbsData
        self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

    @Slot()
    def emitExcitonAbsorption(self):
        self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

    def absorptionCurveIndex(self, q):
        for curveData in self.excAbsData:
            if curveData['q'] == q:
                return self.excAbsData.index(curveData)
        return -1

    """
    def getQPathCartesian(self):
        # qPathCar = red_car(self.options.qPath.kpoints, self.lattice.rlat)

        # x = calculate_distances(qPathCar)
        # labels = self.options.qPath.klabels

        # self.qPathReady.emit(x, labels)

        self.qPathReady.emit(self.options.qBZ.special_kpoints_distances(merge_sections=True), self.options.qBZ.path_labels_list(merge_sections=True))
    """

    @Slot()
    def getExcitonBandStructure(self, points, dummy):
        if np.all(self.collinear_qpoints[points[0].data().i] == [0.0, 0.0, 0.0]):
            excitonDB = YamboExcitonDB.from_db_file(self.lattice, filename='ndb.BS_diago_Q1', folder=self.options.diagoDir)

            if self.options.gw:
                energies = YamboQPDB.from_db(folder=self.options.qpDir)
            else:
                energies = YamboElectronsDB.from_db_file(folder=self.options.saveDir)

            excitonIndices = tuple(point.data().j for point in points)

            excitonBands = excitonDB.interpolate(energies=energies, excitons=excitonIndices, bz=self.options.qBZ, lpratio=5, verbose=True)

            # self.k = calculate_distances(red_car(excitonBands.kpoints, self.lattice.rlat))
            self.k = self.options.qBZ.kpoints_distances()
            self.bands = np.transpose(excitonBands.bands)
            self.weights = np.transpose(excitonBands.weights)
        else:
            self.k = []
            self.bands = []
            self.weights = []

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

    @Slot(int)
    def computeExcitonWaveFunction(self, exc_index=1, fixed_particle='h', fixed_position=None, cutoff_ry=-1, supercell=None):
        if fixed_position is None:
            fixed_position = [0, 0, 0]

        if supercell is None:
            supercell = [1, 1, 1]

        if self.lattice is None:
            self.lattice = YamboLatticeDB.from_db(self.options.saveDir + '/ns.db1')

        filename = 'ndb.BS_diago_Q%d' % exc_index
        excitonDB = YamboExcitonDB.from_db_file(self.lattice, filename=filename, folder=self.options.diagoDir, neigs=20)

        wavefunctionDB = YamboWFDB(path=self.options.saveDir, save='.', latdb=self.lattice, bands_range=[np.min(excitonDB.table[:, 1]) - 1, np.max(excitonDB.table[:, 2])])

        degen_tol = 1e-2
        degen_states = np.array(excitonDB.get_degenerate(exc_index, eps=degen_tol)) - 1

        Akcv = excitonDB.get_Akcv()[degen_states]

        excQpt = excitonDB.car_qpoint
        Qpt = wavefunctionDB.ydb.lat @ excQpt

        block_size = 256

        sc_latvecs, atom_nums, self.wfAtomPositions, real_wfc = ex_wf2Real(Akcv, Qpt, wavefunctionDB, [np.min(excitonDB.table[:, 1]), np.max(excitonDB.table[:, 2])], fixed_position=fixed_position, fix_particle=fixed_particle, supercell=supercell, wfcCutoffRy=cutoff_ry, block_size=block_size)

        density = np.abs(real_wfc) ** 2
        real_wfc = np.sum(density, axis=(0, 1, 2, 3))
        max_normalize_val = np.max(np.abs(real_wfc))

        self.waveFunction = np.clip(np.array(real_wfc / max_normalize_val, dtype=float), 0.0, 1.0)

        self.tr4x4 = np.eye(4, dtype=float)
        self.tr4x4[0:3,0:3] = self.lattice.lat.T * supercell / self.waveFunction.shape

        self.wfComputed.emit()

    def probabilityDensity(self):
        return self.waveFunction

    def unitCell(self):
        if self.lattice is None:
            self.lattice = YamboLatticeDB.from_db(self.options.saveDir + '/ns.db1')

        # print(self.lattice.car_atomic_positions)

        ucell = {
            'atomic_numbers': self.lattice.atomic_numbers,
            'atomic_positions': self.lattice.car_atomic_positions,
            'base_lattice_vectors': self.lattice.lat
        }

        return ucell

    def atomPositions(self):
        return self.wfAtomPositions