"""The results of each dataset kept between runs (core/results_cache.py and MainWindow)."""

import os
import time
from pathlib import Path

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
    assert w.keepResults() and w.storeSessionResults()   # on by default
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
    w2.settings.setValue('cacheResults', False)
    w2.openDataset(bn)
    w2.openDataset(bii3)
    assert w2.calculations.dispPoints == []


@pytest.mark.data
def test_large_wave_functions_are_left_out(newWindow, monkeypatch):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    bii3, bn = (main_window.findDataset(datasetPath(name)) for name in ('BiI3_Bulk_8x8x8', 'BN'))
    w = newWindow()
    w.settings.setValue('wavefunctionCacheLimit', 1000)                  # bytes: smaller than any
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


# The storage folder and the Results and storage dialog

def fill(folder, part, names, size=1000):
    (folder / part).mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / part / name).write_bytes(b'x' * size)


def test_moving_and_clearing_the_storage(tmp_path, monkeypatch):
    from visual_excitons.core.results_cache import moveStorage, folderUsage, clearFolder
    old, new = tmp_path / 'old', tmp_path / 'new'
    fill(old, 'results', ['a.vxsession', 'b.vxsession'])
    fill(old, 'symmetry', ['m1.npy'])
    fill(old, 'other', ['kept.txt'])                     # not ours: left alone
    assert folderUsage(old / 'results') == (2000, 2)
    moveStorage(old, new)
    assert folderUsage(new / 'results') == (2000, 2) and folderUsage(new / 'symmetry') == (1000, 1)
    assert not (old / 'results').exists() and (old / 'other' / 'kept.txt').exists()

    # A failure midway: nothing moved, what was copied removed
    import shutil
    copytree = shutil.copytree

    def failing(source, target, **kwargs):
        if Path(source).name == 'symmetry':
            copytree(source, target, **kwargs)
            raise OSError('no space left')
        return copytree(source, target, **kwargs)
    monkeypatch.setattr(shutil, 'copytree', failing)
    other = tmp_path / 'other'
    with pytest.raises(OSError, match='no space'):
        moveStorage(new, other)
    assert folderUsage(new / 'results')[1] == 2 and folderUsage(new / 'symmetry')[1] == 1
    assert not (other / 'results').exists() and not (other / 'symmetry').exists()
    monkeypatch.setattr(shutil, 'copytree', copytree)
    with pytest.raises(OSError, match='inside'):
        moveStorage(new, new / 'results' / 'deeper')
    assert clearFolder(new / 'symmetry') == 1000 and folderUsage(new / 'symmetry') == (0, 0)


def test_storage_dialog(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from visual_excitons.gui import storage_dialog
    cleared = []
    usage = {'results': (5 * 2 ** 20, 3), 'symmetry': 2 ** 30}
    values = {'storeSessionResults': True, 'keepResults': True, 'cacheLimit': 2 ** 30, 'wavefunctionLimit': 100 * 2 ** 20,
              'folder': str(tmp_path / 'store')}

    def clear(kind):
        cleared.append(kind)
        freed = usage[kind][0] if kind == 'results' else usage[kind]
        usage[kind] = (0, 0) if kind == 'results' else 0
        return freed
    dialog = storage_dialog.StorageDialog(values, tmp_path / 'default', lambda: (*usage['results'], usage['symmetry']),
                                          lambda: clear('results'), lambda: clear('symmetry'))
    qtbot.addWidget(dialog)
    assert dialog.values() == values
    assert dialog.resultsUsageLabel.text() == 'In use: 5.0 MB for 3 datasets.'
    assert dialog.symmetryUsageLabel.text() == 'In use: 1.00 GB.'
    dialog.clearResultsButton.click()
    assert cleared == ['results'] and 'Cleared 5.0 MB' in dialog.resultsUsageLabel.text()
    assert not dialog.clearResultsButton.isEnabled()

    # Limits: the wave functions' within the total; off, both disabled
    dialog.cacheLimitSpinBox.setValue(0.5)
    dialog.wavefunctionLimitSpinBox.setValue(800)
    assert dialog.values()['wavefunctionLimit'] == dialog.values()['cacheLimit'] == 2 ** 29
    dialog.keepResultsCheckBox.setChecked(False)
    assert not dialog.cacheLimitSpinBox.isEnabled() and not dialog.wavefunctionLimitSpinBox.isEnabled()

    # The folder: Default, and one that cannot be used
    [b for b in dialog.findChildren(storage_dialog.QPushButton) if b.text() == 'Default'][0].click()
    assert dialog.values()['folder'] == str(tmp_path / 'default')
    blocker = tmp_path / 'a file'
    blocker.write_text('')
    dialog.folderEdit.setText(str(blocker / 'inside'))
    warnings = []
    monkeypatch.setattr(storage_dialog.QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    dialog.accept()
    assert warnings and 'cannot be used' in warnings[0] and dialog.result() == 0
    dialog.folderEdit.setText(str(tmp_path / 'fine'))
    dialog.accept()
    assert dialog.result() == 1 and (tmp_path / 'fine').is_dir()


@pytest.mark.data
def test_storage_settings_through_the_window(newWindow, tmp_path, monkeypatch):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    monkeypatch.delenv('VISUAL_EXCITONS_RESULTS_CACHE')       # the results under the storage folder, as for users
    monkeypatch.setattr(main_window, 'defaultStorageFolder', lambda: tmp_path / 'default')    # not Qt's own
    first, second = tmp_path / 'first', tmp_path / 'second'
    w = newWindow()
    w.settings.setValue('cacheFolder', str(first))
    w.applyStorage()
    assert w.resultsCache.folder == first / 'results' and w.calculations.diskCacheFolder == str(first)
    bii3, bn = (main_window.findDataset(datasetPath(name)) for name in ('BiI3_Bulk_8x8x8', 'BN'))
    w.openDataset(bii3)
    injectResults(w)
    w.openDataset(bn)
    fill(first, 'symmetry', ['m1.npy'])
    assert w.storageUsage()[1] == 1 and w.storageUsage()[2] == 1000

    # Another folder: what is kept moves there; the results come back from it
    values = {'storeSessionResults': False, 'keepResults': True, 'cacheLimit': 2 ** 30, 'wavefunctionLimit': 2 ** 20,
              'folder': str(second)}
    w.setStorage(values)
    assert w.resultsCache.folder == second / 'results' and len(w.resultsCache.entries()) == 1
    assert (second / 'symmetry' / 'm1.npy').exists() and not (first / 'results').exists()
    assert w.wavefunctionCacheLimit() == 2 ** 20 and not w.storeSessionResults()
    w.openDataset(bii3)
    assert len(w.calculations.dispPoints) == 2
    assert w.sessionContent()[0]['results'] == {}            # not stored in sessions now

    # A limit below what is kept: the oldest go at once
    w.openDataset(bn)
    w.setStorage(dict(values, cacheLimit=1))
    assert w.resultsCache.entries() == []
    # Back to the default folder: no folder in the settings
    w.setStorage(dict(values, folder=str(main_window.defaultStorageFolder())))
    assert w.settings.value('cacheFolder') == ''
