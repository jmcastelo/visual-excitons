"""The results of each dataset kept between runs (core/results_cache.py and MainWindow)."""

import os
import time

import numpy as np
import pytest

from conftest import datasetPath
from visual_excitons.core.results_cache import ResultsCache, datasetKey


def fakeDataset(folder):
    """A dataset of empty databases (enough for its fingerprint)."""
    for sub, name in (('save', 'ns.db1'), ('diagos', 'ndb.BS_diago_Q1'), ('qp', 'ndb.QP')):
        (folder / sub).mkdir(parents=True, exist_ok=True)
        (folder / sub / name).write_bytes(b'x' * 100)
    return {'save': str(folder / 'save'), 'diago': str(folder / 'diagos'), 'qp': str(folder / 'qp'),
            'qpFile': 'ndb.QP', 'gw': True}


def test_round_trip_and_a_changed_dataset(tmp_path):
    cache = ResultsCache(tmp_path / 'cache')
    dataset = fakeDataset(tmp_path / 'data')
    assert cache.load(dataset) == (None, '')
    cache.store(dataset, {'bands': True}, {'bands/k': np.arange(3.0)})
    (meta, arrays), reason = cache.load(dataset)
    assert meta == {'bands': True} and np.array_equal(arrays['bands/k'], [0, 1, 2]) and reason == ''
    # Recomputed databases: the results go
    os.utime(tmp_path / 'data' / 'diagos' / 'ndb.BS_diago_Q1', (time.time() + 100, time.time() + 100))
    cached, reason = cache.load(dataset)
    assert cached is None and 'changed' in reason and not cache.path(dataset).exists()


def test_keys_and_nothing_to_keep(tmp_path):
    dataset = fakeDataset(tmp_path / 'data')
    assert datasetKey(dataset) == datasetKey(dict(dataset, save=dataset['save'] + '/'))        # the same folders
    assert datasetKey(dataset) != datasetKey(dict(dataset, qpFile='ndb.QP_1_5'))              # another QP database
    assert datasetKey(dataset) != datasetKey(dict(dataset, gw=False))
    cache = ResultsCache(tmp_path / 'cache')
    cache.store(dataset, {'bands': True}, {})
    cache.store(dataset, {}, {})                         # no results: none kept
    assert not cache.path(dataset).exists()


def test_least_recently_used_go_first(tmp_path):
    datasets = [fakeDataset(tmp_path / f'data{i}') for i in range(3)]
    cache = ResultsCache(tmp_path / 'cache', limit=10 ** 9)
    for i, dataset in enumerate(datasets):
        cache.store(dataset, {'bands': True}, {'big': np.zeros(20000)})
        os.utime(cache.path(dataset), (1000 + i, 1000 + i))
    cache.load(datasets[0])                              # used again: now the most recent
    size = cache.path(datasets[0]).stat().st_size
    cache.limit = int(2.5 * size)
    cache.prune()
    assert [cache.path(d).exists() for d in datasets] == [True, False, True]
    assert cache.clear() > 0 and cache.entries() == []


# Through the main window

@pytest.fixture
def newWindow(qtbot):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()

    def make():
        w = main_window.MainWindow()
        qtbot.addWidget(w)
        return w
    yield make
    from visual_excitons.gui.theme import themeManager
    themeManager().setMode('System')


@pytest.mark.data
def test_results_come_back_with_the_dataset(newWindow, isolatedResultsCache):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    bii3, bn = (main_window.findDataset(datasetPath(name)) for name in ('BiI3_Bulk_8x8x8', 'BN'))
    w = newWindow()
    assert w.keepResultsAction.isChecked()                # on by default
    w.openDataset(bii3)
    injectResults(w)
    points, waveFunction = list(w.calculations.dispPoints), w.calculations.waveFunction.copy()
    # Untitled, with results: nothing to save, they are kept
    w.updateModified()
    assert not w.isWindowModified()

    # Left for another dataset, and opened again: the same results
    w.openDataset(bn)
    assert w.calculations.dispPoints == [] and w.calculations.waveFunction is None
    w.openDataset(bii3)
    assert w.calculations.dispPoints == points and w.statusBar().currentMessage().startswith('The results of the last')
    np.testing.assert_allclose(w.calculations.waveFunction, waveFunction, atol=1e-6)

    # Kept when the program closes too, for the next run
    w.calculations.selectedExciton = (4, 3, 2.2)
    w.close()
    w2 = newWindow()
    w2.openDataset(bii3)
    assert w2.calculations.selectedExciton == (4, 3, 2.2) and len(w2.calculations.excAbsData) == 2

    # Off: nothing restored
    w2.keepResultsAction.setChecked(False)
    w2.openDataset(bn)
    w2.openDataset(bii3)
    assert w2.calculations.dispPoints == []


@pytest.mark.data
def test_large_wave_functions_are_left_out(newWindow, monkeypatch):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    monkeypatch.setattr(main_window, 'WAVEFUNCTION_LIMIT', 1000)          # bytes: smaller than any
    bii3, bn = (main_window.findDataset(datasetPath(name)) for name in ('BiI3_Bulk_8x8x8', 'BN'))
    w = newWindow()
    w.openDataset(bii3)
    injectResults(w)
    w.openDataset(bn)
    w.openDataset(bii3)
    assert w.calculations.waveFunction is None and len(w.calculations.dispPoints) == 2


@pytest.mark.data
def test_a_session_with_results_wins(newWindow, tmp_path):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    bii3, bn = (main_window.findDataset(datasetPath(name)) for name in ('BiI3_Bulk_8x8x8', 'BN'))
    w = newWindow()
    w.openDataset(bii3)
    injectResults(w)
    path = tmp_path / 'with.vxsession'
    w.writeSessionFile(str(path))                         # its results: those injected
    w.calculations.selectedExciton = (4, 3, 2.2)          # then other results, kept between runs
    w.openDataset(bn)
    w.openSession(str(path))
    assert w.calculations.selectedExciton == (4, 2, 2.1) and len(w.calculations.excAbsData) == 2
