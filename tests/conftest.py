"""
Shared test setup.

Qt runs on its offscreen platform (no display needed) unless QT_QPA_PLATFORM
is set, and the application settings are written to a temporary directory so
the tests never touch the user's own. Tests using the datasets in data/ (not
in the repository) are skipped when these are missing.
"""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# Tests run in parallel (pytest-xdist, see pytest_xdist_auto_num_workers):
# each worker uses one thread for the numerical libraries (OpenBLAS, OpenMP,
# numba), which otherwise start one per CPU thread in every worker and
# saturate the CPU. Set before NumPy is imported.
# Serial runs (-n0, or with the slow tests) use at most half the CPU threads,
# unless set otherwise. Workers always get one: they inherit the environment
# of the main process, where the serial limit is set.
_THREAD_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS',
                     'NUMBA_NUM_THREADS')
for _variable in _THREAD_VARIABLES:
    if os.environ.get('PYTEST_XDIST_WORKER'):
        os.environ[_variable] = '1'
    else:
        os.environ.setdefault(_variable, str(max(1, (os.cpu_count() or 2) // 2)))

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QCoreApplication, Qt, QEvent

# As in main.py, before the application is created
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / 'data'


# Memory of a test worker (measured peak: 0.8 GB, with Qt and YamboPy), and
# memory left free for the system and the user's programs
WORKER_MEMORY = 1.0 * 2 ** 30
MEMORY_MARGIN = 2.0 * 2 ** 30


def selectsSlowTests(config):
    """Whether the run includes the slow tests (marker expression of -m)."""
    expression = (getattr(config.option, 'markexpr', '') or '').strip() if config is not None else ''
    if not expression:
        return True   # no selection: every test
    try:
        from _pytest.mark.expression import Expression
        return Expression.compile(expression).evaluate(lambda name, **kwargs: name in ('slow', 'data'))
    except Exception:   # private pytest API: be conservative if it changes
        return 'slow' in expression and expression != 'not slow'


def pytest_xdist_auto_num_workers(config):
    """
    Workers for `-n auto`, so as to saturate neither the CPU nor the memory:

    - none (a serial run) when the slow tests are included: each loads
      gigabytes of wave functions, which next to other workers can exhaust
      the memory;
    - one per physical core, at most half the CPU threads (4 on a 4-core,
      8-thread CPU);
    - at most as many as fit in the available memory, keeping MEMORY_MARGIN free.
    """
    if selectsSlowTests(config):
        return 0
    logical = os.cpu_count() or 2
    try:
        import psutil
        physical = psutil.cpu_count(logical=False) or logical // 2
        available = psutil.virtual_memory().available
    except ImportError:
        physical, available = logical // 2, None
    workers = max(1, min(physical, logical // 2))
    if available is not None:
        workers = min(workers, int((available - MEMORY_MARGIN) // WORKER_MEMORY))
    # A single worker is a serial run with extra overhead
    return workers if workers >= 2 else 0


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


@pytest.fixture(autouse=True)
def deleteWindows():
    """
    Delete the top-level widgets a test leaves (windows, dialogs, menus). Closed
    is not enough: they stay alive through their signal connections, and every
    theme change repolishes them all, slower and slower as tests go by.
    """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    before = set(app.topLevelWidgets()) if app is not None else set()
    yield
    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        if widget not in before and widget.parent() is None:
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def lattice():
    """YamboLatticeDB loader for a dataset in data/ (skips when missing)."""
    from yambopy import YamboLatticeDB

    def load(name):
        return YamboLatticeDB.from_db(str(datasetPath(name) / 'save' / 'ns.db1'))
    return load
