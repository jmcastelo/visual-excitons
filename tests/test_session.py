"""Session files: format, results and the whole setup through the main window."""

import json
import os
import zipfile

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QQuaternion, QVector3D, QColor

from visual_excitons.core.session import (writeSession, readSession, datasetFingerprint, fingerprintsMatch,
                                          SessionError, SESSION_FORMAT, SESSION_VERSION)
from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.style import AbsorptionStyle
from conftest import datasetPath


# Format

def test_round_trip(tmp_path):
    path = tmp_path / 'a.vxsession'
    manifest = {'page': np.int64(2), 'ranges': (np.float64(1.5), 3.0), 'nested': {'list': np.array([1, 2])}}
    arrays = {'x/y': np.arange(6.0).reshape(2, 3), 'n': np.array([1, 2, 3], dtype=np.int32)}
    writeSession(path, manifest, arrays, programVersion='9.9')
    loaded, loadedArrays = readSession(path)
    assert loaded['format'] == SESSION_FORMAT and loaded['version'] == SESSION_VERSION
    assert loaded['programVersion'] == '9.9' and 'saved' in loaded
    assert loaded['page'] == 2 and loaded['ranges'] == [1.5, 3.0] and loaded['nested'] == {'list': [1, 2]}
    np.testing.assert_array_equal(loadedArrays['x/y'], arrays['x/y'])
    assert loadedArrays['n'].dtype == np.int32
    # Without results, no results file
    writeSession(path, {'page': 0})
    assert readSession(path)[1] == {}
    assert [name for name in os.listdir(tmp_path)] == ['a.vxsession']   # no temporary files left


def test_unreadable_files(tmp_path):
    (tmp_path / 'text.vxsession').write_text('not a zip')
    with pytest.raises(SessionError, match='not a readable session'):
        readSession(tmp_path / 'text.vxsession')

    other = tmp_path / 'other.vxsession'
    with zipfile.ZipFile(other, 'w') as archive:
        archive.writestr('session.json', json.dumps({'format': 'something-else'}))
    with pytest.raises(SessionError, match='not a Visual Excitons session'):
        readSession(other)

    newer = tmp_path / 'newer.vxsession'
    with zipfile.ZipFile(newer, 'w') as archive:
        archive.writestr('session.json', json.dumps({'format': SESSION_FORMAT, 'version': SESSION_VERSION + 1,
                                                     'programVersion': '5.0'}))
    with pytest.raises(SessionError, match='newer version of Visual Excitons \\(5.0\\)'):
        readSession(newer)


def test_failed_save_leaves_the_previous_file(tmp_path, monkeypatch):
    path = tmp_path / 'a.vxsession'
    writeSession(path, {'page': 1})

    def diskFull(*args, **kwargs):
        raise OSError('No space left on device')
    monkeypatch.setattr(np, 'savez_compressed', diskFull)
    with pytest.raises(OSError):
        writeSession(path, {'page': 2}, {'x': np.zeros(3)})
    assert readSession(path)[0]['page'] == 1
    assert os.listdir(tmp_path) == ['a.vxsession']    # the temporary file was removed


def test_fingerprint(tmp_path):
    for directory, filename in (('save', 'ns.db1'), ('diagos', 'ndb.BS_diago_Q1'), ('diagos', 'ndb.BS_diago_Q2')):
        (tmp_path / directory).mkdir(exist_ok=True)
        (tmp_path / directory / filename).write_bytes(b'12345')
    dataset = {'save': str(tmp_path / 'save'), 'diago': str(tmp_path / 'diagos'), 'qp': None}
    saved = datasetFingerprint(dataset)
    assert saved['diago'][:2] == [2, 10] and fingerprintsMatch(datasetFingerprint(dataset), saved)

    # Touched (e.g. copied elsewhere): strict comparison fails, lenient passes
    os.utime(tmp_path / 'save' / 'ns.db1', ns=(1, 1))
    assert not fingerprintsMatch(datasetFingerprint(dataset), saved)
    assert fingerprintsMatch(datasetFingerprint(dataset), saved, strict=False)

    # Recomputed (another size, one more Q-point): no match at all
    (tmp_path / 'diagos' / 'ndb.BS_diago_Q3').write_bytes(b'1')
    assert not fingerprintsMatch(datasetFingerprint(dataset), saved, strict=False)
    assert not fingerprintsMatch(datasetFingerprint(dataset), {})


