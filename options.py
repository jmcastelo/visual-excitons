from PySide6.QtCore import QObject, Signal
from pathlib import PurePath, Path
from yambopy import ibrav_required_parameters, get_lattice_data, YamboLatticeDB, BrillouinZone
from glob import glob
import numpy as np



def get_angle_between(ai, aj):
    return np.round(np.arccos(np.dot(ai, aj) / (np.linalg.norm(ai) * np.linalg.norm(aj))) * 180 / np.pi, 4)



def get_cell_params(cell):
    cell_params = {
        'a': np.round(np.linalg.norm(cell[0,:]), 4),
        'b': np.round(np.linalg.norm(cell[1,:]), 4),
        'c': np.round(np.linalg.norm(cell[2,:]), 4),
        'alpha': get_angle_between(cell[1,:], cell[2,:]),
        'beta': get_angle_between(cell[0,:], cell[2,:]),
        'gamma': get_angle_between(cell[0,:], cell[1,:])
    }
    return cell_params



class Options(QObject):
    # Dir signals
    saveDirChanged = Signal(str, str)
    diagoDirChanged = Signal(str, str)
    qpDirChanged = Signal(str, str)

    # Database signal
    databaseFound = Signal(bool)

    numQPointsChanged = Signal(int)

    def __init__(self):
        super().__init__()

        # ibrav
        self.ibrav = -1
        self.ibravParameters = ibrav_required_parameters()
        self.availableIbrav = [ibrav for ibrav in list(self.ibravParameters.keys())]

        # Lattice data
        self.cell = []
        self.latticeParameters = {}
        self.variant =''
        self.highSymmetryPoints = {}
        self.availableHighSymmetryPoints = []
        self.defaultPath = ''

        # Q-Path (yet undefined)
        self.qBZ = None

        # Dispersion
        self.nExcitons = 6

        # Absorption
        self.energyStep = 0.02
        self.energyMin = 4.0
        self.energyMax = 20.0

        # Excitons
        self.excMinIntensity = 0.1

    def setSaveDir(self, dir):
        file = Path(dir + '/ns.db1')
        if file.is_file():
            self.saveDir = dir
            self.saveDirChanged.emit(dir, "ns.db1 found")
            self.setLatticeParameters()
            self.databaseFound.emit(True)
        else:
            self.saveDirChanged.emit(dir, "ns.db1 not found!")
            self.databaseFound.emit(False)

    def setDiagoDir(self, dir):
        files = glob(dir + '/ndb.BS_diago_Q*')
        self.nQpoints = len(files)

        if self.nQpoints > 0 :
            self.diagoDir = dir
            self.parentDir = Path(dir).parent.absolute()
            self.jobString = PurePath(self.diagoDir).name
            self.diagoDirChanged.emit(dir, "ndb.BS_diago_Q* found - (" + str(self.nQpoints) + " Q-Points)")
            self.numQPointsChanged.emit(self.nQpoints)
        else:
            self.diagoDirChanged.emit(dir, "ndb.BS_diago_Q* not found!")

    def setQPDir(self, dir):
        file = Path(dir + '/ndb.QP')
        if file.is_file():
            self.qpDir = dir
            self.qpDirChanged.emit(dir, "ndb.QP found")
        else:
            self.qpDirChanged.emit(dir, "ndb.QP not found!")

    def setLatticeParameters(self):
        lattice = YamboLatticeDB.from_db(self.saveDir + '/ns.db1', Expand=False)
        self.cell = lattice.lat
        self.latticeParameters = get_cell_params(self.cell)

    def detectLatticeType(self):
        for ibrav in self.availableIbrav:
            try:
                testCell, _, _, _ = get_lattice_data(ibrav, self.latticeParameters)
            except ValueError as e:
                continue

            if np.allclose(self.cell, testCell, rtol=1e-5):
                return ibrav

        return -1

    def setLatticeData(self, ibrav):
        cell, self.variant, self.highSymmetryPoints, self.defaultPath = get_lattice_data(ibrav, self.latticeParameters)
        self.availableHighSymmetryPoints = [label for label in self.highSymmetryPoints.keys()]

    def setIbrav(self, i):
        self.ibrav = i

    def setBrillouinZone(self, path: str = None, npoints: int = None, density: float = None):
        self.qBZ = BrillouinZone(ibrav=self.ibrav, parameters=self.latticeParameters, path_string=path, npoints=npoints, density=density)

    def getPathString(self):
        return self.qBZ.path_string
    """
    def updateQPointValue(self, index, component, value):
        self.kList[index][0][component] = value
        self.qPath = kPath(self.kList, self.intervals)

    def updateQPointLabel(self, index, label):
        self.kList[index][1] = label
        self.qPath = kPath(self.kList, self.intervals)

    def updateInterval(self, index, value):
        if index < len(self.intervals):
            self.intervals[index] = value
            self.qPath = kPath(self.kList, self.intervals)

    def insertQPoint(self, index):
        qPoint = [[0.0, 0.0, 0.0], "Gamma"]
        self.kList.insert(index + 1, qPoint)
        self.intervals.append(10)
        self.qPath = kPath(self.kList, self.intervals)

    def removeQPoint(self, index):
        self.kList.pop(index)
        if index < len(self.intervals): self.intervals.pop(index)
        self.qPath = kPath(self.kList, self.intervals)
    """

    def setNExcitons(self, n):
        if n < 1: n = 1
        self.nExcitons = n

    def setEnergyStep(self, step):
        if step <= 0.0: step = 0.001
        elif step > self.energyMax - self.energyMin: step = self.energyMax - self.energyMin
        self.energyStep = step

    def setEnergyMin(self, energy):
        if energy >= self.energyMax: energy = self.energyMax - self.energyStep
        if energy + self.energyStep > self.energyMax: self.energyStep = self.energyMax - self.energyMin
        self.energyMin = energy

    def setEnergyMax(self, energy):
        if energy <= self.energyMin: energy = self.energyMin + self.energyStep
        if self.energyMin + self.energyStep > energy: energy = self.energyMin + self.energyStep
        self.energyMax = energy

    def setExcMinIntensity(self, intensity):
        if intensity < 0.0: intensity = 0.0
        if intensity > 1.0: intensity = 1.0
        self.excMinIntensity = intensity
