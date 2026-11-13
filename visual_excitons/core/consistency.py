"""
Whether the databases of a dataset belong together: the SAVE directory, the
QP database and the BSE databases of one calculation.

The databases share no identifier (each SERIAL_NUMBER is the file's own), but
they hold enough physical data to cross-check:

- QP and SAVE: the same lattice constants (HEAD_D_LATT, LATTICE_PARAMETER),
  the same irreducible k-points, and DFT energies (QP_Eo) equal to the SAVE
  eigenvalues up to one constant (Yambo shifts the zero of energy): the
  strongest test that the QP database was computed on that SAVE directory.
- BSE and SAVE: the coordinates stored in newer BSE files (Q-point) are those
  of the Q-point their name gives; their bands are within the SAVE's.
- BSE and QP: their bands are within the QP range (a warning: Yambo may have
  extrapolated the corrections, or applied none, outside it).
- BSE files agree with each other (transition table, bands, coupling).

Only a sample of the BSE files is read (each header takes about 15 ms), unless
all are asked for (`bseSample=None`, in the background: e.g. 8 s for 540 files),
which also catches files renamed with standard names that are not what their
name says.
"""

import numpy as np
from netCDF4 import Dataset

from .databases import identify, LATTICE, QP
from .tasks import DATABASE_LOCK

OK, INFO, WARNING, ERROR = 'ok', 'info', 'warning', 'error'

# BSE files read: the first, the last, and a few in between
BSE_SAMPLE = 6


class Busy(Exception):
    """A calculation is reading the databases: check later."""


def finding(level, area, text):
    return {'level': level, 'area': area, 'text': text}


def _read(path, *names):
    with Dataset(path) as database:
        return {name: np.asarray(database.variables[name][...].data) for name in names if name in database.variables}


def sampleOf(items, count=BSE_SAMPLE):
    """Up to `count` of `items`, evenly spread, the first and last included."""
    items = list(items)
    if len(items) <= count:
        return items
    return [items[round(i * (len(items) - 1) / (count - 1))] for i in range(count)]


def checkDataset(saveDir, qpPath=None, diagoDir=None, bseFiles=None, bseProblems=(), bseSample=BSE_SAMPLE,
                 context=None):
    """
    The findings of the checks: dicts with 'level' (OK, INFO, WARNING, ERROR),
    'area' ('SAVE', 'GW', 'BSE') and 'text'. `bseSample` BSE files are read
    (None: all of them); `context` (a TaskContext) reports their progress.
    Raises Busy if a calculation is reading the databases (not in the task
    doing it: the lock is reentrant).
    """
    if not DATABASE_LOCK.acquire(blocking=False):
        raise Busy()
    try:
        return _check(saveDir, qpPath, diagoDir, bseFiles or {}, bseProblems, bseSample, context)
    finally:
        DATABASE_LOCK.release()


def _check(saveDir, qpPath, diagoDir, bseFiles, bseProblems, bseSample=BSE_SAMPLE, context=None):
    findings = []
    savePath = f'{saveDir}/ns.db1'
    info = identify(savePath)
    if info is None or info['kind'] != LATTICE:
        return [finding(ERROR, 'SAVE', f'{savePath} is not a Yambo SAVE database (no lattice, k-points or energies).')]
    save = _read(savePath, 'LATTICE_PARAMETER', 'K-POINTS', 'EIGENVALUES')
    eigenvalues = save['EIGENVALUES'].reshape(-1, *save['EIGENVALUES'].shape[-2:])[0]   # (k-points, bands)
    nk, nb = eigenvalues.shape
    findings.append(finding(OK, 'SAVE', f'SAVE database: {nk} irreducible k-points, {nb} bands.'))

    qpBands = None
    if qpPath:
        findings += _checkQP(qpPath, save, eigenvalues)
        qpInfo = identify(qpPath)
        qpBands = qpInfo['bands'] if qpInfo and qpInfo['kind'] == QP else None
    if diagoDir and bseFiles:
        findings += _checkBSE(saveDir, diagoDir, bseFiles, nb, qpBands, qpPath, bseSample, context)
    for problem in bseProblems:
        findings.append(finding(WARNING, 'BSE', problem))
    return findings


def _checkQP(qpPath, save, eigenvalues):
    name = qpPath.replace('\\', '/').split('/')[-1]
    info = identify(qpPath)
    if info is None or info['kind'] != QP:
        return [finding(ERROR, 'GW', f'{name} is not a QP database.')]
    qp = _read(qpPath, 'HEAD_D_LATT', 'QP_kpts', 'QP_table', 'QP_Eo')
    nk, nb = eigenvalues.shape
    errors = []
    if 'HEAD_D_LATT' in qp and not np.allclose(qp['HEAD_D_LATT'], save['LATTICE_PARAMETER'], rtol=1e-6):
        errors.append(f'its lattice constants ({", ".join(f"{a:.4f}" for a in qp["HEAD_D_LATT"])} Bohr) are not those '
                      f'of the SAVE directory ({", ".join(f"{a:.4f}" for a in save["LATTICE_PARAMETER"])} Bohr)')
    if qp['QP_kpts'].shape != save['K-POINTS'].shape or not np.allclose(qp['QP_kpts'], save['K-POINTS'], atol=1e-6):
        errors.append(f'its k-points ({qp["QP_kpts"].shape[-1]}) are not those of the SAVE directory ({nk})')
    bands = qp['QP_table'][0].astype(int) - 1
    kpoints = qp['QP_table'][2].astype(int) - 1
    if bands.max() >= nb or kpoints.max() >= nk:
        errors.append(f'it has bands or k-points beyond those of the SAVE directory ({nb} bands)')
    elif not errors:
        shift = eigenvalues[kpoints, bands] - qp['QP_Eo']
        if np.ptp(shift) > 1e-5:
            errors.append('its DFT energies are not those of the SAVE directory (computed from another DFT run?)')
    if errors:
        return [finding(ERROR, 'GW', f'{name} does not belong to this SAVE directory: ' + '; '.join(errors) + '.')]
    return [finding(OK, 'GW', f'{name} (bands {info["bands"][0]}–{info["bands"][1]}) was computed on this SAVE '
                              'directory: same lattice, k-points and DFT energies.')]


