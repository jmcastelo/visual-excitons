from PySide6.QtCore import QObject, Signal, Slot
from yambopy import YamboLatticeDB, ExcitonDispersion, YamboExcitonDB, YamboBSEAbsorptionSpectra, YamboQPDB
from yambopy import YamboElectronsDB, YamboWFDB, ex_wf2Real
import numpy as np
from pathlib import Path

from .databases import qPointNames
from .dataset import Dataset
from .parameters import SpectraParameters
from .tasks import TaskRunner, databaseAccess, DATABASE_LOCK
from .memory import PlaneWaves, estimateMemory, chooseBlockSize, availableMemory
from .export import supercellAtoms, writeDensity
from .analysis import voxelVectors
from .atomic_data import BOHR_TO_ANGSTROM
from visual_excitons.yambopy_ext.bse.exciton_kspace import exciton_kspace
from visual_excitons.yambopy_ext.bse.exciton_bands import interpolate_exciton_bands, band_energies_ibz
from visual_excitons.yambopy_ext.dbs.qp_energies import qp_energies
from visual_excitons.yambopy_ext.bse.exciton_particle_density import exciton_particle_density, density_maxima

# States within this energy (eV) of an exciton are degenerate with it (summed with it when
# Calculations.sumDegenerate: wave function, composition, band structure)
DEGENERACY_EV = 1e-2



class PointData:
    """A plotted exciton: its point i of the Q-path, its index j (from 1), and its Q-point q if not on the path."""

    def __init__(self, i, j, q=None):
        self.i = i
        self.j = j
        self.q = q


# Calculations proper. They run in the worker thread (see tasks.py): they only
# use their arguments, never the state shared with the GUI.

def computeDispersion(context, saveDir, diagoDir, nExcitons, qBZ, qPoints, bseFiles=None):
    """
    The excitonic dispersion along the Q-path. With every Q-point of the grid
    computed, through yambopy's ExcitonDispersion, interpolated; with only some
    (`qPoints`, indices from 0), the computed Q-points on the path, not
    interpolated (the interpolation needs them all), and a note saying so.
    `bseFiles` (Q-point index -> file name) gives the files of other names;
    ExcitonDispersion only reads the standard ones.
    """
    bseFiles = bseFiles or {}
    standardNames = all(bseFiles.get(q, f'ndb.BS_diago_Q{q + 1}') == f'ndb.BS_diago_Q{q + 1}' for q in qPoints)
    context.stage('Loading the lattice')
    lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')
    collinearQPoints, qIndices, x = qBZ.find_collinear_grid(lattice)
    collinearQPoints, qIndices, x = np.asarray(collinearQPoints), np.asarray(qIndices), np.asarray(x)
    nIbz = int(lattice.ibz_nkpoints)
    note = ''

    if list(qPoints) == list(range(nIbz)) and standardNames:
        # One exciton database per Q-point (counted by the progress hooks)
        context.stage('Loading the excitons of each Q-point', nIbz)
        excitonDispersion = ExcitonDispersion(lattice, nExcitons, diagoDir)
        y = excitonDispersion.exc_energies[qIndices]
        context.stage('Interpolating along the Q-path')
        xInter, yInter = excitonDispersion.interpolate_dispersion(qBZ) if nIbz > 1 else ([], [])
    else:
        computed = set(qPoints)
        onPath = np.array([q in computed for q in qIndices], dtype=bool)
        if not onPath.any():
            raise ValueError(f'None of the computed Q-points ({qPointNames(qPoints)}) is on the Q-path. Choose a path '
                             'through them, or show their absorption spectra from the Spectra controls.')
        collinearQPoints, qIndices, x = collinearQPoints[onPath], qIndices[onPath], x[onPath]
        distinct = sorted(set(int(q) for q in qIndices))
        context.stage('Loading the excitons of each Q-point', len(distinct))
        energies = {}
        for q in distinct:
            excitonDB = YamboExcitonDB.from_db_file(lattice, filename=bseFiles.get(q, 'ndb.BS_diago_Q%d' % (q + 1)),
                                                    folder=diagoDir, neigs=nExcitons)
            energies[q] = np.asarray(excitonDB.eigenvalues.real[:nExcitons])
            context.advance()
        count = min(len(values) for values in energies.values())
        y = np.array([energies[int(q)][:count] for q in qIndices])
        excitonDispersion, xInter, yInter = None, [], []
        if len(distinct) == len(qPoints):
            shown = 'it' if len(distinct) == 1 else 'them'
        else:
            shown = f'those on the path ({qPointNames(distinct)})'
        if list(qPoints) == list(range(nIbz)):
            note = ('Every Q-point was computed, but some BSE databases have other names than ndb.BS_diago_Q<n>: the '
                    'dispersion is not interpolated (yambopy reads the standard names only).')
        else:
            note = (f'Only {qPointNames(qPoints)} computed ({len(qPoints)} of the {nIbz} Q-points of the grid): the '
                    f'dispersion shows {shown}, not interpolated (that needs every Q-point).')
        if len(distinct) < len(qPoints):
            note += ' The spectra of the others can be added from the Absorption section.'

    return {
        'lattice': lattice,
        'excitonDispersion': excitonDispersion,
        'collinearQPoints': collinearQPoints,
        'qIndices': qIndices,
        'points': [[[x[i], y[i][j]] for i in range(len(x))] for j in range(y.shape[1])],
        'pointsData': [[PointData(i, j + 1) for i in range(len(x))] for j in range(y.shape[1])],
        'xInter': xInter,
        'yInter': yInter,
        'xRange': (float(qBZ.kpoints_distances()[0]), float(qBZ.kpoints_distances()[-1])) if note else (min(x), max(x)),
        'yRange': (np.array(y).min(), np.array(y).max()),
        'specialPoints': qBZ.special_kpoints_distances(merge_sections=True),
        'labels': qBZ.path_labels_list(merge_sections=True),
        'note': note,
        'qPointCount': len(set(int(q) for q in qIndices)),
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
                      autoRange=False, bseFiles=None):
    filename = (bseFiles or {}).get(qPointIndex, "ndb.BS_diago_Q%d" % (qPointIndex + 1))
    if not (Path(diagoDir) / filename).is_file():
        raise ValueError(f'Q-point {qPointIndex + 1} was not computed: there is no BSE database for it ({filename}) '
                         'in the BSE directory.')
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
        pointsData = [PointData(index, int(j), q=qPointIndex) for j in brightExcitons[:, 2]]

    return {'q': qPointIndex, 'index': index, 'energy': energyRange, 'absorption': epsilon.imag,
            'brightExcEnergy': brightExcitons[:, 0], 'brightExcAbsorption': brightExcAbsInterp,
            'brightExcIntensities': brightExcitons[:, 1], 'brightExcIndices': brightExcitons[:, 2],
            'darkExcEnergy': darkExcitons[:, 0], 'data': pointsData, 'range': (energyMin, energyMax)}


