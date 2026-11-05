from PySide6.QtCore import QObject, Signal, Slot
from pathlib import PurePath, Path
from yambopy import IBRAV_REQUIRED_PARAMETERS, get_lattice_data, YamboLatticeDB, BrillouinZone
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
        self.availableIbrav = [ibrav for ibrav in list(IBRAV_REQUIRED_PARAMETERS.keys())]

        # Lattice data
        self.cell = []
        self.latticeParameters = {}
        self.variant = ''
        self.highSymmetryPoints = {}
        self.extraHighSymmetryPoints = {}
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

        # Bands
        self.gw = True

        # Exciton wavefunctions
        self.partType = 'h'
        self.holePos = [0.0, 0.0, 0.0]
        self.electronPos = [0.0, 0.0, 0.0]
        self.wfCutoffRy = 10
        self.scell = [1, 1, 1]
        self.wfIsoLevel = 0.5
        self.numWfIsoLevels = 10
        self.wfIsoOpacity = 0.1
        self.volSliceDensity = 5
        self.volOpacity = 0.8
        self.volContrast = 1.0
        # View directions (VESTA convention: the direction of projection,
        # i.e. from the viewer into the screen). Vectors are given in the basis
        # of each group and converted to Cartesian with viewVectorToCartesian
        self.viewBases = ['Cartesian', 'Lattice [uvw]', 'Reciprocal (hkl)']
        self.viewPresets = {
            'Cartesian': {
                'x': [1, 0, 0],
                'y': [0, 1, 0],
                'z': [0, 0, 1],
                'x + y': [1, 1, 0],
                'x + z': [1, 0, 1],
                'y + z': [0, 1, 1],
                'x + y + z': [1, 1, 1]
            },
            'Lattice [uvw]': {
                'a  [1 0 0]': [1, 0, 0],
                'b  [0 1 0]': [0, 1, 0],
                'c  [0 0 1]': [0, 0, 1],
                '[1 1 0]': [1, 1, 0],
                '[1 0 1]': [1, 0, 1],
                '[0 1 1]': [0, 1, 1],
                '[1 1 1]': [1, 1, 1]
            },
            'Reciprocal (hkl)': {
                'a*  normal to (1 0 0)': [1, 0, 0],
                'b*  normal to (0 1 0)': [0, 1, 0],
                'c*  normal to (0 0 1)': [0, 0, 1],
                'normal to (1 1 0)': [1, 1, 0],
                'normal to (1 0 1)': [1, 0, 1],
                'normal to (0 1 1)': [0, 1, 1],
                'normal to (1 1 1)': [1, 1, 1]
            }
        }

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

            if np.allclose(self.cell, testCell, atol=1.0e-4, rtol=0):
                return ibrav

        return None

    def setLatticeData(self, ibrav):
        cell, self.variant, self.highSymmetryPoints, self.defaultPath = get_lattice_data(ibrav, self.latticeParameters)
        self.availableHighSymmetryPoints = [label for label in self.highSymmetryPoints.keys()]

    def setIbrav(self, i):
        self.ibrav = i

    def setBrillouinZone(self, path: str = None, npoints: int = None, density: float = None):
        self.qBZ = BrillouinZone(ibrav=self.ibrav, parameters=self.latticeParameters, path_string=path, extra_points=self.extraHighSymmetryPoints, npoints=npoints, density=density)

    def getPathString(self):
        return self.qBZ.path_string

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

    def particleType(self):
        return self.partType

    @Slot(int)
    def setParticleType(self, index: int):
        if index == 0:
            self.partType = 'h'
        elif index == 1:
            self.partType = 'e'

    def particlePosition(self):
        if self.partType == 'h':
            return self.holePos
        else:
            return self.electronPos

    def setParticlePosition(self, position: list):
        if self.partType == 'h':
            self.holePos = position
        elif self.partType == 'e':
            self.electronPos = position

    def particlePositionCartesian(self):
        return self.cell.T @ self.particlePosition()

    def wfCutoff(self):
        return self.wfCutoffRy

    @Slot(float)
    def setWfCutoff(self, cutoff: float):
        self.wfCutoffRy = cutoff

    def supercell(self):
        return self.scell

    def setSupercell(self, sc: list):
        self.scell = sc

    def isoLevel(self):
        return self.wfIsoLevel

    def setIsoLevel(self, level: float):
        self.wfIsoLevel = level

    def numIsoLevels(self):
        return self.numWfIsoLevels

    def setNumIsoLevels(self, numLevels: int):
        self.numWfIsoLevels = numLevels

    def sliceDensity(self):
        return self.volSliceDensity

    def setSliceDensity(self, density: int):
        self.volSliceDensity = density

    def volumeOpacity(self):
        return self.volOpacity

    def setVolumeOpacity(self, opacity: float):
        self.volOpacity = min(max(opacity, 0.0), 1.0)

    def volumeContrast(self):
        return self.volContrast

    def setVolumeContrast(self, contrast: float):
        self.volContrast = max(contrast, 0.01)

    def opacity(self):
        return self.wfIsoOpacity

    def setOpacity(self, alpha: float):
        self.wfIsoOpacity = alpha

    def hasCell(self):
        return len(self.cell) > 0

    def viewVectorToCartesian(self, vector, basis: str):
        """
        Cartesian components of `vector` given in `basis` (one of viewBases):
        Cartesian, lattice [uvw] -> u a + v b + w c, or reciprocal (hkl) -> h a* + k b* + l c*.
        Only the direction matters, so the 2*pi factor of the reciprocal basis is dropped.
        """
        vector = np.asarray(vector, dtype=float)
        if basis == 'Cartesian':
            return vector
        if not self.hasCell():
            raise ValueError('Lattice vectors are not available: no SAVE database loaded')
        cell = np.asarray(self.cell, dtype=float)  # rows: a, b, c
        if basis == 'Lattice [uvw]':
            return cell.T @ vector
        if basis == 'Reciprocal (hkl)':
            reciprocal = np.linalg.inv(cell).T  # rows: a*, b*, c* (without 2*pi)
            return reciprocal.T @ vector
        raise ValueError(f'Unknown view basis: {basis}')