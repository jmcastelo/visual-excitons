"""
Datasets: the directories of the databases of one calculation, and the
dataset open (Dataset).

A dataset is a SAVE directory (ns.db1), a BSE directory (ndb.BS_diago_Q*)
and, for GW calculations, a QP directory (ndb.QP, or QP databases of other
names: they are recognised by their content, see databases.py). They can be
found inside a common folder, as in data/<system>/{save, diagos, qp}.
"""

import os
from pathlib import Path, PurePath

import numpy as np
from PySide6.QtCore import QObject, Signal
from yambopy import get_lattice_data, lattice_data_for_cell, YamboLatticeDB, BrillouinZone

from .tasks import databaseAccess
from .databases import hasDatabase, qpDatabases, bseFiles, qPointNames, LATTICE, QP, BSE
from .cellshift import kGrid
from .lattice_info import (latticeSummary, cellParameters, ibravCandidates, SYMMETRY_TOLERANCES,
                           LATTICE_SYMMETRY)


# How deep to look below the chosen folder
SEARCH_DEPTH = 3


def _directoriesWith(root: Path, kind: str, depth: int):
    """Directories at most `depth` levels below `root` (included) holding databases of `kind`, shallowest first."""
    found = []
    level = [root]
    for _ in range(depth + 1):
        nextLevel = []
        for directory in level:
            try:
                if hasDatabase(directory, kind):
                    found.append(directory)
                nextLevel += sorted(child for child in directory.iterdir() if child.is_dir() and not child.name.startswith('.'))
            except OSError:
                continue
        level = nextLevel
    return found


def findDataset(folder):
    """
    Directories of the databases inside `folder` (or `folder` itself), as a
    dict with keys 'save', 'diago' and 'qp' (None when not found) and 'gw'
    (whether a QP database was found).
    """
    root = Path(folder).expanduser().resolve()
    dataset = {'save': None, 'diago': None, 'qp': None}

    saves = _directoriesWith(root, LATTICE, SEARCH_DEPTH)
    if saves:
        save = saves[0]
        dataset['save'] = str(save)
        # The other databases of the same calculation sit next to the SAVE
        # directory: look only there, so as not to mix different systems
        root = save if save == root else save.parent

    for key, kind in (('diago', BSE), ('qp', QP)):
        directories = _directoriesWith(root, kind, SEARCH_DEPTH)
        if directories:
            dataset[key] = str(directories[0])
    dataset['gw'] = dataset['qp'] is not None
    if dataset['qp']:
        # The QP database used there, by default (several may be found)
        dataset['qpFile'] = qpDatabases(dataset['qp'])[0]['name']
    return dataset


def datasetName(dataset) -> str:
    """Short name of a dataset: its common folder, e.g. BiI3_Bulk_8x8x8."""
    paths = [Path(path) for path in (dataset.get('save'), dataset.get('diago'), dataset.get('qp')) if path]
    if not paths:
        return ''
    if len(paths) == 1:
        return paths[0].parent.name or paths[0].name
    common = Path(os.path.commonpath([str(path) for path in paths]))
    return common.name or str(common)


def datasetExists(dataset) -> bool:
    return bool(dataset.get('save')) and Path(dataset['save'], 'ns.db1').is_file()


