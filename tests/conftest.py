"""
Shared test setup.

Qt runs on its offscreen platform (no display needed) unless QT_QPA_PLATFORM
is set, and the application settings are written to a temporary directory so
the tests never touch the user's own. Tests using the datasets in data/ (not
in the repository) are skipped when these are missing.
"""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / 'data'


def datasetPath(name: str) -> Path:
    """Folder of a dataset in data/, or skip the test if it is not there."""
    path = DATA_DIR / name
    if not (path / 'save' / 'ns.db1').is_file():
        pytest.skip(f'dataset data/{name} not available')
    return path


@pytest.fixture(scope='session', autouse=True)
def isolatedSettings(tmp_path_factory):
    directory = tmp_path_factory.mktemp('settings')
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, str(directory))
    yield directory


@pytest.fixture
def lattice():
    """YamboLatticeDB loader for a dataset in data/ (skips when missing)."""
    from yambopy import YamboLatticeDB

    def load(name):
        return YamboLatticeDB.from_db(str(datasetPath(name) / 'save' / 'ns.db1'))
    return load
