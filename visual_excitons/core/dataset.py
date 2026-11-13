"""
Datasets: the directories of the databases of one calculation.

A dataset is a SAVE directory (ns.db1), a BSE directory (ndb.BS_diago_Q*)
and, for GW calculations, a QP directory (ndb.QP, or QP databases of other
names: they are recognised by their content, see databases.py). They can be
found inside a common folder, as in data/<system>/{save, diagos, qp}.
"""

import os
from pathlib import Path

from .databases import hasDatabase, qpDatabases, LATTICE, QP, BSE


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
