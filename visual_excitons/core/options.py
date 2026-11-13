from PySide6.QtCore import QObject, Signal, Slot
from pathlib import PurePath, Path
from yambopy import IBRAV_REQUIRED_PARAMETERS, get_lattice_data, lattice_data_for_cell, YamboLatticeDB, BrillouinZone
import numpy as np

from .tasks import databaseAccess
from .databases import bseFiles, qpDatabases



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



# Lattice variants (Setyawan-Curtarolo) by family, and their ibrav (with the
# other orientation of the same lattice, if any)
VARIANT_IBRAV = {'CUB': [1], 'FCC': [2], 'BCC': [3, -3], 'HEX': [4], 'RHL': [5, -5], 'TET': [6], 'BCT': [7],
                 'ORC': [8], 'ORCC': [9, -9], 'ORCF': [10], 'ORCI': [11]}


def computedQPoints(folder):
    """
    Indices (from 0) of the Q-points with a BSE file in `folder`, sorted. The
    number of a BSE file (ndb.BS_diago_Q<n>) is the index (from 1) of its
    Q-point in the irreducible list of the grid; a calculation may have only
    some. Files are recognised by their content too (see databases.py).
    """
    return list(bseFiles(folder)[0])


def qPointNames(indices, limit=12):
    """Q-points by their file numbers, runs shortened: [0, 1, 2, 4, 29] -> 'Q1–Q3, Q5, Q30'."""
    runs = []
    for index in sorted(indices):
        if runs and index == runs[-1][1] + 1:
            runs[-1][1] = index
        else:
            runs.append([index, index])
    names = [f'Q{a + 1}' if a == b else f'Q{a + 1}, Q{b + 1}' if b == a + 1 else f'Q{a + 1}–Q{b + 1}' for a, b in runs]
    if len(names) > limit:
        names = names[:limit] + ['…']
    return ', '.join(names)


def tickLabels(labels):
    """
    Path labels as shown on the plots: Γ, Σ₁, K′, merged sections as K|U
    (yambopy's Unicode rendering); a label it cannot read (e.g. from an older
    session file) is shown as it is.
    """
    from yambopy.bz.labels import format_label
    shown = []
    for label in labels:
        try:
            shown.append(format_label(str(label), 'unicode'))
        except ValueError:
            shown.append(str(label))
    return shown


def ibravCandidates(variant):
    """The ibrav values of a lattice variant (e.g. BCT2 -> [7], RHL1 -> [5, -5])."""
    return VARIANT_IBRAV.get(variant.rstrip('0123456789'), [])