def _checkBSE(saveDir, diagoDir, bseFiles, nb, qpBands, qpPath, bseSample=BSE_SAMPLE, context=None):
    findings = []
    items = sorted(bseFiles.items())
    sample = items if bseSample is None else sampleOf(items, bseSample)
    if context is not None:
        context.stage('Reading the BSE databases', len(sample))
    lattice = None
    tables, revisions, couplings, mismatched = {}, set(), set(), []
    for q, name in sample:
        if context is not None:
            context.advance()
        try:
            data = _read(f'{diagoDir}/{name}', 'BS_TABLE', 'Q-point', 'HEAD_REVISION', 'COUPLING')
        except (OSError, RuntimeError):
            findings.append(finding(ERROR, 'BSE', f'{name} cannot be read.'))
            continue
        if 'BS_TABLE' not in data:
            findings.append(finding(ERROR, 'BSE', f'{name} is not a BSE database.'))
            continue
        table = data['BS_TABLE']
        table = table if table.shape[0] < table.shape[-1] else table.T     # rows: k, v, c, ...
        tables[name] = (table.shape[1], int(table[1].min()), int(table[2].max()))
        if 'HEAD_REVISION' in data:
            revisions.add(int(np.ravel(data['HEAD_REVISION'])[0]))
        if 'COUPLING' in data:
            couplings.add(int(np.ravel(data['COUPLING'])[0]))
        if 'Q-point' in data:
            if lattice is None:
                from yambopy import YamboLatticeDB
                lattice = YamboLatticeDB.from_db(f'{saveDir}/ns.db1', Expand=False)
            # In reduced coordinates, modulo reciprocal lattice vectors: Yambo
            # may store a Q-point shifted by one (the same Q-point)
            reciprocal = np.asarray(lattice.rlat, dtype=float).T
            points = np.linalg.solve(reciprocal, np.asarray(lattice.car_kpoints, dtype=float).T).T
            position = np.linalg.solve(reciprocal, np.asarray(data['Q-point'], dtype=float) / lattice.alat)
            same = lambda point: np.allclose(point - position, np.round(point - position), atol=1e-4)
            if q >= len(points) or not same(points[q]):
                matches = [i for i, point in enumerate(points) if same(point)]
                actual = f'those of Q-point {matches[0] + 1}' if len(matches) else 'not those of any Q-point of the grid'
                mismatched.append(f'{name}: its coordinates are {actual}')

    if not tables:
        return findings
    lows = {low for _, low, _ in tables.values()}
    highs = {high for _, _, high in tables.values()}
    low, high = min(lows), max(highs)
    checked = (f'all {len(bseFiles)} BSE databases checked' if len(tables) == len(bseFiles) > BSE_SAMPLE
               else f'{len(tables)} of the {len(bseFiles)} BSE databases checked')
    if high > nb:
        findings.append(finding(ERROR, 'BSE', f'The BSE databases use bands up to {high}, but the SAVE directory has '
                                              f'{nb}: they belong to another calculation.'))
    if mismatched:
        listed = '; '.join(mismatched[:8]) + (f'; and {len(mismatched) - 8} more' if len(mismatched) > 8 else '')
        findings.append(finding(ERROR, 'BSE', f'{len(mismatched)} BSE database{"s are" if len(mismatched) > 1 else " is"} '
                                              f'not of the Q-point {"their" if len(mismatched) > 1 else "its"} name gives: '
                                              f'{listed}.'))
    if len({size for size, _, _ in tables.values()}) > 1 or len(lows) > 1 or len(highs) > 1 or len(couplings) > 1:
        findings.append(finding(WARNING, 'BSE', 'The BSE databases differ in their transitions or bands (from '
                                                'different runs?): ' + ', '.join(f'{name}: bands {lo}–{hi}'
                                                for name, (_, lo, hi) in list(tables.items())[:4]) + '.'))
    if qpBands is not None and (low < qpBands[0] or high > qpBands[1]):
        outside = [b for b in range(low, high + 1) if b < qpBands[0] or b > qpBands[1]]
        name = qpPath.replace('\\', '/').split('/')[-1]
        findings.append(finding(WARNING, 'BSE', f'The BSE uses bands {low}–{high}, but {name} corrects bands '
                                                f'{qpBands[0]}–{qpBands[1]}: band{"s" if len(outside) > 1 else ""} '
                                                f'{", ".join(map(str, outside[:6]))} had no GW correction, or an '
                                                'extrapolated one.'))
    if len(revisions) > 1:
        findings.append(finding(INFO, 'BSE', 'The BSE databases were written by different Yambo revisions: '
                                             + ', '.join(map(str, sorted(revisions))) + '.'))
    if not any(f['level'] == ERROR for f in findings):
        findings.append(finding(OK, 'BSE', f'BSE databases: bands {low}–{high}, within the SAVE directory ({checked}).'))
    return findings


def summary(findings):
    """The worst level found (OK if none worse)."""
    for level in (ERROR, WARNING):
        if any(f['level'] == level for f in findings):
            return level
    return OK