def computeBandStructure(context, lattice, saveDir, diagoDir, bseFile, qIndex, excitonIndices, degenerate, qBZ,
                         gw=False, qpDir=None, qpFile=None):
    """
    The excitonic band structure of excitons `excitonIndices` (1-based) of
    Q-point `qIndex` (0-based, the file `bseFile`), along the Q-path `qBZ`:
    the hole's weights on the valence bands (at k-Q), the electron's on the
    conduction bands (at k), on DFT or QP energies (see
    yambopy_ext.bse.exciton_bands, which explains the interpolation).
    """
    if lattice is None:
        context.stage('Loading the lattice')
        lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')
    context.stage('Loading the databases')
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename=bseFile, folder=diagoDir,
                                            neigs=max(excitonIndices) + 20)
    missing = [i for i in excitonIndices if i > len(excitonDB.eigenvalues)]
    if missing:
        raise ValueError(f'Exciton {missing[0]} does not exist: {bseFile} has {len(excitonDB.eigenvalues)} excitons')
    electrons = YamboElectronsDB.from_db_file(folder=saveDir)
    # QP energies with GW and a QP database; DFT otherwise
    qpPath = Path(qpDir) / (qpFile or 'ndb.QP') if gw and qpDir else None
    gw = qpPath is not None and qpPath.is_file()
    qp = qp_energies(str(qpPath)) if gw else None
    first, last = int(excitonDB.start_band) + 1, int(excitonDB.mband)
    energies, estimated = band_energies_ibz(electrons.eigenvalues_ibz[0], first, last, qp)

    context.stage('Interpolating the bands')
    result = interpolate_exciton_bands(excitonDB, qBZ.kpoints('red'), excitonIndices, energies,
                                       degenerate=degenerate, degen_eps=DEGENERACY_EV)
    return {'lattice': lattice, 'k': qBZ.kpoints_distances(), 'bands': np.transpose(result['energies']),
            'weights': np.transpose(result['weights']),
            'info': {'qIndex': int(qIndex), 'states': result['states'], 'clicked': [int(i) for i in excitonIndices],
                     'degenerate': bool(degenerate), 'redQPoint': [float(x) for x in result['red_qpoint']],
                     'bands': list(result['bands']), 'estimatedBands': estimated, 'gw': bool(gw),
                     'energyInterpolation': result['energy_interpolation']}}


def loadWavefunctionDB(cache, saveDir, lattice, excitonDB):
    """
    The wave functions of the bands of the BSE of `excitonDB`, kept in `cache`
    (a dict) for the next calculation that needs them (wave function, symmetry
    and spin): one database at a time, they are large.
    """
    bandsRange = [int(np.min(excitonDB.table[:, 1])) - 1, int(np.max(excitonDB.table[:, 2]))]
    key = (saveDir, tuple(bandsRange))
    if cache is not None and key in cache:
        return cache[key]
    if cache is not None:
        # Free the previous one before loading, not after
        cache.clear()
    wavefunctionDB = YamboWFDB(path=saveDir, save='.', latdb=lattice, bands_range=bandsRange)
    if cache is not None:
        cache[key] = wavefunctionDB
    return wavefunctionDB


# Spin axes offered: Cartesian, or the lattice's third vector (the layer normal of a layer along c)
SPIN_AXES = ('z', 'x', 'y', 'c')

# Degenerate states for the symmetry analysis: within 1 meV (the 10 meV of DEGENERACY_EV
# lumps nearby states into groups that are not irreducible)
SYMMETRY_DEGENERACY_EV = 1e-3


# Seconds per k-point of the full grid and per symmetry to compute the electronic
# representation matrices (measured: 0.023 for BiI3 8x8x8, 0.018 for WSe2 72x72x1)
DMAT_SECONDS_PER_KPOINT = 0.02


def symmetryCacheKey(saveDir, firstBand, lastBand, rotations):
    """A name for the representation matrices of a dataset, its bands and its symmetries, for the disk cache."""
    import hashlib
    digest = hashlib.sha1()
    for name in ('ns.db1', 'ns.wf'):
        path = Path(saveDir) / name
        stat = path.stat() if path.exists() else None
        digest.update(f'{path.resolve()}|{stat.st_size if stat else 0}|{stat.st_mtime_ns if stat else 0}'.encode())
    digest.update(f'{firstBand}-{lastBand}'.encode())
    digest.update(np.round(np.asarray(rotations, dtype=float), 6).tobytes())
    return digest.hexdigest()[:20]


def computeCharacter(context, lattice, saveDir, diagoDir, bseFile, qIndex, excIndex, axis='z', wavefunctionCache=None,
                     symmetryCache=None, diskCache=None):
    """
    The symmetry (irreducible representation of the little group of Q) and the
    spin along `axis` of the degenerate group of exciton `excIndex` (1-based)
    of Q-point `qIndex` (0-based), from the wave functions (see
    yambopy_ext.bse.exciton_symmetry and exciton_spin).

    `symmetryCache`, a dict, keeps the crystal's symmetries and the electronic
    representation matrices computed (they serve every Q-point of the dataset);
    `diskCache`, a folder, keeps the matrices between sessions (they take about
    DMAT_SECONDS_PER_KPOINT per k-point and symmetry: minutes for dense grids).
    """
    from visual_excitons.yambopy_ext.bse.exciton_symmetry import crystal_symmetries, degenerate_groups, exciton_irreps
    from visual_excitons.yambopy_ext.bse.exciton_spin import exciton_spin, spin_operator, spin_matrix_elements
    if lattice is None:
        context.stage('Loading the lattice')
        lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')
    context.stage('Loading the exciton')
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename=bseFile, folder=diagoDir, neigs=excIndex + 20)
    if excIndex > len(excitonDB.eigenvalues):
        raise ValueError(f'Exciton {excIndex} does not exist: {bseFile} has {len(excitonDB.eigenvalues)} excitons')
    groups = degenerate_groups(np.real(excitonDB.eigenvalues), atol=SYMMETRY_DEGENERACY_EV, rtol=0)
    group = next(g for g in groups if excIndex in g)
    if group[-1] == len(excitonDB.eigenvalues):
        # The group may go on beyond the states read: read more
        excitonDB = YamboExcitonDB.from_db_file(lattice, filename=bseFile, folder=diagoDir, neigs=excIndex + 100)
        groups = degenerate_groups(np.real(excitonDB.eigenvalues), atol=SYMMETRY_DEGENERACY_EV, rtol=0)
        group = next(g for g in groups if excIndex in g)
    context.stage('Loading the wave functions')
    wavefunctionDB = loadWavefunctionDB(wavefunctionCache, saveDir, lattice, excitonDB)

    result = {'lattice': lattice, 'qIndex': int(qIndex), 'excIndex': int(excIndex), 'states': group,
              'energy': float(np.mean(np.real(excitonDB.eigenvalues)[np.array(group) - 1])), 'axis': axis,
              'notes': []}
    car_q = np.zeros(3) if excitonDB.car_qpoint is None else np.asarray(excitonDB.car_qpoint, dtype=float)
    red_q = np.linalg.solve(np.asarray(lattice.rlat, dtype=float).T, car_q)
    result['redQPoint'] = [float(x) for x in red_q]
    gamma = np.allclose(red_q - np.round(red_q), 0.0, atol=1e-6)
    kind = (excitonDB.Lkind or '').lower()
    if kind and gamma and 'bar' not in kind:
        result['notes'].append(f'The BSE kernel is {excitonDB.Lkind} at Γ, where Lbar is recommended: '
                               'Lfull breaks symmetries, so the labels may not hold.')
    if kind and not gamma and 'full' not in kind:
        result['notes'].append(f'The BSE kernel is {excitonDB.Lkind} at a finite Q, where Lfull should be used.')

    # Symmetry
    context.stage('Analysing the symmetry')
    # The representation matrices depend on the dataset and the bands of the BSE, not on Q
    key = (saveDir, int(np.min(excitonDB.table[:, 1])), int(np.max(excitonDB.table[:, 2])))
    cached = symmetryCache.get(key) if symmetryCache is not None else None
    if cached is None:
        cached = {'symmetries': crystal_symmetries(lattice), 'dmats': {}}
        if symmetryCache is not None:
            symmetryCache.clear()
            symmetryCache[key] = cached
    # The matrices of earlier sessions
    folder = Path(diskCache) if diskCache else None
    name = symmetryCacheKey(saveDir, key[1], key[2], cached['symmetries'][0]) if folder else None
    if folder is not None and folder.is_dir():
        for path in folder.glob(f'dmat_{name}_*.npy'):
            isym = int(path.stem.rsplit('_', 1)[1])
            if isym not in cached['dmats']:
                try:
                    cached['dmats'][isym] = np.load(path)
                except (OSError, ValueError):
                    pass
    before = set(cached['dmats'])
    try:
        irreps = exciton_irreps(excitonDB, wavefunctionDB, [group], symmetries=cached['symmetries'],
                                dmats=cached['dmats'])
        result['pointGroup'] = irreps['point_group']
        result['operations'] = len(irreps['operations'])
        entry = irreps['groups'][0]
        result['irreps'] = entry.get('irreps')
        result['irrepsError'] = entry.get('error')
    except (NotImplementedError, ValueError) as error:
        result['pointGroup'], result['irreps'], result['irrepsError'] = None, None, str(error)
    if folder is not None:
        for isym in set(cached['dmats']) - before:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                np.save(folder / f'dmat_{name}_{isym}.npy', cached['dmats'][isym])
            except OSError:
                break                       # no cache then: computed again next time

    # Spin (spinor wave functions only)
    if wavefunctionDB.nspinor == 2:
        context.stage('Computing the spin')
        direction = (np.asarray(lattice.lat, dtype=float)[2] if axis == 'c'
                     else np.eye(3)[{'x': 0, 'y': 1, 'z': 2}[axis]])
        spin = exciton_spin(excitonDB, wavefunctionDB, [group], direction=direction,
                            matrix_elements=spin_matrix_elements(wavefunctionDB, spin_operator(direction)))[0]
        result['spin'] = {k: spin[k] for k in ('total', 'electron', 'hole')}
    else:
        result['spin'] = None
        result['notes'].append('Without spin-orbit coupling (no spinor wave functions), spin is not resolved this '
                               'way: each band holds both spins.')
    return result


