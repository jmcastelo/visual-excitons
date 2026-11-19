"""
The results of each dataset kept between runs: written when the dataset is
left (another one opened, a new session, the program closed), restored when it
is opened again, if its databases did not change since (the fingerprint of
session.py). One entry per dataset, in the session file format without
preferences; the least recently used dropped beyond a total size.
"""

import hashlib
import json
import os
from pathlib import Path

from .session import (writeSession, readSession, datasetFingerprint, fingerprintsMatch, SessionError,
                      SESSION_SUFFIX)

# Total size of the cache, and largest wave function kept with the other results (bytes)
CACHE_LIMIT = 2 ** 30
WAVEFUNCTION_LIMIT = 100 * 2 ** 20

# What identifies a dataset's results: its databases and how they are used
DATASET_KEYS = ('save', 'diago', 'qp', 'qpFile', 'gw')


def datasetKey(dataset):
    """A name for the results of `dataset` (dict of its directories, QP file, GW): a hash of what they depend on."""
    identity = {key: dataset.get(key) for key in DATASET_KEYS}
    for key in ('save', 'diago', 'qp'):
        if identity[key]:
            identity[key] = str(Path(identity[key]).resolve())
    identity['gw'] = bool(identity['gw'])
    return hashlib.sha1(json.dumps(identity, sort_keys=True).encode()).hexdigest()


class ResultsCache:
    """The cached results of the datasets, in `folder`, at most `limit` bytes in all."""

    def __init__(self, folder, limit=CACHE_LIMIT):
        self.folder = Path(folder)
        self.limit = limit

    def path(self, dataset):
        return self.folder / (datasetKey(dataset) + SESSION_SUFFIX)

    def store(self, dataset, meta, arrays, programVersion='', optional=('waveFunction',)):
        """
        Keep the results of `dataset` (as Calculations.resultsSnapshot gives
        them); none: forget them. An entry larger than the whole limit is
        written again without the `optional` results (their metadata key and
        arrays 'key/...'), and not kept if still too large: never written only
        to be pruned at once. Returns what happened, 'kept', 'reduced' (without
        the optional results), 'too large' or 'none', and the size (bytes) of
        what was kept, or of the smallest entry tried when too large.
        """
        path = self.path(dataset)
        if not meta:
            path.unlink(missing_ok=True)
            return 'none', 0
        self.folder.mkdir(parents=True, exist_ok=True)
        dataset = {key: dataset.get(key) for key in DATASET_KEYS}

        def write(meta, arrays):
            manifest = {'dataset': dataset, 'fingerprint': datasetFingerprint(dataset), 'results': meta}
            writeSession(path, manifest, arrays, programVersion=programVersion)
            return path.stat().st_size

        status, size = 'kept', write(meta, arrays)
        if size > self.limit and any(key in meta for key in optional):
            meta = {key: value for key, value in meta.items() if key not in optional}
            arrays = {name: array for name, array in arrays.items() if name.split('/')[0] not in optional}
            status, size = 'reduced', write(meta, arrays) if meta else size
        if size > self.limit or not meta:
            path.unlink(missing_ok=True)
            return 'too large', size
        self.prune()
        return status, size

    def load(self, dataset):
        """
        The results kept for `dataset`, as (meta, arrays), and None if there is
        nothing to restore; and why not (or ''). Results of databases changed
        since are dropped.
        """
        path = self.path(dataset)
        if not path.is_file():
            return None, ''
        try:
            manifest, arrays = readSession(path)
        except SessionError:
            path.unlink(missing_ok=True)
            return None, 'the results kept from the last time could not be read'
        if not fingerprintsMatch(datasetFingerprint(dataset), manifest.get('fingerprint', {})):
            path.unlink(missing_ok=True)
            return None, 'the results kept from the last time were dropped: the dataset changed since'
        os.utime(path)                    # recently used: kept longest
        return (manifest.get('results') or {}, arrays), ''

    def entries(self):
        """The cached files, the most recently used first."""
        if not self.folder.is_dir():
            return []
        return sorted(self.folder.glob('*' + SESSION_SUFFIX), key=lambda p: p.stat().st_mtime, reverse=True)

    def size(self):
        return sum(p.stat().st_size for p in self.entries())

    def sizes(self):
        """The size of each entry, the most recently used first (the order prune keeps them in)."""
        return [p.stat().st_size for p in self.entries()]


    def prune(self):
        """Drop the least recently used entries beyond the limit."""
        total = 0
        for path in self.entries():
            total += path.stat().st_size
            if total > self.limit:
                path.unlink(missing_ok=True)

    def clear(self):
        """Forget every dataset's results; the space freed (bytes)."""
        freed = 0
        for path in self.entries():
            freed += path.stat().st_size
            path.unlink(missing_ok=True)
        return freed


def droppedBy(sizes, limit):
    """How many entries (sizes, the most recently used first) pruning to `limit` would drop."""
    total = 0
    for i, size in enumerate(sizes):
        total += size
        if total > limit:
            return len(sizes) - i
    return 0


# What is kept in the storage folder (MainWindow.storageFolder): the results between runs, and the
# representation matrices of the symmetry analysis (see calculations.computeCharacter)
STORAGE_PARTS = ('results', 'symmetry')


def folderUsage(folder):
    """The total size (bytes) and number of the files in `folder` and below (0, 0 if it does not exist)."""
    folder = Path(folder)
    if not folder.is_dir():
        return 0, 0
    files = [p for p in folder.rglob('*') if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files)


def clearFolder(folder):
    """Delete the files in `folder` and below; the space freed (bytes)."""
    freed, _ = folderUsage(folder)
    folder = Path(folder)
    if folder.is_dir():
        for path in sorted(folder.rglob('*'), reverse=True):        # files before their folders
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
    return freed


def moveStorage(old, new, parts=STORAGE_PARTS):
    """
    Move what is kept in the storage folder `old` (its `parts`) to `new`: all
    copied first, then the originals deleted, so that a failure (e.g. no space)
    leaves `old` as it was, and what was copied removed again (OSError raised).
    """
    import shutil
    old, new = Path(old).resolve(), Path(new).resolve()
    if old == new:
        return
    for part in parts:
        if new.is_relative_to(old / part):
            raise OSError(f'{new} is inside {old / part}, which would be moved into itself')
    copied = []
    try:
        for part in parts:
            source, target = old / part, new / part
            if not source.is_dir():
                continue
            copied.append((source, target, target.exists()))      # before copying: undone if it fails midway
            shutil.copytree(source, target, dirs_exist_ok=True)
    except OSError:
        for source, target, existed in copied:
            if existed:
                for path in source.rglob('*'):
                    if path.is_file():
                        (target / path.relative_to(source)).unlink(missing_ok=True)
            else:
                shutil.rmtree(target, ignore_errors=True)
        raise
    for source, target, existed in copied:
        shutil.rmtree(source, ignore_errors=True)
