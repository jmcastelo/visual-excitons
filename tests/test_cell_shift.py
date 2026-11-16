"""The origin of the cell shown: layers centred, and everything shifted together."""

import numpy as np
import pytest

from visual_excitons.core.cellshift import (detectLayer, shiftAtoms, rollDensity, shiftCrystal, snapShift,
                                            periodicAxes, seamAxes, reducedPositions, wrapShift)
from visual_excitons.core.analysis import radialDistribution, gridPositions
from conftest import datasetPath

# A WSe2-like monolayer: W at c = 0, Se at ±0.07, 43.9 Bohr of cell along c
CELL = np.array([[6.279, 0.0, 0.0], [-3.140, 5.438, 0.0], [0.0, 0.0, 43.867]])
ATOMS = np.array([[0.0, 0.0, 0.0], [1 / 3, 2 / 3, 0.0724], [1 / 3, 2 / 3, -0.0724]]) @ CELL


def test_layer_detected_and_centred():
    axis, shift = detectLayer(CELL, ATOMS)
    assert axis == 2 and shift == pytest.approx(0.5)
    centred = reducedPositions(CELL, shiftAtoms(CELL, ATOMS, [0, 0, shift]))[:, 2]
    assert sorted(centred) == pytest.approx([0.4276, 0.5, 0.5724])
    # Bulk: no vacuum
    bulk = np.eye(3) * 10.0
    assert detectLayer(bulk, np.array([[0, 0, 0], [5, 5, 5]], dtype=float)) is None
    # A thin vacuum counts only with a single k-point along it (a 2D calculation)
    thin = np.diag([4.7, 4.7, 12.0])
    atoms = np.array([[0, 0, 6.0], [2.35, 2.35, 6.0]])
    assert detectLayer(thin, atoms) is None
    assert detectLayer(thin, atoms, grid=[18, 18, 1]) == (2, pytest.approx(0.0))     # already centred


def test_shifts():
    assert wrapShift(0.75) == pytest.approx(-0.25) and wrapShift(-0.5) == pytest.approx(0.5)
    assert snapShift([0.33, 0.5, 0.1], [12, 12, 10]) == pytest.approx([4 / 12, 0.5, 0.1])
    density = np.zeros((4, 4, 8))
    density[0, 0, 0] = 1.0
    rolled = rollDensity(density, [0, 0, 0.5], [4, 4, 8])
    assert rolled[0, 0, 4] == 1.0 and rolled.sum() == 1.0
    assert rollDensity(density, [0, 0, 0], [4, 4, 8]) is density
    np.testing.assert_allclose(shiftCrystal([1.2, 0.0, 0.9], [0.0, 0.5, 0.5], [3, 1, 1]), [1.2, 0.5, 0.4])


def test_periodic_axes_and_seams():
    assert periodicAxes([3, 3, 1], [72, 72, 1]) == [False, False, True]
    assert periodicAxes([3, 3, 1], None) == [False, False, False]
    density = np.ones((6, 6, 6))
    assert seamAxes(density, [0.5, 0, 0.5], [3, 3, 1], [72, 72, 1]) == [0]        # c wraps exactly
    density[[0, -1], :, :] = 0.0
    assert seamAxes(density, [0.5, 0, 0], [3, 3, 1], [72, 72, 1]) == []           # decayed at the faces of a


def test_distances_to_the_nearest_image():
    """A monolayer exciton with the hole on the face of the cell: straight distances overestimate it."""
    shape = (24, 24, 48)
    voxels = CELL * np.array([3, 3, 1])[:, None] / np.array(shape)[:, None]
    hole = np.array([1.5, 1.5, 0.0]) @ CELL                                        # c = 0, on the face
    offsets = gridPositions(shape, voxels) - hole
    offsets[..., 2] -= np.round(offsets[..., 2] / CELL[2, 2]) * CELL[2, 2]        # the periodic distance
    density = np.exp(-np.sum(offsets ** 2, axis=-1) / (2 * 3.0 ** 2))
    straight = radialDistribution(density, voxels, hole)
    periodic = radialDistribution(density, voxels, hole, periodic=[False, False, True])
    assert periodic['mean'] == pytest.approx(3.0 * np.sqrt(8 / np.pi), rel=0.05)
    assert straight['mean'] > 3 * periodic['mean']                                 # the half at the top counted far
    assert periodic['boundary'] < straight['boundary'] / 10                        # c faces are not cuts