# Results

class FakeLattice:
    lat = np.eye(3) * 8.0
    atomic_numbers = [6]
    car_atomic_positions = np.zeros((1, 3))


def withResults(calc):
    """Synthetic results of every kind."""
    calc.qIndices = np.array([4, 0, 2])
    calc.collinear_qpoints = np.zeros((3, 3))
    calc.dispPoints = [[[0, 2.0], [1, 2.1], [2, 2.2]], [[0, 2.5], [1, 2.6], [2, 2.7]]]
    calc.dispXInter, calc.dispYInter = np.linspace(0, 2, 5), np.ones((2, 5))
    calc.dispersionAxes = {'xRange': [0, 2], 'yRange': [2.0, 2.7], 'specialPoints': [0, 2], 'labels': ['L', 'G']}
    curve = {'energy': np.linspace(1.5, 3, 4), 'absorption': np.ones(4), 'brightExcEnergy': np.array([2.1]),
             'brightExcAbsorption': np.array([1.0]), 'brightExcIntensities': np.array([1.0]),
             'brightExcIndices': np.array([2.0]), 'darkExcEnergy': np.array([2.0, 2.3]), 'range': (1.5, 3.0)}
    calc.excAbsData = [dict(curve, q=4, index=0, fixed=True), dict(curve, q=2, index=2, fixed=False)]
    calc.k, calc.bands, calc.weights = np.linspace(0, 1, 3), np.ones((2, 3)), np.ones((2, 3))
    calc.selectedExciton = (4, 2, 2.1)
    calc.lattice = FakeLattice()
    calc.waveFunction = np.random.default_rng(0).random((6, 6, 6))
    calc.tr4x4, calc.wfAtomPositions = np.eye(4), np.zeros((2, 3))
    calc.wfFixedParticle, calc.wfSupercell, calc.wfGrid = 'e', [3, 3, 1], [2, 2, 6]
    calc.wfFixedPosition, calc.wfExciton = [0.5, 0.0, 0.0], (4, 2)


def test_results_round_trip(qtbot):
    source = Calculations(Options(), synchronous=True)
    withResults(source)
    meta, arrays = source.resultsSnapshot()
    assert sorted(meta) == ['absorption', 'bands', 'dispersion', 'selectedExciton', 'waveFunction']
    assert arrays['waveFunction/density'].dtype == np.float32
    meta = json.loads(json.dumps(__import__('visual_excitons.core.session', fromlist=['jsonable']).jsonable(meta)))

    target = Calculations(Options(), synchronous=True)
    target.lattice = FakeLattice()
    style = AbsorptionStyle()
    target.excitonAbsorptionCurveAppended.connect(style.appendCurveStyle)
    target.excitonAbsorptionCurveRemoved.connect(style.removeCurveStyle)
    with qtbot.waitSignals([target.wfComputed, target.excitonSelected, target.excitonAbsorptionReady]):
        target.restoreResults(meta, arrays)

    assert target.dispPoints == source.dispPoints and list(target.qIndices) == [4, 0, 2]
    assert target.dispPointsData[1][2].i == 2 and target.dispPointsData[1][2].j == 2
    assert [(d['q'], d['fixed']) for d in target.excAbsData] == [(4, True), (2, False)]
    assert target.excAbsData[1]['data'][0].i == 2 and target.excAbsData[1]['data'][0].j == 2
    assert len(style.curveStyle.curvePens) == 2                        # styles in step with the curves
    np.testing.assert_allclose(target.waveFunction, source.waveFunction, atol=1e-6)
    assert target.wfSupercell == [3, 3, 1] and target.wfExciton == (4, 2) and target.wfFixedParticle == 'e'
    assert target.selectedExciton == (4, 2, 2.1)
    np.testing.assert_array_equal(target.bands, source.bands)

    # Without the wave function (it can be large)
    meta, arrays = source.resultsSnapshot(includeWaveFunction=False)
    assert 'waveFunction' not in meta and not any(name.startswith('waveFunction') for name in arrays)


