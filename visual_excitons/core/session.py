"""
Session files: a whole setup of the program in one file, to come back to it
or to share it.

A session file (.vxsession) is a zip archive with:

- session.json: the manifest, readable by humans: format name and version,
  program version, date, the dataset (directories, Q-path), all parameters,
  the camera, the page shown, a fingerprint of the dataset, and the metadata
  of the stored results.
- results.npz: the arrays of the computed results (optional): dispersion,
  absorption spectra, band structure, wave function.

The fingerprint (sizes and modification times of the databases) tells
whether the dataset changed since the session was saved: stored results
then no longer apply.
"""

import io
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SESSION_FORMAT = 'visual-excitons-session'
SESSION_VERSION = 1
SESSION_SUFFIX = '.vxsession'
SESSION_FILTER = f'Visual Excitons session (*{SESSION_SUFFIX})'

MANIFEST_NAME = 'session.json'
RESULTS_NAME = 'results.npz'


class SessionError(Exception):
    """A session file that cannot be read."""


def jsonable(value):
    """`value` with NumPy scalars and arrays, and tuples, turned into plain JSON types."""
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    return value


def writeSession(path, manifest, arrays=None, programVersion=''):
    """
    Write a session file: `manifest` (JSON-able dict) and `arrays` (name ->
    NumPy array). Written to a temporary file first, then moved in place, so
    an interrupted save never leaves a broken file.
    """
    path = Path(path)
    content = dict(jsonable(manifest))
    content.update(format=SESSION_FORMAT, version=SESSION_VERSION, programVersion=programVersion,
                   saved=datetime.now(timezone.utc).isoformat(timespec='seconds'))

    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name, suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'wb') as file, zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(content, indent=2))
            if arrays:
                buffer = io.BytesIO()
                np.savez_compressed(buffer, **arrays)
                # Already compressed: stored as is
                archive.writestr(RESULTS_NAME, buffer.getvalue(), compress_type=zipfile.ZIP_STORED)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def readSession(path):
    """The manifest and the arrays (name -> array) of a session file; SessionError if it cannot be read."""
    try:
        with zipfile.ZipFile(path, 'r') as archive:
            manifest = json.loads(archive.read(MANIFEST_NAME))
            arrays = {}
            if RESULTS_NAME in archive.namelist():
                with np.load(io.BytesIO(archive.read(RESULTS_NAME)), allow_pickle=False) as data:
                    arrays = {name: data[name] for name in data.files}
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        raise SessionError(f'{path} is not a readable session file ({error})')

    if manifest.get('format') != SESSION_FORMAT:
        raise SessionError(f'{path} is not a Visual Excitons session file')
    if int(manifest.get('version', 0)) > SESSION_VERSION:
        raise SessionError(f'{path} was saved by a newer version of Visual Excitons '
                           f'({manifest.get("programVersion") or "unknown"}): update the program to open it')
    return manifest, arrays


def fingerprintsMatch(current, saved, strict=True):
    """
    Whether the dataset is the one the session was saved with. Not `strict`
    (the dataset was moved or copied, which may change modification times):
    the same numbers and sizes of databases.
    """
    if not saved or set(current) != set(saved):
        return False
    if strict:
        return all(list(current[key]) == list(saved[key]) for key in current)
    return all(list(current[key])[:2] == list(saved[key])[:2] for key in current)


def datasetFingerprint(dataset):
    """
    Sizes and modification times of the databases of `dataset` (dict with
    'save', 'diago', 'qp'): changes when any of them is replaced or recomputed.
    """
    def describe(paths):
        stats = [os.stat(p) for p in sorted(paths) if os.path.isfile(p)]
        return [len(stats), sum(s.st_size for s in stats), max((s.st_mtime_ns for s in stats), default=0)]

    fingerprint = {}
    if dataset.get('save'):
        fingerprint['save'] = describe([os.path.join(dataset['save'], 'ns.db1')])
    if dataset.get('diago'):
        from .databases import bseFiles
        fingerprint['diago'] = describe([Path(dataset['diago']) / name for name in bseFiles(dataset['diago'])[0].values()])
    if dataset.get('qp'):
        fingerprint['qp'] = describe([os.path.join(dataset['qp'], dataset.get('qpFile') or 'ndb.QP')])
    return fingerprint