@pytest.mark.data
def test_wse2_layer_centred_in_the_window(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window.openDataset(main_window.findDataset(datasetPath('WSe2')))
    p3, panels = window.wavefunction.parameters3DWidget, window.wavefunction
    assert p3.layer == (2, pytest.approx(0.5)) and p3.centreLayerCheckBox.isChecked()
    assert p3.cellShift() == pytest.approx([0, 0, 0.5]) and not p3.originSpinBoxes[2].isEnabled()
    assert window.calculations.kGrid() == [72, 72, 1]

    # The atoms drawn are in the middle of the cell along c
    vertices = np.concatenate([item.opts['meshdata'].vertexes() for item in panels.excitonWfWidget.latticeItems])
    heights = vertices[:, 2] / CELL[2, 2]
    assert 0.3 < heights.min() and heights.max() < 0.7

    # Unticked: the cell of the calculation; the other axes can be shifted by hand, and reset
    p3.centreLayerCheckBox.setChecked(False)
    assert p3.cellShift() == pytest.approx([0, 0, 0]) and p3.originSpinBoxes[2].isEnabled()
    p3.setCellOrigin([0.25, 0, 0])
    assert p3.cellShift() == pytest.approx([0.25, 0, 0])
    p3.centreLayerCheckBox.setChecked(True)
    p3.originSpinBoxes[0].setValue(0.0)
    p3.centreOnFixedParticle()                         # the hole at (0, 0, 0): to the middle
    assert p3.cellShift() == pytest.approx([0.5, 0.5, 0.5])

    # Kept with the dataset
    window.close()
    again = main_window.MainWindow()
    qtbot.addWidget(again)
    assert again.wavefunction.parameters3DWidget.cellShift() == pytest.approx([0.5, 0.5, 0.5])


def test_export_with_and_without_the_shift(window_with_wave_function, tmp_path, qtbot):
    window, calc = window_with_wave_function
    p3 = window.wavefunction.parameters3DWidget
    p3.setCellOrigin([0, 0, 0.5])
    from test_export import readCube
    for shifted, name in ((True, 'shown.cube'), (False, 'computed.cube')):
        p3.exportShiftedCheckBox.setChecked(shifted)
        target = tmp_path / name
        with qtbot.waitSignal(calc.densityExported, timeout=20000):
            window.calculations.exportDensity(str(target), window.wavefunction.shownShift() if shifted else None)
    (shownHeader, shape, _, _, shownValues, _), (_, _, _, _, computedValues, _) = (
        readCube(tmp_path / 'shown.cube'), readCube(tmp_path / 'computed.cube'))
    shown, computed = shownValues.reshape(shape), computedValues.reshape(shape)
    halfCell = calc.wfGrid[2] // 2                     # half a cell, not half the supercell
    np.testing.assert_allclose(shown, np.roll(computed, halfCell, axis=2), atol=1e-4)
    assert 'cell origin shifted by 0.0000 0.0000 0.5000' in ' '.join(shownHeader)


@pytest.fixture
def window_with_wave_function(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    from test_gui import fakeWaveFunction
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    fakeWaveFunction(window.calculations, sigma=2.0)
    return window, window.calculations


@pytest.mark.data
def test_position_as_shown_and_as_computed(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window.openDataset(main_window.findDataset(datasetPath('WSe2')))
    p3, options = window.wavefunction.parameters3DWidget, window.options
    form = p3.calculationForm
    shown = lambda: [float(edit.text()) for edit in p3.shownParticleLineEdits]

    # Layer centred: both rows, linked; the hole on W at (0, 0, 0) is drawn at c = 0.5
    assert form.isRowVisible(p3.particleShownWidget)
    assert form.labelForField(p3.particleComputedWidget).text() == 'Position as computed:'
    assert shown() == pytest.approx([0, 0, 0.5])

    # Typing c = 0.5 as shown (the layer) gives c = 0 as computed, not the middle of the vacuum
    for edit, text in zip(p3.shownParticleLineEdits, ('0.3333', '0.6667', '0.5')):
        edit.setText(text)
    p3.shownPositionEdited()
    assert options.particlePosition() == pytest.approx([0.3333, 0.6667, 0.0], abs=1e-4)
    assert p3.zParticlePosLineEdit.text() == '0.0000'

    # Editing the position computed updates the one shown
    p3.zParticlePosLineEdit.setText('0.1')
    p3.particlePositionChanged()
    assert shown()[2] == pytest.approx(0.6)

    # No shift: a single row, the two would agree
    p3.centreLayerCheckBox.setChecked(False)
    assert not form.isRowVisible(p3.particleShownWidget)
    assert form.labelForField(p3.particleComputedWidget).text() == 'Position (a, b, c):'
    # A shift by hand brings it back
    p3.setCellOrigin([0.25, 0, 0])
    assert form.isRowVisible(p3.particleShownWidget) and shown()[0] == pytest.approx(0.5833, abs=1e-4)
