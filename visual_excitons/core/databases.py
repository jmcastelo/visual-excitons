"""
Yambo databases recognised by their content, not only their names.

Every Yambo database is a netCDF file whose variables tell its kind:

- SAVE (ns.db1): LATTICE_VECTORS, K-POINTS, G-VECTORS, EIGENVALUES.
- QP (ndb.QP, or merged and copied ones under other names, e.g.
  ndb.QP_140_146): QP_E, QP_Eo, QP_table (band, band, k-point), QP_kpts.
- BSE (ndb.BS_diago_Q<n>): BS_Energies, BS_TABLE.

Reading a header takes about 15 ms, too long for hundreds of BSE files: files
with the standard BSE name are taken at their word (the consistency checks
open some of them), other files are opened, after a cheap check of their
signature, and the results are cached by path, size and modification time.

A BSE file must still give its Q-point in its name: yambopy reads it from the
text after the first "Q" of the name (and recognises Γ as "1"), and older files
store nothing about it. Files whose name does not give it are reported.
"""

import re
from pathlib import Path

from netCDF4 import Dataset

from .tasks import databaseAccess

LATTICE, QP, BSE = 'lattice', 'qp', 'bse'

SIGNATURES = {
    LATTICE: {'LATTICE_VECTORS', 'K-POINTS', 'G-VECTORS', 'EIGENVALUES'},
    QP: {'QP_E', 'QP_Eo', 'QP_table', 'QP_kpts'},
    BSE: {'BS_Energies', 'BS_TABLE'},
}

STANDARD_BSE_NAME = re.compile(r'ndb\.BS_diago_Q(\d+)')
# What yambopy reads: the Q-point is the text after the first "Q" of the name
BSE_NAME_Q = re.compile(r'[^Q]*Q(\d+)')

NETCDF_SIGNATURES = (b'\x89HDF\r\n\x1a\n', b'CDF\x01', b'CDF\x02', b'CDF\x05')

_cache = {}


def isNetCDF(path) -> bool:
    try:
        with open(path, 'rb') as file:
            start = file.read(8)
    except OSError:
        return False
    return any(start.startswith(signature) for signature in NETCDF_SIGNATURES)


def bseQPoint(name):
    """The Q-point (index from 0) a BSE file's name gives, as yambopy reads it, or None."""
    match = BSE_NAME_Q.fullmatch(name)
    return int(match.group(1)) - 1 if match and int(match.group(1)) > 0 else None


def identify(path):
    """
    What database `path` is: a dict with 'kind' (LATTICE, QP or BSE), 'path',
    'name' and details (QP: 'bands' (first, last), 'kpoints'; BSE: 'q', from
    the name, None if it gives none), or None if it is not one.
    """
    path = Path(path)
    name = path.name
    if '_fragment_' in name or not path.is_file():
        return None
    match = STANDARD_BSE_NAME.fullmatch(name)
    if match and int(match.group(1)) > 0:
        return {'kind': BSE, 'path': str(path), 'name': name, 'q': int(match.group(1)) - 1, 'opened': False}
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in _cache:
        _cache[key] = _readDatabase(path)
    return _cache[key]


def _readDatabase(path):
    if not isNetCDF(path):
        return None
    try:
        with databaseAccess(), Dataset(path) as database:
            names = set(database.variables)
            kind = next((kind for kind, signature in SIGNATURES.items() if signature <= names), None)
            if kind is None:
                return None
            info = {'kind': kind, 'path': str(path), 'name': path.name, 'opened': True}
            if kind == QP:
                bands = database.variables['QP_table'][0, :]
                info['bands'] = (int(bands.min()), int(bands.max()))
                info['kpoints'] = int(database.variables['QP_kpts'].shape[-1])
            elif kind == BSE:
                info['q'] = bseQPoint(path.name)
            return info
    except (OSError, RuntimeError, KeyError, IndexError, ValueError):
        return None


def scan(folder, kinds=None):
    """The databases in `folder` (not its subfolders), of `kinds` if given, sorted by name."""
    try:
        paths = sorted(child for child in Path(folder).iterdir() if child.is_file())
    except OSError:
        return []
    found = []
    for path in paths:
        info = identify(path)
        if info is not None and (kinds is None or info['kind'] in kinds):
            found.append(info)
    return found


def hasDatabase(folder, kind) -> bool:
    """Whether `folder` holds a database of `kind` (quick for standard names)."""
    if kind == BSE and any(Path(folder).glob('ndb.BS_diago_Q*')):
        return True
    if kind == LATTICE:
        return Path(folder, 'ns.db1').is_file()
    return bool(scan(folder, {kind}))


def qpDatabases(folder):
    """The QP databases in `folder`, the default one first: ndb.QP, otherwise the widest band range."""
    found = scan(folder, {QP})
    return sorted(found, key=lambda info: (info['name'] != 'ndb.QP', -(info['bands'][1] - info['bands'][0]), info['name']))


def bseFiles(folder):
    """
    The BSE files of `folder`: ({Q-point index from 0: file name}, problems),
    where problems lists files whose name gives no Q-point, and Q-points with
    several files (the standard name is kept, otherwise the first by name).
    """
    files, problems = {}, []
    for info in scan(folder, {BSE}):
        q, name = info['q'], info['name']
        if q is None:
            problems.append(f'{name} is a BSE database, but its name does not give its Q-point '
                            '(e.g. ndb.BS_diago_Q5): it is not used.')
            continue
        if q in files:
            standard = f'ndb.BS_diago_Q{q + 1}'
            kept = standard if standard in (files[q], name) else min(files[q], name)
            problems.append(f'Q-point {q + 1} has two BSE databases, {files[q]} and {name}: {kept} is used.')
            files[q] = kept
            continue
        files[q] = name
    return dict(sorted(files.items())), problems