def jsonableCharacter(character):
    """The symmetry and spin of computeCharacter, for a session file."""
    keys = ('qIndex', 'excIndex', 'states', 'energy', 'axis', 'notes', 'redQPoint', 'pointGroup', 'operations',
            'irreps', 'irrepsError', 'spin')
    return {key: character.get(key) for key in keys}


def computeComposition(context, lattice, saveDir, diagoDir, bseFile, qIndex, excIndex, degenerate, cache=None):
    """
    Where exciton `excIndex` (1-based) of Q-point `qIndex` (0-based) lives in
    reciprocal space and what it is made of (see yambopy_ext.bse.exciton_kspace),
    with the states degenerate with it if `degenerate`.

    `cache`, a dict, keeps the BSE database read (with the states up to the
    one asked plus a margin): another exciton of the same Q-point is instant.
    """
    if lattice is None:
        context.stage('Loading the lattice')
        lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')
    neigs = excIndex + 20       # the states degenerate with it, at most a few above
    key = (diagoDir, bseFile)
    cached = cache.get(key) if cache is not None else None
    if cached is not None and cached[1] >= neigs:
        excitonDB = cached[0]
    else:
        context.stage('Loading the exciton')
        excitonDB = YamboExcitonDB.from_db_file(lattice, filename=bseFile, folder=diagoDir, neigs=neigs)
        if cache is not None:
            cache.clear()       # one database at a time
            cache[key] = (excitonDB, neigs)
    if excIndex > len(excitonDB.eigenvalues):
        raise ValueError(f'Exciton {excIndex} does not exist: {bseFile} has {len(excitonDB.eigenvalues)} excitons')
    # The same degeneracy as the wave function's (computeWaveFunction)
    result = exciton_kspace(excitonDB, excIndex, degenerate=degenerate, degen_eps=DEGENERACY_EV)
    result.update(lattice=lattice, qIndex=qIndex, excIndex=excIndex, degenerate=bool(degenerate))
    return result


def computeWaveFunction(context, lattice, saveDir, diagoDir, q_index, exc_index, fixed_particle, fixed_position,
                        cutoff_ry, supercell, cache=None, block_size=256, bseFile=None, degenerate=True):
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
    filename = bseFile or 'ndb.BS_diago_Q%d' % (q_index + 1)
    # Load the states up to the requested one, plus a margin for the states
    # degenerate with it
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename=filename, folder=diagoDir, neigs=exc_index + 20)
    numStates = len(excitonDB.eigenvalues)
    if exc_index > numStates:
        raise ValueError(f'Exciton {exc_index} does not exist: {filename} has {numStates} excitons')

    # Loading the wave functions and the real-space calculation report their own
    # stages and progress (tqdm hooks)
    wavefunctionDB = loadWavefunctionDB(cache, saveDir, lattice, excitonDB)

    # With the states degenerate with it (their densities summed), or alone
    states = excitonDB.get_degenerate(exc_index, eps=DEGENERACY_EV) if degenerate else [exc_index]
    degen_states = np.array(states) - 1
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
        wfcCutoffRy=cutoff_ry, block_size=block_size)

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
        'states': [int(s) for s in states],
        'degenerate': bool(degenerate),
    }


# The NTO weight kept for the particle densities (the density dropped integrates to the rest)
PARTICLE_DENSITY_WEIGHT = 0.999
# Local maxima of a particle density reported: at least this share of the largest
PARTICLE_MAXIMA_THRESHOLD = 0.1


def computeParticleDensity(context, lattice, saveDir, diagoDir, bseFile, qIndex, excIndex, particle, cutoff_ry,
                           degenerate=True, cache=None):
    """
    The own density of the hole or of the electron (`particle`, 'h' or 'e') of
    exciton `excIndex` (1-based, with its degenerate states if `degenerate`)
    at Q-point `qIndex` (0-based), on the unit-cell grid the wave function
    uses at `cutoff_ry` (-1: all plane waves): see
    yambopy_ext.bse.exciton_particle_density. `cache` is the wave functions'
    (see loadWavefunctionDB).
    """
    if lattice is None:
        context.stage('Loading the lattice')
        lattice = YamboLatticeDB.from_db(saveDir + '/ns.db1')
    context.stage('Loading the exciton')
    excitonDB = YamboExcitonDB.from_db_file(lattice, filename=bseFile, folder=diagoDir, neigs=excIndex + 20)
    if excIndex > len(excitonDB.eigenvalues):
        raise ValueError(f'Exciton {excIndex} does not exist: {bseFile} has {len(excitonDB.eigenvalues)} excitons')
    wavefunctionDB = loadWavefunctionDB(cache, saveDir, lattice, excitonDB)
    states = excitonDB.get_degenerate(excIndex, eps=DEGENERACY_EV) if degenerate else [excIndex]
    Akcv = excitonDB.get_Akcv()[np.array(states) - 1]
    Qpt = wavefunctionDB.ydb.lat @ excitonDB.car_qpoint
    bands = [int(np.min(excitonDB.table[:, 1])), int(np.max(excitonDB.table[:, 2]))]
    name = 'hole' if particle == 'h' else 'electron'
    context.stage(f'Computing the {name} density', Akcv.shape[3])
    density, info = exciton_particle_density(Akcv, Qpt, wavefunctionDB, bands, particle, cutoff_ry,
                                             PARTICLE_DENSITY_WEIGHT, progress=context.advance)
    indices, values = density_maxima(density, PARTICLE_MAXIMA_THRESHOLD)
    return {'lattice': lattice, 'density': density.astype(np.float32), 'particle': particle, 'qIndex': qIndex,
            'excIndex': excIndex, 'states': [int(x) for x in states], 'degenerate': bool(degenerate),
            'cutoff': float(cutoff_ry), 'maxima': indices.tolist(), 'weightKept': info['weight_kept'] / info['weight']}