class Options(QObject):
    # Dir signals
    saveDirChanged = Signal(str, str)
    diagoDirChanged = Signal(str, str)
    qpDirChanged = Signal(str, str)
    # The QP databases found in the QP directory (see databases.qpDatabases), and the one used
    qpDatabasesChanged = Signal(list, str)

    # Database signals: a new SAVE directory is about to be read; it was read
    datasetAboutToChange = Signal()
    databaseFound = Signal(bool)

    numQPointsChanged = Signal(int)
    # The Q-points computed (indices from 0, as in ndb.BS_diago_Q<index + 1>)
    qPointsChanged = Signal(list)

    # Calculation type: True for DFT+GW+BSE, False for DFT+BSE
    gwChanged = Signal(bool)

    def __init__(self):
        super().__init__()

        # Data directories (see setSaveDir, setDiagoDir, setQPDir)
        self.saveDir = ''
        self.diagoDir = ''
        self.qpDir = ''
        self.qpFile = ''            # the QP database used, in qpDir (e.g. ndb.QP, ndb.QP_140_146)
        self.qpDatabases = []       # those found in qpDir (dicts of databases.identify)
        self.bseFiles = {}          # Q-point index (from 0) -> BSE file name in diagoDir
        self.bseProblems = []       # BSE files not used, and why
        self.parentDir = ''
        self.jobString = ''
        self.nQpoints = 0
        self.qPoints = []           # computed Q-points (see computedQPoints)
        self.nIbzQpoints = 0        # irreducible Q-points of the grid (from the SAVE directory)

        # ibrav
        self.ibrav = -1
        self.availableIbrav = [ibrav for ibrav in list(IBRAV_REQUIRED_PARAMETERS.keys())]

        # Lattice data
        self.cell = []
        self.latticeParameters = {}
        self.variant = ''
        # The lattice identified from the cell (lattice_data_for_cell): its ibrav,
        # and whether the points and the Brillouin zone come from the cell
        self.detectedIbrav = None
        self.cellLatticeData = None
        self.latticeFromCell = False
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
        # Automatic range: the excitons of each spectrum, plus a margin (see calculations)
        self.absorptionAutoRange = True

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
        self.wfIsoOpacity = 0.3
        self.wfIsoSetOpacity = 0.1
        self.volSliceDensity = 5
        self.volOpacity = 0.8
        self.volContrast = 1.0
        # Atoms and bonds (ball-and-stick): atoms are drawn with their covalent
        # radius times atomRadiusScale; bonds join atoms closer than
        # bondToleranceFactor times the sum of their covalent radii
        self.atomRadiusScale = 0.5
        self.bondToleranceFactor = 1.15
        self.bondRadiusAngstrom = 0.12
        self.bondColorMode = 0  # 0: half bonds in the colors of their atoms, 1: uniform grey
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
        self.datasetAboutToChange.emit()
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
        files, problems = bseFiles(dir)
        self.qPoints = list(files)
        self.nQpoints = len(self.qPoints)
        if self.nQpoints > 0:
            self.bseFiles, self.bseProblems = files, problems

        if self.nQpoints > 0 :
            self.diagoDir = dir
            self.parentDir = Path(dir).parent.absolute()
            self.jobString = PurePath(self.diagoDir).name
            status = f'BSE databases found - ({self.qPointCount()})'
            if self.qPoints != list(range(self.nQpoints)):
                status += f': {qPointNames(self.qPoints)}'
            if problems:
                status += f'; {len(problems)} file{"s" if len(problems) > 1 else ""} not used (see Check dataset)'
            self.diagoDirChanged.emit(dir, status)
            self.numQPointsChanged.emit(self.nQpoints)
            self.qPointsChanged.emit(list(self.qPoints))
        else:
            self.diagoDirChanged.emit(dir, "No BSE databases (ndb.BS_diago_Q*) found!")

    def qPointCount(self):
        """E.g. '90 Q-points', or '4 of 90 Q-points' when only some were computed."""
        if self.nIbzQpoints and self.nQpoints < self.nIbzQpoints:
            return f'{self.nQpoints} of {self.nIbzQpoints} Q-points'
        return f'{self.nQpoints} Q-point' + ('' if self.nQpoints == 1 else 's')

    def hasAllQPoints(self):
        """Whether every Q-point of the grid was computed (as the interpolated dispersion needs)."""
        return self.nIbzQpoints > 0 and self.qPoints == list(range(self.nIbzQpoints))

    def missingQPoint(self, qIndex):
        """None if Q-point `qIndex` (from 0) was computed, otherwise a message saying it was not."""
        if not self.diagoDir or qIndex in self.qPoints:
            return None
        return (f'Q-point {qIndex + 1} was not computed: there is no BSE database for it (ndb.BS_diago_Q{qIndex + 1}) '
                f'in the BSE directory (computed: {qPointNames(self.qPoints) or "none"}).')

    def setQPDir(self, dir, qpFile=None):
        """The QP directory, and the QP database used there: `qpFile` if given and found, otherwise the default."""
        databases = qpDatabases(dir)
        if databases:
            self.qpDir = dir
            self.qpDatabases = databases
            names = [info['name'] for info in databases]
            self.qpFile = qpFile if qpFile in names else names[0]
            self.qpDirChanged.emit(dir, self.qpStatus())
            self.qpDatabasesChanged.emit(databases, self.qpFile)
        else:
            self.qpDirChanged.emit(dir, "No QP database (ndb.QP) found!")

    def setQPFile(self, name):
        """Use another of the QP databases found."""
        if name in [info['name'] for info in self.qpDatabases] and name != self.qpFile:
            self.qpFile = name
            self.qpDirChanged.emit(self.qpDir, self.qpStatus())
            self.qpDatabasesChanged.emit(self.qpDatabases, self.qpFile)

    def qpStatus(self):
        info = next(info for info in self.qpDatabases if info['name'] == self.qpFile)
        count = len(self.qpDatabases)
        found = 'QP database found' if count == 1 else f'{count} QP databases found'
        return f'{found}: using {self.qpFile} (bands {info["bands"][0]}–{info["bands"][1]})'

    def bseFile(self, qIndex):
        """The BSE file of Q-point `qIndex` (from 0)."""
        return self.bseFiles.get(qIndex, f'ndb.BS_diago_Q{qIndex + 1}')

    def hasStandardBseNames(self):
        return all(name == f'ndb.BS_diago_Q{q + 1}' for q, name in self.bseFiles.items())

    def setLatticeParameters(self):
        with databaseAccess():
            lattice = YamboLatticeDB.from_db(self.saveDir + '/ns.db1', Expand=False)
        self.cell = lattice.lat
        self.latticeParameters = get_cell_params(self.cell)
        self.nIbzQpoints = int(lattice.ibz_nkpoints)
        self.detectedIbrav, self.cellLatticeData, self.latticeFromCell = None, None, False

    def detectLatticeType(self):
        """
        The ibrav of the lattice of the cell, or None. It is identified from
        the symmetry of the cell (spglib, through lattice_data_for_cell), so
        centred lattices (FCC, BCC, BCT...) are found whatever primitive
        vectors the cell has, and whatever its orientation; their special
        points are then in the reduced coordinates of the cell itself.
        """
        self.detectedIbrav, self.cellLatticeData = None, None
        try:
            _, variant, points, defaultPath = lattice_data_for_cell(np.asarray(self.cell, dtype=float))
        except ValueError:
            return None
        candidates = ibravCandidates(variant)
        if not candidates:
            return None
        # Of the orientations of the same lattice, the one of this cell if it is a standard one
        ibrav = candidates[0]
        for candidate in candidates:
            try:
                standardCell = get_lattice_data(candidate, self.latticeParameters)[0]
            except ValueError:
                continue
            if np.shape(standardCell) == np.shape(self.cell) and np.allclose(self.cell, standardCell, atol=1.0e-4, rtol=0):
                ibrav = candidate
                break
        self.detectedIbrav = ibrav
        self.cellLatticeData = (variant, points, defaultPath)
        return ibrav

    def setLatticeData(self, ibrav):
        """
        The special points and default path of lattice `ibrav`: from the cell
        if it is the lattice detected, from the lattice parameters otherwise
        (a lattice chosen by hand).
        """
        self.latticeFromCell = self.cellLatticeData is not None and ibrav == self.detectedIbrav
        if self.latticeFromCell:
            self.variant, points, self.defaultPath = self.cellLatticeData
            self.highSymmetryPoints = dict(points)
        else:
            cell, self.variant, self.highSymmetryPoints, self.defaultPath = get_lattice_data(ibrav, self.latticeParameters)
        self.availableHighSymmetryPoints = [label for label in self.highSymmetryPoints.keys()]
        # A path and extra points belong to the previous lattice: they must be set again
        self.qBZ = None
        self.extraHighSymmetryPoints = {}

    def setGW(self, gw: bool):
        if gw != self.gw:
            self.gw = gw
            self.gwChanged.emit(gw)

    def setIbrav(self, i):
        self.ibrav = i

    def setBrillouinZone(self, path: str = None, npoints: int = None, density: float = None):
        lattice = (dict(cell=np.asarray(self.cell, dtype=float)) if self.latticeFromCell and self.ibrav == self.detectedIbrav
                   else dict(ibrav=self.ibrav, parameters=self.latticeParameters))
        self.qBZ = BrillouinZone(**lattice, path_string=path, extra_points=self.extraHighSymmetryPoints, npoints=npoints,
                                 density=density)

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

    def setAbsorptionAutoRange(self, auto: bool):
        self.absorptionAutoRange = bool(auto)

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

    def setParticlePositionOf(self, particleType: str, position: list):
        if particleType == 'h':
            self.holePos = position
        elif particleType == 'e':
            self.electronPos = position

    def particlePositionCartesian(self):
        # The wave function is computed with the fixed particle in the central cell of
        # the (odd) supercell, so that is where it is shown
        return self.cell.T @ (np.asarray(self.particlePosition(), dtype=float) + np.asarray(self.scell) // 2)

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

    def atomScale(self):
        return self.atomRadiusScale

    def setAtomScale(self, scale: float):
        self.atomRadiusScale = max(scale, 0.01)

    def bondTolerance(self):
        return self.bondToleranceFactor

    def setBondTolerance(self, tolerance: float):
        self.bondToleranceFactor = max(tolerance, 0.0)

    def bondRadius(self):
        """Bond radius in angstrom."""
        return self.bondRadiusAngstrom

    def setBondRadius(self, radius: float):
        self.bondRadiusAngstrom = max(radius, 0.001)

    def bondColoring(self):
        return self.bondColorMode

    def setBondColoring(self, mode: int):
        self.bondColorMode = mode

    def isoOpacity(self):
        return self.wfIsoOpacity

    def setIsoOpacity(self, alpha: float):
        self.wfIsoOpacity = alpha

    def isoSetOpacity(self):
        return self.wfIsoSetOpacity

    def setIsoSetOpacity(self, alpha: float):
        self.wfIsoSetOpacity = alpha

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