class Dataset(QObject):
    """
    The dataset open: its directories and databases, its Q-points, the lattice
    identified from its cell (special points), the Q-path set, and whether its
    calculation has GW corrections.
    """

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

        # ibrav (of the lattice detected; -1: none)
        self.ibrav = -1

        # Lattice data
        self.cell = []
        self.latticeParameters = {}
        self.variant = ''
        # The lattice identified from the cell (lattice_data_for_cell): its ibrav,
        # (variant, special points, default path), the tolerance it took, or why not
        self.detectedIbrav = None
        self.cellLatticeData = None
        self.symmetryTolerance = None
        self.strictVariant = None      # the variant at the strictest tolerance, if another
        self.latticeProblem = ''
        # The atoms of the cell (Cartesian, Bohr) and the k-point grid
        self.atomicNumbers, self.atomicPositions, self.kGrid = [], np.empty((0, 3)), None
        self.highSymmetryPoints = {}
        self.extraHighSymmetryPoints = {}
        self.availableHighSymmetryPoints = []
        self.defaultPath = ''

        # Q-Path (yet undefined)
        self.qBZ = None

        # Calculation type: DFT+GW+BSE (QP energies) or DFT+BSE
        self.gw = True

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

    def close(self):
        """
        Forget the dataset: its directories, lattice and Q-path, as before any
        was opened (the parameters of the controls are not part of it).
        """
        self.datasetAboutToChange.emit()
        self.saveDir = self.diagoDir = self.qpDir = self.qpFile = ''
        self.qpDatabases, self.bseFiles, self.bseProblems = [], {}, []
        self.parentDir = self.jobString = ''
        self.nQpoints, self.qPoints, self.nIbzQpoints = 0, [], 0
        self.ibrav = -1
        self.cell, self.latticeParameters, self.variant = [], {}, ''
        self.detectedIbrav, self.cellLatticeData, self.symmetryTolerance, self.latticeProblem = None, None, None, ''
        self.strictVariant = None
        self.atomicNumbers, self.atomicPositions, self.kGrid = [], np.empty((0, 3)), None
        self.highSymmetryPoints, self.extraHighSymmetryPoints, self.availableHighSymmetryPoints = {}, {}, []
        self.defaultPath = ''
        self.qBZ = None
        self.saveDirChanged.emit('', 'ns.db1 not found!')
        self.diagoDirChanged.emit('', 'No BSE databases (ndb.BS_diago_Q*) found!')
        self.qpDirChanged.emit('', 'No QP database (ndb.QP) found!')
        self.qpDatabasesChanged.emit([], '')
        self.numQPointsChanged.emit(0)
        self.qPointsChanged.emit([])
        self.databaseFound.emit(False)

    def setDiagoDir(self, dir):
        files, problems = bseFiles(dir)
        # A folder without BSE databases changes nothing (the directory in use stays)
        if files:
            self.qPoints = list(files)
            self.nQpoints = len(self.qPoints)
            self.bseFiles, self.bseProblems = files, problems
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
        self.latticeParameters = cellParameters(self.cell)
        self.nIbzQpoints = int(lattice.ibz_nkpoints)
        self.atomicNumbers = [int(z) for z in lattice.atomic_numbers]
        self.atomicPositions = np.asarray(lattice.car_atomic_positions, dtype=float)[:len(self.atomicNumbers)]
        # From the irreducible k-points (they have the grid's steps): no expansion needed
        self.kGrid = kGrid(lattice)
        self.detectedIbrav, self.cellLatticeData, self.symmetryTolerance, self.latticeProblem = None, None, None, ''

    def detectLatticeType(self):
        """
        The ibrav of the lattice of the cell, or None. It is identified from
        the symmetry of the cell (spglib, through lattice_data_for_cell), so
        centred lattices (FCC, BCC, BCT...) are found whatever primitive
        vectors the cell has, and whatever its orientation; their special
        points are then in the reduced coordinates of the cell itself. Of the
        SYMMETRY_TOLERANCES, the most symmetric lattice found is taken, with
        the strictest tolerance giving it (symmetryTolerance; strictVariant:
        what the strictest gave, if different); latticeProblem says why none was.
        """
        self.detectedIbrav, self.cellLatticeData, self.symmetryTolerance, self.latticeProblem = None, None, None, ''
        self.strictVariant = None
        found = []
        for tolerance in SYMMETRY_TOLERANCES:
            try:
                _, variant, points, defaultPath = lattice_data_for_cell(np.asarray(self.cell, dtype=float),
                                                                        symprec=tolerance)
            except ValueError as error:
                self.latticeProblem = str(error)
                continue
            family = variant.rstrip('0123456789')
            if not ibravCandidates(variant):
                self.latticeProblem = f'lattice variant {variant} not supported'
                continue
            found.append((LATTICE_SYMMETRY.get(family, 0), tolerance, variant, points, defaultPath))
        if not found:
            return None
        best = max(found, key=lambda entry: (entry[0], -entry[1]))
        _, tolerance, variant, points, defaultPath = best
        if found[0][1] == SYMMETRY_TOLERANCES[0] and found[0][2] != variant:
            self.strictVariant = found[0][2]
        self.symmetryTolerance, self.latticeProblem = tolerance, ''
        candidates = ibravCandidates(variant)
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

    def identifyLattice(self):
        """Detect the lattice and take its special points; its ibrav, or None (latticeProblem says why)."""
        ibrav = self.detectLatticeType()
        self.ibrav = ibrav if ibrav is not None else -1
        if ibrav is None:
            self.variant, self.highSymmetryPoints, self.defaultPath = '', {}, ''
            self.availableHighSymmetryPoints, self.qBZ, self.extraHighSymmetryPoints = [], None, {}
            return None
        self.setLatticeData()
        return ibrav

    def setLatticeData(self):
        """The special points and default path of the lattice detected, in the cell's reduced coordinates."""
        if self.cellLatticeData is None:
            raise ValueError('The lattice of the cell was not identified.')
        self.variant, points, self.defaultPath = self.cellLatticeData
        self.highSymmetryPoints = dict(points)
        self.availableHighSymmetryPoints = [label for label in self.highSymmetryPoints.keys()]
        # A path and extra points belong to the previous lattice: they must be set again
        self.qBZ = None
        self.extraHighSymmetryPoints = {}

    def setGW(self, gw: bool):
        if gw != self.gw:
            self.gw = gw
            self.gwChanged.emit(gw)

    def setBrillouinZone(self, path: str = None, npoints: int = None, density: float = None):
        if self.cellLatticeData is None:
            raise ValueError('The lattice of the cell was not identified: no Q-path can be set.')
        self.qBZ = BrillouinZone(cell=np.asarray(self.cell, dtype=float), path_string=path, extra_points=self.extraHighSymmetryPoints, npoints=npoints,
                                 density=density)

    def latticeSummary(self):
        """The crystal's description for the System panel (see lattice_info.latticeSummary), or None."""
        if not self.hasCell():
            return None
        return latticeSummary(self.cell, self.atomicNumbers, self.atomicPositions, self.kGrid,
                              self.symmetryTolerance or SYMMETRY_TOLERANCES[0])

    def pathString(self):
        return self.qBZ.path_string

    def hasCell(self):
        return len(self.cell) > 0