class Calculations(QObject):
    # The results changed: computed, restored, cleared...
    resultsChanged = Signal()
    qPathReady = Signal(list, list)

    excitonDispersionReady = Signal(list, list, list, list)
    excitonDispersionRange = Signal(tuple, tuple)
    excitonDispersionNumCurvesChanged = Signal(int)
    # About the dispersion shown, e.g. only some Q-points computed ('' if nothing to say)
    dispersionNoteChanged = Signal(str)
    # Distinct Q-points in the dispersion shown (1: e.g. only Γ computed)
    dispersionQPointCountChanged = Signal(int)
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
    # The composition of the selected exciton (a dict, see computeComposition), or None
    compositionReady = Signal(object)
    # Why the composition of the selected exciton cannot be shown (e.g. its Q-point was not computed)
    compositionFailed = Signal(str)
    # The symmetry and spin of an exciton (a dict, see computeCharacter), or None
    characterReady = Signal(object)
    # The own density of the fixed particle (see computeParticleDensity), or None when cleared
    particleDensityReady = Signal(object)

    # Progress and errors of the background calculations (see tasks.py)
    busyStarted = Signal(str)          # a task starts: its message
    busyFinished = Signal()            # a task finished, failed or was cancelled
    busyChanged = Signal(bool)         # whether any task is running or queued
    progressChanged = Signal(int, int, str)  # done, total (0: unknown), stage
    taskCancelled = Signal(str)
    errorOccurred = Signal(str, str)   # title, message
    # Whether the states degenerate with the selected exciton are summed with it
    # (its wave function, composition and band structure)
    sumDegenerateChanged = Signal(bool)

    def __init__(self, dataset=None, spectraParameters=None, synchronous=False):
        """
        The calculations on `dataset` (a core.dataset.Dataset), with the
        parameters of the spectra (core.parameters.SpectraParameters); new
        ones if not given (tests). `synchronous`: run the calculations in the
        calling thread (tests).
        """
        super().__init__()

        self.dataset = dataset if dataset is not None else Dataset()
        self.spectraParameters = spectraParameters if spectraParameters is not None else SpectraParameters()
        self.sumDegenerate = True

        self.tasks = TaskRunner(synchronous, self)
        self.tasks.started.connect(self.busyStarted)
        self.tasks.finished.connect(self.busyFinished)
        self.tasks.busyChanged.connect(self.busyChanged)
        self.tasks.progress.connect(self.progressChanged)
        self.tasks.cancelled.connect(self.taskCancelled)
        self.tasks.failed.connect(self.errorOccurred)
        # Calculations on the previous dataset are pointless: stop them before it changes
        self.dataset.datasetAboutToChange.connect(self.tasks.reset)

        self.dispPoints = []
        self.dispPointsData = []
        self.dispXInter = []
        self.dispYInter = []
        self.dispersionAxes = {}

        self.excAbsData = []
        # Increased with every change of the results (for "unsaved changes")
        self.resultsVersion = 0
        self.restoringResults = False
        self.showExcitonLabels = False

        self.k = []
        self.bands = []
        self.weights = []
        self.weightFactor = 1.0

        self.lattice = None
        self.excitonDispersion = None
        self.collinear_qpoints = None
        self.qIndices = None

        # The composition of the selected exciton (see computeComposition), and
        # the BSE database it was read from
        self.composition = None
        self.compositionCache = {}
        # The symmetry and spin of an exciton (see computeCharacter), and the crystal's
        # symmetries and representation matrices computed for it (kept for other Q-points)
        self.character = None
        # The own density of a particle (a dict, see computeParticleDensity), or None
        self.particleDensity = None
        self.symmetryCache = {}
        # Where the representation matrices are kept between sessions (None: not kept)
        self.diskCacheFolder = None

        self.waveFunction = None
        self.wfAtomPositions = None
        # Effective parameters of the last wave function (see computeWaveFunction)
        self.wfFixedParticle = None
        self.wfFixedPosition = None
        self.wfSupercell = None
        self.wfGrid = None
        self.wfExciton = None  # (q index, exciton index)
        self.wfStates = None   # the states summed (1-based), and whether those degenerate were asked
        self.wfDegenerate = None
        # The band structure: the excitons last clicked (q index, indices), and what is shown
        self.bandStructureSelection = None
        self.bandStructureInfo = None
        self.tr4x4 = np.eye(4, dtype=float)

        self.selectedExciton = None  # (q index, exciton index, energy)

        # Wave-function database kept between calculations (see computeWaveFunction);
        # only used from the worker thread
        self.wavefunctionCache = {}
        # For the estimates of size (see estimateWaveFunction)
        self.planeWaves = None
        self.excitonSizes = {}

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

    def markResultsChanged(self):
        """Note a change of the results (emitted at its start: listeners check them later)."""
        self.resultsVersion += 1
        self.resultsChanged.emit()

    @Slot()
    def resetSpectra(self):
        """
        Forget the dispersion, absorption spectra, band structure and selected
        exciton, e.g. when the QP corrections change their energies (the wave
        function stays: it does not depend on them).
        """
        self.markResultsChanged()
        self.tasks.reset()
        self.excitonDispersion = None
        self.collinear_qpoints = None
        self.qIndices = None
        self.selectedExciton = None
        self.clearAbsorptionCurves()
        self.excitonAbsorptionClear.emit()
        self.dispPoints, self.dispPointsData, self.dispXInter, self.dispYInter = [], [], [], []
        self.emitExcitonDispersionReady()
        self.dispersionNoteChanged.emit('')
        self.k, self.bands, self.weights = [], [], []
        self.bandStructureSelection = self.bandStructureInfo = None
        self.excitonBandStructureClear.emit()
        # It goes with the selected exciton
        if self.composition is not None:
            self.composition = None
            self.compositionReady.emit(None)

    def hasResults(self):
        """Whether anything was computed: dispersion, absorption spectra, band structure or wave function."""
        return bool(len(self.dispPoints) or self.excAbsData or len(self.k) or self.waveFunction is not None)

    @Slot()
    def resetDataset(self):
        """Forget everything computed from the previous dataset."""
        self.resetSpectra()
        self.lattice = None
        self.waveFunction = None
        self.wfAtomPositions = None
        self.compositionCache = {}
        self.symmetryCache = {}
        if self.character is not None:
            self.character = None
            self.characterReady.emit(None)
        if self.particleDensity is not None:
            self.particleDensity = None
            self.particleDensityReady.emit(None)
        # A new dict: a task still running on the old dataset keeps the old one
        self.wavefunctionCache = {}
        self.planeWaves = None
        self.excitonSizes = {}

    # Composition of the selected exciton

    @Slot(bool)
    def setSumDegenerate(self, sum):
        if bool(sum) != self.sumDegenerate:
            self.sumDegenerate = bool(sum)
            self.sumDegenerateChanged.emit(self.sumDegenerate)

    def compositionMatches(self, degenerate):
        """Whether the composition shown is that of the selected exciton, with `degenerate` as asked."""
        c, selected = self.composition, self.selectedExciton
        return (c is not None and selected is not None and (c['qIndex'], c['excIndex']) == tuple(selected[:2])
                and c['degenerate'] == bool(degenerate))

    def computeComposition(self, degenerate=True):
        """The composition of the selected exciton, in the background (compositionReady when done)."""
        if self.selectedExciton is None:
            if self.composition is not None:
                self.composition = None
                self.compositionReady.emit(None)
            return
        if self.compositionMatches(degenerate) or not self.dataset.saveDir or not self.dataset.diagoDir:
            return
        qIndex, excIndex, _ = self.selectedExciton
        # Computed when an exciton is selected: problems are said in its panel, not in a dialog
        missing = self.dataset.missingQPoint(qIndex)
        if missing:
            return self._failComposition(missing)
        o = self.dataset
        arguments = dict(lattice=self.lattice, saveDir=o.saveDir, diagoDir=o.diagoDir, bseFile=o.bseFile(qIndex),
                         qIndex=qIndex, excIndex=excIndex, degenerate=degenerate, cache=self.compositionCache)

        def compute(context):
            try:
                return computeComposition(context, **arguments)
            except ValueError as error:          # e.g. an exciton beyond those of the database
                return {'error': str(error)}
        self.tasks.submit('Analysing the exciton…', compute, self._applyComposition, key='composition')

    # Symmetry and spin of the selected exciton (on request: they need the wave functions)

    def characterMatches(self):
        """Whether the symmetry and spin shown are those of the selected exciton."""
        c, selected = self.character, self.selectedExciton
        return c is not None and selected is not None and (c['qIndex'], c['excIndex']) == tuple(selected[:2])

    def computeCharacter(self, axis='z'):
        """The symmetry and spin along `axis` of the selected exciton, in the background."""
        if self.selectedExciton is None or not self.dataset.saveDir or not self.dataset.diagoDir:
            return
        qIndex, excIndex, _ = self.selectedExciton
        missing = self.dataset.missingQPoint(qIndex)
        if missing:
            return self._reject('Analysing the symmetry and spin…', missing)
        o = self.dataset
        arguments = dict(lattice=self.lattice, saveDir=o.saveDir, diagoDir=o.diagoDir, bseFile=o.bseFile(qIndex),
                         qIndex=qIndex, excIndex=excIndex, axis=axis, wavefunctionCache=self.wavefunctionCache,
                         symmetryCache=self.symmetryCache,
                         diskCache=str(Path(self.diskCacheFolder) / 'symmetry') if self.diskCacheFolder else None)
        self.tasks.submit('Analysing the symmetry and spin…', lambda context: computeCharacter(context, **arguments),
                          self._applyCharacter, key='character')

    def _applyCharacter(self, result):
        self.markResultsChanged()
        if self.lattice is None:
            self.lattice = result['lattice']
        self.character = {key: value for key, value in result.items() if key != 'lattice'}
        self.characterReady.emit(self.character)

    # The own density of the fixed particle (on request: it needs the wave functions)

    def computeParticleDensity(self, qIndex, excIndex, particle, cutoff):
        """
        The density of the hole or of the electron (`particle`) of exciton
        `excIndex` (1-based) at Q-point `qIndex` (0-based), at the wave
        function's `cutoff` (Ry, -1: all plane waves), with the degenerate
        states if sumDegenerate; in the background (particleDensityReady).
        """
        name = 'hole' if particle == 'h' else 'electron'
        message = f'Computing the {name} density…'
        if not self.dataset.saveDir or not self.dataset.diagoDir:
            return self._reject(message, 'Open a dataset with its BSE databases first.')
        missing = self.dataset.missingQPoint(qIndex)
        if missing:
            return self._reject(message, missing)
        o = self.dataset
        arguments = dict(lattice=self.lattice, saveDir=o.saveDir, diagoDir=o.diagoDir, bseFile=o.bseFile(qIndex),
                         qIndex=qIndex, excIndex=excIndex, particle=particle, cutoff_ry=cutoff,
                         degenerate=self.sumDegenerate, cache=self.wavefunctionCache)
        self.tasks.submit(message, lambda context: computeParticleDensity(context, **arguments),
                          self._applyParticleDensity, key='particle-density')

    def _applyParticleDensity(self, result):
        self.markResultsChanged()
        if self.lattice is None:
            self.lattice = result['lattice']
        self.particleDensity = {key: value for key, value in result.items() if key != 'lattice'}
        self.particleDensityReady.emit(self.particleDensity)

    def _failComposition(self, reason):
        if self.composition is not None:
            self.composition = None
            self.compositionReady.emit(None)
        self.compositionFailed.emit(reason)

    def _applyComposition(self, result):
        if 'error' in result:
            return self._failComposition(result['error'])
        self.markResultsChanged()
        if self.lattice is None:
            self.lattice = result['lattice']
        self.composition = {key: value for key, value in result.items() if key != 'lattice'}
        self.compositionReady.emit(self.composition)

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
        if self.qIndices is None and point.data().q is None:
            return
        data = point.data()
        qIndex = int(data.q) if data.q is not None else int(self.qIndices[data.i])
        excIndex = int(data.j)
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
        dataset = self.dataset
        if dataset.qBZ is None:
            return self._reject(message, 'No Q-path: set one on the System page first.')
        if not dataset.diagoDir:
            return self._reject(message, 'No BSE directory: choose one on the System page first.')

        if not dataset.qPoints:
            return self._reject(message, 'The BSE directory has no BSE databases (ndb.BS_diago_Q*).')

        arguments = dict(saveDir=dataset.saveDir, diagoDir=dataset.diagoDir,
                         nExcitons=self.spectraParameters.nExcitons, qBZ=dataset.qBZ, qPoints=list(dataset.qPoints), bseFiles=dict(dataset.bseFiles))
        self.tasks.submit(message, lambda context: computeDispersion(context, **arguments),
                          self._applyDispersion, key='dispersion')

    def _applyDispersion(self, result):
        self.markResultsChanged()
        self.lattice = result['lattice']
        self.excitonDispersion = result['excitonDispersion']
        self.collinear_qpoints = result['collinearQPoints']
        self.qIndices = result['qIndices']
        self.dispPoints = result['points']
        self.dispPointsData = result['pointsData']
        self.dispXInter = result['xInter']
        self.dispYInter = result['yInter']
        self.dispersionAxes = {'xRange': list(result['xRange']), 'yRange': list(result['yRange']),
                               'specialPoints': list(result['specialPoints']), 'labels': list(result['labels']),
                               'note': result.get('note', ''), 'qPointCount': int(result.get('qPointCount', 0))}
        # The spectra belonged to the previous dispersion
        self.clearAbsorptionCurves()

        self.dispersionNoteChanged.emit(self.dispersionAxes['note'])
        self.dispersionQPointCountChanged.emit(self.dispersionAxes['qPointCount'])
        self.qPathReady.emit(result['specialPoints'], result['labels'])
        self.excitonDispersionRange.emit(result['xRange'], result['yRange'])
        # As many curve styles as excitons (the interpolated curves may be missing)
        self.excitonDispersionNumCurvesChanged.emit(len(self.dispPoints))
        self.excitonDispersionInit.emit()

        self.excitonBandStructureClear.emit()
        self.excitonAbsorptionClear.emit()

    @Slot()
    def emitExcitonDispersionReady(self):
        self.excitonDispersionReady.emit(self.dispPoints, self.dispPointsData, self.dispXInter, self.dispYInter)

    # Absorption

    def absorptionParameters(self):
        """Snapshot of the inputs of the absorption spectra."""
        o = self.dataset
        p = self.spectraParameters
        return dict(lattice=self.lattice, diagoDir=o.diagoDir, energyStep=p.energyStep, energyMin=p.energyMin,
                    energyMax=p.energyMax, minIntensity=p.excMinIntensity, autoRange=p.absorptionAutoRange,
                    bseFiles=dict(o.bseFiles))

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

    @Slot(int)
    def showQPointAbsorption(self, qPointIndex):
        """Add the absorption spectrum at a Q-point given by its index (e.g. one off the Q-path), kept."""
        message = 'Computing the absorption spectrum…'
        missing = self.dataset.missingQPoint(qPointIndex)
        if missing:
            return self._reject(message, missing)
        curve = self.absorptionCurveIndex(qPointIndex)
        if curve >= 0:
            self.excAbsData[curve]['fixed'] = True
            return
        if self.lattice is None:
            with databaseAccess():
                self.lattice = YamboLatticeDB.from_db(self.dataset.saveDir + '/ns.db1')
        parameters = self.absorptionParameters()
        self.tasks.submit(message, lambda context: self.computeAbsorptionSpectrum(-1, qPointIndex, parameters),
                          lambda data: self._updateAbsorptionCurves(qPointIndex, True, data))

    def _updateAbsorptionCurves(self, qPointIndex, toggleCurve, data):
        """Curves after a click on Q-point `qPointIndex`, with its spectrum `data` if newly computed."""
        self.markResultsChanged()
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
        self.markResultsChanged()
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

    def clearAbsorptionCurves(self):
        """
        Drop all absorption curves, with their styles: the curve styles are a list
        parallel to the curves (see excitonAbsorptionCurveRemoved), which would
        otherwise keep entries of curves no longer there.
        """
        self.markResultsChanged()
        for index in reversed(range(len(self.excAbsData))):
            self.excAbsData.pop(index)
            self.excitonAbsorptionCurveRemoved.emit(index)

    def absorptionCurveIndex(self, q):
        for i, curveData in enumerate(self.excAbsData):
            if curveData['q'] == q:
                return i
        return -1

    # Band structure

    @Slot()
    def getExcitonBandStructure(self, points, dummy):
        """
        The band structure of the excitons clicked (at any Q-point: that of the
        first; those of others are left out), kept to be computed again when
        sumDegenerate changes.
        """
        def qIndexOf(point):
            data = point.data()
            if data.q is not None:
                return int(data.q)
            return int(self.qIndices[data.i]) if self.qIndices is not None else None
        qIndex = qIndexOf(points[0]) if points else None
        if qIndex is None:
            self.bandStructureSelection = None
            self._applyBandStructure({'k': [], 'bands': [], 'weights': []})
            return
        indices = sorted({int(point.data().j) for point in points if qIndexOf(point) == qIndex})
        self.bandStructureSelection = (qIndex, indices)
        self.computeBandStructure()

    def computeBandStructure(self):
        """The band structure of the excitons last clicked, with the degeneracy setting of now."""
        if self.bandStructureSelection is None:
            return
        qIndex, indices = self.bandStructureSelection
        o = self.dataset
        if o.qBZ is None or not o.saveDir or not o.diagoDir or o.missingQPoint(qIndex):
            self._applyBandStructure({'k': [], 'bands': [], 'weights': []})
            return
        arguments = dict(lattice=self.lattice, saveDir=o.saveDir, diagoDir=o.diagoDir, bseFile=o.bseFile(qIndex),
                         qIndex=qIndex, excitonIndices=indices, degenerate=self.sumDegenerate, qBZ=o.qBZ,
                         gw=o.gw, qpDir=o.qpDir, qpFile=o.qpFile)
        self.tasks.submit('Interpolating the excitonic band structure…',
                          lambda context: computeBandStructure(context, **arguments),
                          self._applyBandStructure, key='band-structure')

    def _applyBandStructure(self, result):
        self.markResultsChanged()
        if self.lattice is None and result.get('lattice') is not None:
            self.lattice = result['lattice']
        # What it is: Q-point, states, bands (see computeBandStructure); None when cleared
        self.bandStructureInfo = result.get('info')
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
                                   supercell=None, block_size=256):
        """
        Compute, in the background, the real-space wave function of exciton
        `exc_index` (1-based) at Q-point `q_index` (0-based, the file
        ndb.BS_diago_Q<q_index + 1>); wfComputed is emitted when it is ready.
        """
        missing = self.dataset.missingQPoint(q_index)
        if missing:
            return self._reject('Computing the exciton wave function…', missing)
        arguments = dict(lattice=self.lattice, saveDir=self.dataset.saveDir, diagoDir=self.dataset.diagoDir,
                         bseFile=self.dataset.bseFile(q_index),
                         q_index=q_index, exc_index=exc_index, fixed_particle=fixed_particle,
                         fixed_position=list(fixed_position if fixed_position is not None else [0, 0, 0]),
                         cutoff_ry=cutoff_ry, supercell=list(supercell if supercell is not None else [1, 1, 1]),
                         cache=self.wavefunctionCache, block_size=block_size, degenerate=self.sumDegenerate)
        self.tasks.submit('Computing the exciton wave function…',
                          lambda context: computeWaveFunction(context, **arguments),
                          self._applyWaveFunction, key='wave-function')

    def _applyWaveFunction(self, result):
        self.markResultsChanged()
        self.lattice = result['lattice']
        self.waveFunction = result['waveFunction']
        self.wfAtomPositions = result['atomPositions']
        self.tr4x4 = result['tr4x4']
        self.wfFixedParticle = result['fixedParticle']
        self.wfSupercell = result['supercell']
        self.wfGrid = result['grid']
        self.wfFixedPosition = result['fixedPosition']
        self.wfExciton = (result['qIndex'], result['excIndex'])
        self.wfStates = list(result.get('states') or [result['excIndex']])
        self.wfDegenerate = result.get('degenerate')
        self.wfComputed.emit()

    # Results in session files (see session.py)

    def resultsSnapshot(self, includeWaveFunction=True):
        """
        The computed results, as JSON-able metadata and NumPy arrays (name ->
        array), to store in a session file.
        """
        meta, arrays = {}, {}

        if self.qIndices is not None and len(self.dispPoints):
            arrays['dispersion/qIndices'] = np.asarray(self.qIndices)
            arrays['dispersion/collinearQPoints'] = np.asarray(self.collinear_qpoints, dtype=float)
            arrays['dispersion/points'] = np.asarray(self.dispPoints, dtype=float)
            arrays['dispersion/xInter'] = np.asarray(self.dispXInter, dtype=float)
            arrays['dispersion/yInter'] = np.asarray(self.dispYInter, dtype=float)
            meta['dispersion'] = dict(self.dispersionAxes)

        curves = []
        for i, data in enumerate(self.excAbsData):
            for name in ('energy', 'absorption', 'brightExcEnergy', 'brightExcAbsorption', 'brightExcIntensities',
                         'brightExcIndices', 'darkExcEnergy'):
                arrays[f'absorption/{i}/{name}'] = np.asarray(data[name], dtype=float)
            curves.append({'q': int(data['q']), 'index': int(data['index']), 'fixed': bool(data['fixed']),
                           'range': list(data.get('range', ()))})
        if curves:
            meta['absorption'] = curves

        if len(self.k):
            arrays['bands/k'] = np.asarray(self.k, dtype=float)
            arrays['bands/bands'] = np.asarray(self.bands, dtype=float)
            arrays['bands/weights'] = np.asarray(self.weights, dtype=float)
            meta['bands'] = dict(self.bandStructureInfo) if self.bandStructureInfo else True

        if self.selectedExciton is not None:
            meta['selectedExciton'] = list(self.selectedExciton)

        if self.character is not None:
            meta['character'] = jsonableCharacter(self.character)

        if self.particleDensity is not None:
            d = self.particleDensity
            arrays['particleDensity/density'] = np.asarray(d['density'], dtype=np.float32)
            meta['particleDensity'] = {key: d[key] for key in ('particle', 'qIndex', 'excIndex', 'states',
                                                                'degenerate', 'cutoff', 'maxima', 'weightKept')}

        if self.composition is not None:
            c = self.composition
            arrays['composition/electron'] = np.asarray(c['electron'], dtype=float)
            arrays['composition/hole'] = np.asarray(c['hole'], dtype=float)
            meta['composition'] = {'qIndex': int(c['qIndex']), 'excIndex': int(c['excIndex']),
                                   'degenerate': bool(c['degenerate']), 'states': list(c['states']),
                                   'energy': float(c['energy']), 'redQPoint': [float(x) for x in c['red_qpoint']],
                                   'pairs': [list(p) for p in c['pairs']],
                                   'valence': [[b, w] for b, w in c['valence'].items()],
                                   'conduction': [[b, w] for b, w in c['conduction'].items()]}

        if includeWaveFunction and self.waveFunction is not None:
            # Single precision: plenty for a density relative to its maximum, half the size
            arrays['waveFunction/density'] = self.waveFunction.astype(np.float32)
            arrays['waveFunction/tr4x4'] = np.asarray(self.tr4x4, dtype=float)
            arrays['waveFunction/atomPositions'] = np.asarray(self.wfAtomPositions, dtype=float)
            meta['waveFunction'] = {'fixedParticle': self.wfFixedParticle, 'supercell': list(self.wfSupercell),
                                    'grid': list(self.wfGrid), 'fixedPosition': list(self.wfFixedPosition),
                                    'exciton': list(self.wfExciton),
                                    'states': list(self.wfStates or []), 'degenerate': self.wfDegenerate}
        return meta, arrays

    def restoreResults(self, meta, arrays):
        """
        Show results stored by resultsSnapshot, as if just computed. The dataset
        must be open (the lattice is read from it).
        """
        self.markResultsChanged()
        # Results with their own view: not centered again (see WavefunctionPanels)
        self.restoringResults = True
        try:
            self._restoreResults(meta, arrays)
        finally:
            self.restoringResults = False

    def _restoreResults(self, meta, arrays):
        lattice = self.lattice
        if lattice is None:
            with databaseAccess():
                lattice = self.lattice = YamboLatticeDB.from_db(self.dataset.saveDir + '/ns.db1')

        if 'dispersion' in meta:
            axes = meta['dispersion']
            points = arrays['dispersion/points']
            self._applyDispersion({
                'lattice': lattice, 'excitonDispersion': None,
                'collinearQPoints': arrays['dispersion/collinearQPoints'],
                'qIndices': arrays['dispersion/qIndices'],
                'points': points.tolist(),
                'pointsData': [[PointData(i, j + 1) for i in range(points.shape[1])] for j in range(points.shape[0])],
                'xInter': arrays['dispersion/xInter'], 'yInter': arrays['dispersion/yInter'],
                'xRange': tuple(axes['xRange']), 'yRange': tuple(axes['yRange']),
                'specialPoints': axes['specialPoints'], 'labels': axes['labels'],
                'note': axes.get('note', ''),
                'qPointCount': axes.get('qPointCount', len(set(np.asarray(arrays['dispersion/qIndices']).tolist()))),
            })

        for i, curve in enumerate(meta.get('absorption', [])):
            data = {name: arrays[f'absorption/{i}/{name}'] for name in
                    ('energy', 'absorption', 'brightExcEnergy', 'brightExcAbsorption', 'brightExcIntensities',
                     'brightExcIndices', 'darkExcEnergy')}
            data.update(q=curve['q'], index=curve['index'], fixed=curve['fixed'], range=tuple(curve['range']),
                        data=[PointData(curve['index'], int(j), q=int(curve['q'])) for j in data['brightExcIndices']])
            self.excAbsData.append(data)
            self.excitonAbsorptionCurveAppended.emit(curve['q'])
        if meta.get('absorption'):
            self.excitonAbsorptionReady.emit(self.excAbsData, self.showExcitonLabels)

        if meta.get('bands'):
            info = meta['bands'] if isinstance(meta['bands'], dict) else None      # True: before finite Q (at Γ)
            self._applyBandStructure({'info': info, 'k': arrays['bands/k'], 'bands': arrays['bands/bands'],
                                      'weights': arrays['bands/weights']})

        if 'waveFunction' in meta:
            wf = meta['waveFunction']
            self._applyWaveFunction({
                'lattice': lattice, 'waveFunction': arrays['waveFunction/density'].astype(float),
                'atomPositions': arrays['waveFunction/atomPositions'], 'tr4x4': arrays['waveFunction/tr4x4'],
                'fixedParticle': wf['fixedParticle'], 'supercell': list(wf['supercell']), 'grid': list(wf['grid']),
                'fixedPosition': list(wf['fixedPosition']), 'qIndex': wf['exciton'][0], 'excIndex': wf['exciton'][1],
                'states': wf.get('states') or None, 'degenerate': wf.get('degenerate'),
            })

        if 'character' in meta and isinstance(meta['character'], dict):
            self._applyCharacter(dict(meta['character'], lattice=lattice))

        if 'particleDensity' in meta and 'particleDensity/density' in arrays:
            self._applyParticleDensity(dict(meta['particleDensity'], lattice=lattice,
                                            density=arrays['particleDensity/density']))

        # Before the selected exciton, so that it is not computed again for it
        if 'composition' in meta:
            c = meta['composition']
            self._applyComposition({
                'lattice': lattice, 'qIndex': int(c['qIndex']), 'excIndex': int(c['excIndex']),
                'degenerate': bool(c['degenerate']), 'states': [int(x) for x in c['states']],
                'energy': float(c['energy']), 'red_qpoint': np.asarray(c['redQPoint'], dtype=float),
                'electron': arrays['composition/electron'], 'hole': arrays['composition/hole'],
                'pairs': [(int(v), int(cb), float(w)) for v, cb, w in c['pairs']],
                'valence': {int(b): float(w) for b, w in c['valence']},
                'conduction': {int(b): float(w) for b, w in c['conduction']},
            })

        if 'selectedExciton' in meta:
            qIndex, excIndex, energy = meta['selectedExciton']
            self.selectedExciton = (int(qIndex), int(excIndex), float(energy))
            self.excitonSelected.emit(*self.selectedExciton)

    # Size of a wave-function calculation (see memory.py)

    def estimateWaveFunction(self, q_index, exc_index, cutoff_ry, supercell, displayFactor=1):
        """
        Grid and memory of computing exciton `exc_index` at Q-point `q_index`;
        None when the databases are busy (a calculation is reading them) or
        missing. Raises ValueError for an exciton that does not exist.
        """
        if not self.dataset.saveDir or not self.dataset.diagoDir:
            return None
        missing = self.dataset.missingQPoint(q_index)
        if missing:
            raise ValueError(missing)
        if not DATABASE_LOCK.acquire(blocking=False):
            return None
        try:
            if self.lattice is None:
                self.lattice = YamboLatticeDB.from_db(self.dataset.saveDir + '/ns.db1')
            if self.planeWaves is None:
                self.planeWaves = PlaneWaves(self.dataset.saveDir, self.lattice)
            key = (self.dataset.diagoDir, q_index, exc_index)
            if key not in self.excitonSizes:
                filename = self.dataset.bseFile(q_index)
                excitonDB = YamboExcitonDB.from_db_file(self.lattice, filename=filename, folder=self.dataset.diagoDir,
                                                        neigs=exc_index + 20)
                if exc_index > len(excitonDB.eigenvalues):
                    raise ValueError(f'Exciton {exc_index} does not exist: {filename} has '
                                     f'{len(excitonDB.eigenvalues)} excitons')
                bands = int(np.max(excitonDB.table[:, 2])) - (int(np.min(excitonDB.table[:, 1])) - 1)
                self.excitonSizes[key] = {
                    'states': len(excitonDB.get_degenerate(exc_index, eps=DEGENERACY_EV)),
                    'bands': bands,
                    # Coefficients: (states, ..., k-points, conduction, valence)
                    'kpoints': excitonDB.get_Akcv().shape[-3],
                }
        except (OSError, KeyError, IndexError) as error:
            raise ValueError(str(error))
        finally:
            DATABASE_LOCK.release()

        size = dict(self.excitonSizes[key])
        if not self.sumDegenerate:
            size['states'] = 1          # the exciton alone
        fftBox = self.planeWaves.fftBox(cutoff_ry)
        supercell = [s + 1 - s % 2 for s in supercell]   # odd, as computed
        # A snapshot of the keys: the worker thread may be changing the cache
        loaded = any(saveDir == self.dataset.saveDir and bands[1] - bands[0] == size['bands']
                     for saveDir, bands in list(self.wavefunctionCache.keys()))
        memory = availableMemory()
        blockSize = chooseBlockSize(self.planeWaves, fftBox, size['states'], size['kpoints'],
                                    memory[1] if memory else None)
        estimate = estimateMemory(self.planeWaves, fftBox, supercell, size['states'], size['bands'], size['kpoints'],
                                  wavefunctionsLoaded=loaded, displayFactor=displayFactor, blockSize=blockSize)
        estimate.update(fftBox=fftBox, supercell=supercell, states=size['states'], loaded=loaded, blockSize=blockSize)
        return estimate

    # Geometry of the last wave function (lengths in Bohr)

    def wfVoxels(self):
        """Voxel vectors (rows) of the grid of the wave function."""
        return voxelVectors(self.lattice.lat, self.wfSupercell, self.waveFunction.shape)

    def wfFixedCrystal(self):
        """Position of the fixed particle in crystal coordinates of the supercell (central cell)."""
        return np.asarray(self.wfFixedPosition, dtype=float) + np.asarray(self.wfSupercell) // 2

    def wfFixedCartesian(self):
        return np.asarray(self.lattice.lat, dtype=float).T @ self.wfFixedCrystal()

    def kGrid(self):
        """The full k-point grid of the dataset (cached with its lattice)."""
        if self.lattice is None:
            self.unitCell()
        if getattr(self, '_kGrid', (None, None))[0] is not self.lattice:
            from .cellshift import kGrid
            self._kGrid = (self.lattice, kGrid(self.lattice))
        return self._kGrid[1]

    def wfSupercellAtoms(self):
        """Atomic numbers and Cartesian positions of the atoms of the supercell."""
        cell = self.unitCell()
        return supercellAtoms(cell['base_lattice_vectors'], cell['atomic_positions'], cell['atomic_numbers'],
                              self.wfSupercell)

    def exportParticleDensity(self, filename, supercell, shift=None):
        """
        Save the fixed particle's own density (particleDensity) with the atoms,
        repeated over `supercell` (format from the extension: .cube or .xsf), in
        the background; with `shift` (fractions of a, b, c), as shown with that
        cell origin. Values relative to its largest.
        """
        name = 'hole' if self.particleDensity is None or self.particleDensity['particle'] == 'h' else 'electron'
        message = f'Saving the {name} density…'
        d = self.particleDensity
        if d is None:
            return self._reject(message, 'No particle density: compute one first (Placing the fixed particle).')
        from .cellshift import snapShift, rollDensity, shiftAtoms
        lattice = np.asarray(self.unitCell()['base_lattice_vectors'], dtype=float)
        supercell = [int(n) for n in supercell]
        grid = d['density'].shape
        density = np.tile(np.asarray(d['density'], dtype=float) / (float(np.max(d['density'])) or 1.0), supercell)
        cell = self.unitCell()
        positions = np.asarray(cell['atomic_positions'], dtype=float)[:len(cell['atomic_numbers'])]
        shift = snapShift(shift, grid) if shift is not None and any(shift) else None
        if shift is not None:
            density = rollDensity(density, shift, grid)
            positions = shiftAtoms(lattice, positions, shift)
        numbers, atomPositions = supercellAtoms(lattice, positions, cell['atomic_numbers'], supercell)
        states = d['states']
        which = f'exciton {d["excIndex"]}' if len(states) == 1 else f'excitons {states[0]}-{states[-1]}'
        cutoff = 'all plane waves' if d['cutoff'] < 0 else f'{d["cutoff"]:g} Ry'
        comment = (f'{name.capitalize()} density of {which} at Q-point {d["qIndex"] + 1}: where the {name} is, wherever '
                   f'the {"electron" if name == "hole" else "hole"} is ({cutoff}); supercell {"x".join(map(str, supercell))};'
                   f' values relative to the maximum')
        if shift is not None:
            comment += f'; cell origin shifted by {" ".join(f"{s:.4f}" for s in shift)} (fractions of a, b, c)'
        arguments = dict(density=density, lattice=lattice, supercell=supercell, atomicNumbers=numbers,
                         atomPositions=atomPositions, comment=comment)

        def compute(context):
            context.stage('Writing ' + str(filename).rsplit('/', 1)[-1])
            writeDensity(filename, **arguments)
            return filename

        self.tasks.submit(message, compute, self.densityExported.emit)

    def exportDensity(self, filename, shift=None):
        """
        Save the probability density with the atoms of the supercell (format
        from the extension: .cube or .xsf), in the background; with `shift`
        (fractions of a, b, c; see cellshift.py), as shown with that cell origin.
        """
        message = 'Saving the probability density…'
        if self.waveFunction is None:
            return self._reject(message, 'No wave function: compute one first.')

        from .cellshift import snapShift, rollDensity, shiftAtoms, shiftCrystal
        lattice = np.asarray(self.lattice.lat, dtype=float)
        density, fixedCrystal = self.waveFunction, self.wfFixedCrystal()
        shift = snapShift(shift, self.wfGrid) if shift is not None and any(shift) else None
        if shift is not None:
            cell = self.unitCell()
            count = len(cell['atomic_numbers'])
            shifted = shiftAtoms(lattice, np.asarray(cell['atomic_positions'], dtype=float)[:count], shift)
            numbers, positions = supercellAtoms(lattice, shifted, cell['atomic_numbers'], self.wfSupercell)
            density = rollDensity(density, shift, self.wfGrid)
            fixedCrystal = shiftCrystal(fixedCrystal, shift, self.wfSupercell)
        else:
            numbers, positions = self.wfSupercellAtoms()
        fixedAngstrom = lattice.T @ fixedCrystal * BOHR_TO_ANGSTROM
        particle = 'hole' if self.wfFixedParticle == 'h' else 'electron'
        qIndex, excIndex = self.wfExciton
        comment = (f'Exciton {excIndex} at Q-point {qIndex + 1}, {particle} fixed at crystal coordinates '
                   f'{" ".join(f"{x:.4f}" for x in fixedCrystal)} of the supercell '
                   f'({" ".join(f"{x:.4f}" for x in fixedAngstrom)} A); '
                   f'supercell {"x".join(map(str, self.wfSupercell))}; values relative to the maximum')
        if shift is not None:
            comment += f'; cell origin shifted by {" ".join(f"{s:.4f}" for s in shift)} (fractions of a, b, c)'
        arguments = dict(density=density, lattice=lattice, supercell=list(self.wfSupercell),
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
                self.lattice = YamboLatticeDB.from_db(self.dataset.saveDir + '/ns.db1')

        return {
            'atomic_numbers': self.lattice.atomic_numbers,
            'atomic_positions': self.lattice.car_atomic_positions,
            'base_lattice_vectors': self.lattice.lat
        }

    def atomPositions(self):
        return self.wfAtomPositions
