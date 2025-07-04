from PySide6.QtCore import QObject, Signal, Slot
from yambopy import YamboLatticeDB, ExcitonDispersion, YamboExcitonDB, YamboBSEAbsorptionSpectra
from yambopy.lattice import calculate_distances, red_car
from yambopy.tools.skw import SkwInterpolator
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

    @Slot()
    def getExcitonDispersion(self):
        self.lattice = YamboLatticeDB.from_db(self.options.saveDir + '/ns.db1')
        self.excitonDispersion = ExcitonDispersion(self.lattice, self.options.nExcitons, self.options.diagoDir)

        collinear_qpoints, indices, collinear_distances = self.options.qBZ.get_collinear_kpoints(self.excitonDispersion.car_qpoints, self.lattice.sym_car, True)
        energies = self.excitonDispersion.exc_energies[indices]

        x = collinear_distances
        y = energies

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

    @Slot()
    def emitExcitonDispersionReady(self):
        self.excitonDispersionReady.emit(self.dispPoints, self.dispPointsData, self.dispXInter, self.dispYInter)

    def computeAbsorptionSpectrum(self, index):
        qPointIndex = self.dispersionData['qindices'][index]

        filename = "ndb.BS_diago_Q%d"%(qPointIndex + 1)

        excitonDB = YamboExcitonDB.from_db_file(self.lattice, filename = filename, folder = self.options.diagoDir)

        energyRange, epsilon = excitonDB.get_chi(estep = self.options.energyStep, emin = self.options.energyMin, emax = self.options.energyMax)

        excitonAbsorption = YamboBSEAbsorptionSpectra(excitonDB, qpt = qPointIndex + 1, path = self.options.parentDir, job_string = self.options.jobString, save = self.options.saveDir)

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
        qPointIndex = self.dispersionData['qindices'][index]

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

    def getQPathCartesian(self):
        # qPathCar = red_car(self.options.qPath.kpoints, self.lattice.rlat)

        # x = calculate_distances(qPathCar)
        # labels = self.options.qPath.klabels

        # self.qPathReady.emit(x, labels)

        self.qPathReady.emit(self.options.qBZ.special_kpoints_distances(merge_sections=True), self.options.qBZ.path_labels_list(merge_sections=True))

    @Slot()
    def getExcitonBandStructure(self, points, dummy):
        if (self.dispersionData['qpoints_car'][points[0].data().i] == [0.0, 0.0, 0.0]).all():
            excitonDB = YamboExcitonDB.from_db_file(self.lattice, filename = 'ndb.BS_diago_Q1', folder = self.options.diagoDir)

            excitonIndices = tuple(point.data().j for point in points)

            excitonBands = excitonDB.interpolate(energies = self.saveDB, excitons = excitonIndices, path = self.options.qPath, lpratio = 10, verbose = False)

            self.k = calculate_distances(red_car(excitonBands.kpoints, self.lattice.rlat))
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
