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
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')

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
    assert w.sessionPath == str(path.resolve()) and w.windowTitle().startswith('setup — BiI3_Bulk_8x8x8')
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
    assert w2.sessionPath is None and not w2.windowTitle().startswith('setup')
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