# Through the main window

def shownTitle(window):
    """The title as shown: Qt replaces [*] with * when there are unsaved changes."""
    return window.windowTitle().replace('[*]', '*' if window.isWindowModified() else '')


def injectResults(window, wfShape=(54, 54, 18), supercell=(3, 3, 1)):
    """Give the window synthetic results as a calculation would (signals, curve styles...)."""
    from visual_excitons.core.session import jsonable
    source = Calculations(Options(), synchronous=True)
    withResults(source)
    source.waveFunction = np.random.default_rng(1).random(wfShape)
    source.wfSupercell, source.wfGrid = list(supercell), [n // s for n, s in zip(wfShape, supercell)]
    meta, arrays = source.resultsSnapshot()
    window.calculations.restoreResults(jsonable(meta), arrays)


@pytest.fixture
def newWindow(qtbot, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()

    def make():
        w = main_window.MainWindow()
        qtbot.addWidget(w)
        return w
    yield make
    from visual_excitons.gui.theme import themeManager
    themeManager().setMode('System')


def test_save_needs_a_dataset(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, 'information', lambda *args: shown.append(args[2]))
    newWindow().writeSessionFile(str(tmp_path / 'x.vxsession'))
    assert shown == ['Open a dataset first.'] and not (tmp_path / 'x.vxsession').exists()


@pytest.mark.data
def test_whole_setup_through_a_session_file(newWindow, tmp_path):
    import visual_excitons.gui.main_window as main_window
    folder = datasetPath('BiI3_Bulk_8x8x8')
    w = newWindow()
    w.openDataset(main_window.findDataset(folder))
    w.system.qPathLineEdit.setText('LGZF')
    assert w.system.setBrillouinZone()
    p3 = w.wavefunction.parameters3DWidget
    p3.colormapComboBox.setCurrentText('Magma')
    p3.setSupercell([3, 3, 1])
    injectResults(w)
    # The second absorption curve in its own color
    style = w.absorptionStyle
    style.setApplyToAllCurves(False)
    style.setCurrentCurveIndex(1)
    style.curveStyle.setCurveColor(QColor('#00c853'))
    style.setApplyToAllCurves(True)
    w.dispersionStyle.curveStyle.setCurveWidth(3)
    view = w.wavefunction.excitonWfWidget
    view.setCameraParams(rotation=QQuaternion.fromAxisAndAngle(QVector3D(0, 1, 0), 33.0), distance=4321.0)
    camera = view.cameraState()
    path = tmp_path / 'setup.vxsession'
    w.writeSessionFile(str(path))
    assert w.sessionPath == str(path.resolve()) and shownTitle(w).startswith('setup — BiI3_Bulk_8x8x8')
    w.close()

    w2 = newWindow()
    assert w2.recentSessionsMenu.actions()[0].text() == 'setup'
    w2.wavefunction.parameters3DWidget.colormapComboBox.setCurrentText('Greys')
    w2.openSession(str(path))
    c2 = w2.calculations
    assert 'with its results' in w2.statusBar().currentMessage()
    assert w2.options.getPathString() == 'LGZF' and w2.options.supercell() == [3, 3, 1]
    assert w2.wavefunction.parameters3DWidget.colormapComboBox.currentText() == 'Magma'
    assert c2.selectedExciton == (4, 2, 2.1) and len(c2.excAbsData) == 2 and c2.waveFunction.shape == (54, 54, 18)
    # The styles of the plots, each curve's too (restored after the curves)
    assert w2.absorptionStyle.curveStyle.curvePens[1].color().name() == '#00c853'
    assert w2.absorptionStyle.curveStyle.curvePens[0].color().name() != '#00c853'
    assert all(pen.width() == 3 for pen in w2.dispersionStyle.curveStyle.curvePens)
    restored = w2.wavefunction.excitonWfWidget.cameraState()
    np.testing.assert_allclose(restored['rotation'] + restored['center'] + [restored['distance']],
                               camera['rotation'] + camera['center'] + [camera['distance']], atol=1e-5)

    # Opening a dataset afterwards forgets the session: Save must not overwrite it
    w2.openDataset(main_window.findDataset(folder))
    assert w2.sessionPath is None and not shownTitle(w2).startswith('setup')
    w2.close()


@pytest.mark.data
def test_changed_or_moved_dataset(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    folder = datasetPath('BiI3_Bulk_8x8x8')
    w = newWindow()
    w.openDataset(main_window.findDataset(folder))
    injectResults(w)
    path = tmp_path / 'setup.vxsession'
    w.writeSessionFile(str(path))
    manifest, arrays = readSession(path)

    # The dataset changed since: parameters yes, results no
    changed = dict(manifest, fingerprint={key: [0, 0, 0] for key in manifest['fingerprint']})
    writeSession(path, changed, arrays)
    w2 = newWindow()
    w2.openSession(str(path))
    assert 'the dataset changed' in w2.statusBar().currentMessage() and w2.calculations.waveFunction is None

    # The dataset moved: located by the user, results kept (same sizes)
    moved = dict(manifest, dataset=dict(manifest['dataset'], save='/nowhere/save', diago='/nowhere/diagos'))
    writeSession(path, moved, arrays)
    monkeypatch.setattr(main_window.QMessageBox, 'question', lambda *args: main_window.QMessageBox.StandardButton.Open)
    monkeypatch.setattr(main_window.QFileDialog, 'getExistingDirectory', lambda *args, **kwargs: str(folder))
    w3 = newWindow()
    w3.openSession(str(path))
    assert w3.options.saveDir == str(folder / 'save')
    assert 'with its results' in w3.statusBar().currentMessage() and w3.calculations.waveFunction is not None

    # Not located: nothing opened
    monkeypatch.setattr(main_window.QMessageBox, 'question', lambda *args: main_window.QMessageBox.StandardButton.Cancel)
    w4 = newWindow()
    w4.openSession(str(path))
    assert w4.sessionPath is None


@pytest.mark.data
def test_unsaved_changes(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    from PySide6.QtWidgets import QMessageBox
    w = newWindow()
    w.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    w.updateModified()
    assert not w.isWindowModified()                              # no session: nothing to mark
    path = tmp_path / 'mine.vxsession'
    w.writeSessionFile(str(path))
    assert not w.isWindowModified() and shownTitle(w).startswith('mine — ')

    # A change: marked; undone: not any more
    p3 = w.wavefunction.parameters3DWidget
    original = p3.colormapComboBox.currentText()
    p3.colormapComboBox.setCurrentText('Magma' if original != 'Magma' else 'Inferno')
    w.updateModified()
    assert w.isWindowModified() and shownTitle(w).startswith('mine* — ')
    p3.colormapComboBox.setCurrentText(original)
    w.updateModified()
    assert not w.isWindowModified()

    # Opening or closing a section is not a change of the session; new results are
    next(iter(p3.sections.values())).setExpanded(False)
    w.updateModified()
    assert not w.isWindowModified()
    w.calculations.markResultsChanged()
    w.updateModified()
    assert w.isWindowModified()

    # Closing asks: Cancel keeps the window, Save saves and closes
    answers = []
    def answer(button):
        def ask(parent, title, text, buttons, default):
            answers.append(text)
            return button
        return ask
    monkeypatch.setattr(main_window.QMessageBox, 'warning', answer(QMessageBox.StandardButton.Cancel))
    assert not w.close() and 'mine has changes that are not saved' in answers[-1] and 'closing' in answers[-1]
    opened = []
    monkeypatch.setattr(main_window.QFileDialog, 'getExistingDirectory', lambda *args, **kwargs: opened.append(1) or '')
    w.chooseDataset()
    assert opened == [] and 'opening another dataset' in answers[-1]   # cancelled before choosing

    before = path.stat().st_mtime_ns
    monkeypatch.setattr(main_window.QMessageBox, 'warning', answer(QMessageBox.StandardButton.Save))
    assert w.close() and path.stat().st_mtime_ns != before


@pytest.mark.data
def test_discard_closes_without_saving(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    from PySide6.QtWidgets import QMessageBox
    w = newWindow()
    w.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    path = tmp_path / 'mine.vxsession'
    w.writeSessionFile(str(path))
    before = path.stat().st_mtime_ns
    w.calculations.markResultsChanged()
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: QMessageBox.StandardButton.Discard)
    assert w.close() and path.stat().st_mtime_ns == before
    # Not modified: closing does not ask
    w2 = newWindow()
    w2.openSession(str(path))
    w2.updateModified()
    assert not w2.isWindowModified() and w2.close()


# New sessions and the start page

def test_starts_empty_with_the_start_page(newWindow, tmp_path):
    from PySide6.QtCore import QSettings
    import json
    settings = QSettings('VisualExcitons', 'VisualExcitons')
    session = tmp_path / 'kept.vxsession'
    session.touch()
    settings.setValue('recentSessions', json.dumps([str(session), str(tmp_path / 'gone.vxsession')]))
    settings.setValue('recentDatasets', json.dumps([{'save': str(tmp_path / 'gone' / 'save')}]))
    w = newWindow()
    page = w.startPage
    assert w.dataset is None and w.options.saveDir == '' and not page.isHidden()
    assert w.wavefunction.excitonWfWidget.gizmo.isHidden()      # drawn over everything otherwise
    assert w.windowTitle() == 'Visual Excitons'
    # The recent ones, those missing disabled
    assert [(link.text(), link.isEnabled()) for link in page.sessionLinks] == [('kept', True), ('gone', False)]
    assert [link.isEnabled() for link in page.datasetLinks] == [False]
    assert page.sessionsEmpty.isHidden() and page.datasetsEmpty.isHidden()
    opened = []
    w.openSession = opened.append
    page.sessionLinks[0].click()
    assert opened == [str(session)]


@pytest.mark.data
def test_new_session(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    from PySide6.QtWidgets import QMessageBox
    folder = datasetPath('BiI3_Bulk_8x8x8')
    w = newWindow()
    w.openDataset(main_window.findDataset(folder))
    assert w.startPage.isHidden() and shownTitle(w) == 'Untitled — BiI3_Bulk_8x8x8 — Visual Excitons'
    gizmo = w.wavefunction.excitonWfWidget.gizmo
    assert not gizmo.isHidden()
    w.system.qPathLineEdit.setText('LGZF')
    assert w.system.setBrillouinZone()
    p3 = w.wavefunction.parameters3DWidget
    p3.colormapComboBox.setCurrentText('Magma')            # a preference: kept
    w.updateModified()
    assert not w.isWindowModified()                        # parameters alone: nothing to lose

    # Results not saved in a session: marked, and New session asks; Cancel keeps everything
    injectResults(w)
    w.spectra.inspector.nExcitonsSpinBox.setValue(10)      # a parameter of the dataset
    w.updateModified()
    assert w.isWindowModified() and shownTitle(w).startswith('Untitled* — ')
    answers = []
    def answer(button):
        def ask(parent, title, text, buttons, default):
            answers.append(text)
            return button
        return ask
    monkeypatch.setattr(main_window.QMessageBox, 'warning', answer(QMessageBox.StandardButton.Cancel))
    w.newSession()
    assert 'results of this session are not saved' in answers[-1] and 'starting a new session' in answers[-1]
    assert w.dataset is not None and w.calculations.hasResults()

    # Discard: the dataset closed, as before any was opened
    monkeypatch.setattr(main_window.QMessageBox, 'warning', answer(QMessageBox.StandardButton.Discard))
    w.newSession()
    assert w.dataset is None and w.options.saveDir == '' and w.options.qBZ is None and not w.options.qPoints
    assert not w.calculations.hasResults() and w.calculations.waveFunction is None
    assert not w.startPage.isHidden() and shownTitle(w) == 'Visual Excitons' and w.datasetLabel.text() == 'No dataset'
    assert w.system.saveDirEdit.text() == '' and w.system.hspTable.rowCount() == 0
    assert w.system.qPathLineEdit.text() == '' and not w.system.setPathButton.isEnabled()
    view = w.wavefunction.excitonWfWidget
    assert not view.latticeItems and not view.latticeBoundaryItems and view.cellLattice is None
    assert p3.colormapComboBox.currentText() == 'Magma' and gizmo.isHidden()
    # Nothing to lose now: no question
    answers.clear()
    w.newSession()
    assert answers == []

    # Opened again: its parameters and Q-path are back
    w.startPage.datasetLinks[0].click()
    assert w.options.nExcitons == 10 and w.options.getPathString() == 'LGZF'
    assert w.startPage.isHidden() and not gizmo.isHidden()


@pytest.mark.data
def test_saving_an_untitled_session_when_asked(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    from PySide6.QtWidgets import QMessageBox
    w = newWindow()
    w.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    injectResults(w)
    path = tmp_path / 'asked.vxsession'
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: QMessageBox.StandardButton.Save)
    # Save asks for a file: cancelled, nothing closes
    monkeypatch.setattr(main_window.QFileDialog, 'getSaveFileName', lambda *args, **kwargs: ('', ''))
    assert not w.close()
    monkeypatch.setattr(main_window.QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (str(path), ''))
    assert w.close() and path.is_file()


# Directories chosen by hand in the System panel

@pytest.mark.data
def test_directories_chosen_by_hand(newWindow, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    bii3 = datasetPath('BiI3_Bulk_8x8x8')
    w = newWindow()
    w.openDataset(main_window.findDataset(bii3))
    warnings = []
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: warnings.append(args[2]))

    # Folders without the databases: said so, nothing changes
    empty = tmp_path / 'empty'
    empty.mkdir()
    for kind in ('save', 'diago', 'qp'):
        before = (w.options.saveDir, w.options.diagoDir, w.options.qpDir)
        w.system.directoryChosen.emit(kind, str(empty))
        assert (w.options.saveDir, w.options.diagoDir, w.options.qpDir) == before
        assert 'The directory in use stays' in warnings[-1]
    assert w.system.diagoDirEdit.text() == w.options.diagoDir and w.options.qPoints

    # Another BSE directory: part of the dataset, remembered; results from the old one go
    injectResults(w)
    partial = tmp_path / 'partial'
    partial.mkdir()
    for n in (1, 2):
        (partial / f'ndb.BS_diago_Q{n}').symlink_to(bii3 / 'diagos' / f'ndb.BS_diago_Q{n}')
    w.system.directoryChosen.emit('diago', str(partial))
    assert w.options.diagoDir == str(partial) and w.options.qPoints == [0, 1]
    assert w.dataset['diago'] == str(partial) and w.recentDatasets()[0]['diago'] == str(partial)
    assert not w.calculations.hasResults()

    # Without the QP corrections: the spectra go, the wave function stays
    injectResults(w)
    w.system.calcTypeComboBox.setCurrentIndex(0)
    assert w.dataset['gw'] is False and w.recentDatasets()[0]['gw'] is False
    assert not len(w.calculations.dispPoints) and w.calculations.waveFunction is not None

    # Another SAVE directory: another dataset, asked first (the wave function is not saved)
    from PySide6.QtWidgets import QMessageBox
    w.spectra.inspector.nExcitonsSpinBox.setValue(9)
    bn = datasetPath('BN')
    answers = []
    monkeypatch.setattr(main_window.QMessageBox, 'warning',
                        lambda *args: answers.append(args[2]) or QMessageBox.StandardButton.Cancel)
    w.system.directoryChosen.emit('save', str(main_window.findDataset(bn)['save']))
    assert 'opening another dataset' in answers[-1] and w.dataset['save'] == str(bii3 / 'save')
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: QMessageBox.StandardButton.Discard)
    w.system.directoryChosen.emit('save', str(main_window.findDataset(bn)['save']))
    # BiI3 keeps its parameters
    assert w.dataset['save'] == str(main_window.findDataset(bn)['save']) and w.dataset['diago'] == str(partial)
    assert w.calculations.waveFunction is None and w.options.nExcitons == 6
    assert [d['save'] for d in w.recentDatasets()][:2] == [w.dataset['save'], str(bii3 / 'save')]
    assert w.recentDatasets()[1]['state']['spectra/excitons'] == 9


@pytest.mark.data
def test_export_choices_are_part_of_the_session(newWindow, tmp_path):
    """One session per figure: the figure and 3D image export choices are saved with it."""
    import json
    import visual_excitons.gui.main_window as main_window
    w = newWindow()
    w.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    settings = w.settings
    settings.setValue('figureExport/options', json.dumps({'width': 12.0, 'panels': ['absorption'], 'dpi': 600}))
    settings.setValue('imageExport/scale', 2)
    settings.setValue('imageExport/transparent', True)
    path = tmp_path / 'figure.vxsession'
    w.writeSessionFile(str(path))

    # Other choices in a later export: the session is modified
    settings.setValue('figureExport/options', json.dumps({'width': 8.0}))
    settings.setValue('imageExport/transparent', False)
    w.updateModified()
    assert w.isWindowModified()

    # Opening it brings its choices back for the next export
    w.openSession(str(path))
    assert json.loads(settings.value('figureExport/options')) == {'width': 12.0, 'panels': ['absorption'], 'dpi': 600}
    assert settings.value('imageExport/transparent', type=bool) and settings.value('imageExport/scale', type=int) == 2
    w.updateModified()
    assert not w.isWindowModified()


@pytest.mark.data
def test_every_control_is_part_of_the_session(newWindow, monkeypatch):
    """
    Changing any control of the panels marks the session modified (so it is
    saved in it), except those that are not part of a setup on purpose.
    """
    from PySide6.QtWidgets import (QWidget, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QAbstractButton, QLineEdit,
                                   QAbstractSpinBox, QColorDialog, QFontDialog, QMessageBox)
    import visual_excitons.gui.main_window as main_window
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: QMessageBox.StandardButton.Cancel)
    w = newWindow()
    w.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    w.system.qPathLineEdit.setText('LGZF')
    assert w.system.setBrillouinZone()
    w.sessionPath = 'compared.vxsession'
    w.markSessionSaved()
    system, spectra, p3 = w.system, w.spectra.inspector, w.wavefunction.parameters3DWidget
    excluded = {
        # Applied with Set Q-path, then saved (the path, its sampling)
        system.qPathLineEdit, system.interpolationComboBox, system.numPointsSpin, system.densitySpin,
        # Directories: applied when valid (see test_directories_chosen_by_hand)
        system.saveDirEdit, system.diagoDirEdit, system.qpDirEdit,
        # The Q-point of the next spectrum to add: a chooser, not a setting
        spectra.qPointComboBox,
        # The Appearance panel's own preference
        w.appearancePanel.sameAxesCheckBox,
        *p3.shownParticleLineEdits,                  # shown only with a cell shift (linked to the computed ones)
    }
    dialogs = w.appearancePanel.findChildren(QColorDialog) + w.appearancePanel.findChildren(QFontDialog)
    inDialog = {id(child) for dialog in dialogs for child in dialog.findChildren(QWidget)}

    def change(widget):
        if isinstance(widget, QComboBox):
            if widget.count() < 2:
                return False
            widget.setCurrentIndex((widget.currentIndex() + 1) % widget.count())
            widget.activated.emit(widget.currentIndex())
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            old = widget.value()
            widget.stepBy(2 if widget.value() + 2 * widget.singleStep() <= widget.maximum() else -2)
            widget.editingFinished.emit()
            return widget.value() != old
        elif isinstance(widget, QSlider):
            widget.setValue(widget.value() + (2 if widget.value() + 2 <= widget.maximum() else -2))
        elif isinstance(widget, QAbstractButton):
            old = widget.isChecked()
            widget.click()
            return widget.isChecked() != old
        elif isinstance(widget, QLineEdit):
            try:
                widget.setText(str(float(widget.text()) + 0.1))
            except ValueError:
                return False
            widget.editingFinished.emit()
        return True

    missing = []
    for root in (system, spectra, w.wavefunction.inspector, w.appearancePanel):
        for widget in root.findChildren(QWidget):
            if widget in excluded or id(widget) in inDialog:
                continue
            if isinstance(widget, QAbstractButton) and not widget.isCheckable():
                continue
            if isinstance(widget, QLineEdit) and (widget.isReadOnly() or isinstance(widget.parentWidget(),
                                                                                    (QAbstractSpinBox, QComboBox))):
                continue
            if not isinstance(widget, (QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QAbstractButton, QLineEdit)):
                continue
            w.markSessionSaved()
            if not change(widget):
                continue
            w.updateModified()
            if not w.isWindowModified():
                missing.append(f'{type(widget).__name__} {widget.text() if isinstance(widget, QAbstractButton) else ""}'
                               f' ({widget.toolTip().splitlines()[0] if widget.toolTip() else "no tooltip"})')
    assert not missing, 'Not in sessions: ' + '; '.join(missing)


@pytest.mark.data
def test_every_button_is_part_of_the_session(newWindow, monkeypatch):
    """Buttons that change the setup (view, cell origin, cut plane, Q-path, styles) mark the session modified."""
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import QWidget, QAbstractButton, QToolButton, QColorDialog, QFontDialog, QTabBar, QMessageBox
    import visual_excitons.gui.main_window as main_window
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: QMessageBox.StandardButton.Cancel)
    w = newWindow()
    w.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    w.system.qPathLineEdit.setText('LGZF')
    assert w.system.setBrillouinZone()
    injectResults(w)                              # curves to style, a wave function
    w.sessionPath = 'compared.vxsession'
    panel, p3, view = w.appearancePanel, w.wavefunction.parameters3DWidget, w.wavefunction.excitonWfWidget
    # Not part of a setup: files and checks, calculations and exports (their results are, see the other tests)
    notSetup = {'Browse…', 'Details…', 'Check all BSE', 'Compute dispersion', 'Add spectrum',
                'Compute its wave function', 'Compute wave function', 'Export figure…', 'Image…', 'Density…'}
    # Something for each button to change
    before = {'Set Q-path': lambda: w.system.qPathLineEdit.setText('GLZ'),
              'Apply': lambda: [edit.setText(text) for edit, text in zip(p3.viewDirLineEdits, ('1', '0', '0'))],
              'Reset': lambda: p3.setCellOrigin([0.25, 0.0, 0.0]),
              'Center': lambda: view.setCameraState({**view.cameraState(), 'center': [9.0, 9.0, 9.0]})}
    dialogs = panel.findChildren(QColorDialog) + panel.findChildren(QFontDialog)
    inDialog = {id(child) for dialog in dialogs for child in dialog.findChildren(QWidget)}

    missing = []
    for root in (w.system, w.spectra.inspector, w.wavefunction.inspector, panel):
        for button in root.findChildren(QAbstractButton):
            if (button.isCheckable() or id(button) in inDialog or button.text() in notSetup
                    or isinstance(button.parentWidget(), QTabBar)                    # tab scroll arrows
                    or (isinstance(button, QToolButton) and button.text())           # section headers
                    or button is w.system.hspTable.findChild(QAbstractButton)):      # table corner
                continue
            before.get(button.text(), lambda: None)()
            w.markSessionSaved()
            button.click()
            if panel.colorDialog.isVisible():
                panel.colorDialog.setCurrentColor(QColor('#123456'))
                panel.colorDialog.accept()
            if panel.fontDialog.isVisible():
                panel.fontDialog.setCurrentFont(QFont('Serif', 17))
                panel.fontDialog.accept()
            w.updateModified()
            if not w.isWindowModified():
                missing.append(f'"{button.text()}" ({button.toolTip().splitlines()[0] if button.toolTip() else type(button).__name__})')
    assert not missing, 'Not in sessions: ' + '; '.join(missing)
