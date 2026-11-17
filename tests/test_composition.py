"""The composition of the selected exciton: its weights in reciprocal space, the Composition panel."""

import contextlib
import io

import numpy as np
import pytest

from conftest import datasetPath


def quietly(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call(*args, **kwargs)


@pytest.mark.data
def test_weights_agree_with_yambopy_and_put_the_hole_at_k_minus_q():
    """At Γ, as YamboPy's own weights; at finite Q, the hole where the transition energies are lowest."""
    from yambopy import YamboLatticeDB, YamboExcitonDB, YamboElectronsDB
    from visual_excitons.yambopy_ext.bse.exciton_kspace import exciton_kspace, hole_kpoint_indices
    folder = datasetPath('BiI3_Bulk_8x8x8')
    lattice = YamboLatticeDB.from_db(str(folder / 'save' / 'ns.db1'))
    gamma = YamboExcitonDB.from_db_file(lattice, filename='ndb.BS_diago_Q1', folder=str(folder / 'diagos'), neigs=3)
    result = exciton_kspace(gamma, 1, degenerate=False)
    reference = gamma.get_exciton_weights([1])               # (k, band), the hole's weight at the electron's k
    assert np.allclose(2 * result['electron'], reference.sum(axis=1))
    bands = {**result['valence'], **result['conduction']}
    assert all(bands[b] == pytest.approx(reference[:, b - 1].sum()) for b in bands)

    # Q12 = (0, 1/8, -1/8): pairing the valence band at k-Q (not k+Q) with the conduction band
    # at k gives the transitions of the lowest exciton their lowest DFT energies
    electrons = quietly(YamboElectronsDB.from_db_file, folder=str(folder / 'save'), Expand=True)
    energies = electrons.eigenvalues[0]
    finite = YamboExcitonDB.from_db_file(lattice, filename='ndb.BS_diago_Q12', folder=str(folder / 'diagos'), neigs=1)
    result = exciton_kspace(finite, 1)
    k, v, c = (finite.table[:, i] - 1 for i in range(3))
    weights = np.abs(finite.eigenvectors[0]) ** 2
    mean = {}
    for sign in (-1, 1):
        holes = hole_kpoint_indices(lattice.red_kpoints, -sign * result['red_qpoint'])     # index of k + sign Q
        mean[sign] = np.sum(weights * (energies[k, c] - energies[holes[k], v]))
    assert mean[-1] < mean[1] - 0.02
    assert not np.allclose(result['hole'], result['electron'])


def test_special_points_and_csv():
    from visual_excitons.core.kspace import nearestSpecialPoint, compositionCSV
    rlat = np.linalg.inv([[1, 0, 0], [-0.5, np.sqrt(3) / 2, 0], [0, 0, 6]]).T
    special = {'G': [0, 0, 0], 'M': [0.5, 0, 0], 'K': [1 / 3, 1 / 3, 0]}
    assert nearestSpecialPoint([1 / 3, 1 / 3, 0], special, rlat) == 'K'
    assert nearestSpecialPoint([-1 / 3, -1 / 3, 0], special, rlat) == "K'"        # time-reversed partner
    assert nearestSpecialPoint([-0.5, 1, 0], special, rlat) == 'M'                # M, moved by reciprocal vectors
    assert nearestSpecialPoint([0.1, 0.1, 0], special, rlat) == ''

    class Lattice:
        red_kpoints = np.array([[0, 0, 0], [0.5, 0, 0]])
        rlat = np.eye(3)
    composition = {'qIndex': 0, 'excIndex': 2, 'states': [2, 3], 'energy': 1.5, 'red_qpoint': np.zeros(3),
                   'electron': np.array([0.75, 0.25]), 'hole': np.array([0.75, 0.25]),
                   'pairs': [(4, 5, 1.0)], 'valence': {4: 1.0}, 'conduction': {5: 1.0}}
    text = compositionCSV(composition, Lattice(), 'Test')
    lines = text.splitlines()
    assert 'exciton 2 at Q1' in lines[0] and 'Test' in lines[0] and 'states summed: 2 3' in lines[1]
    assert lines[4].endswith(',0.75000000,0.75000000') and '4,5,1.00000000' in lines


@pytest.fixture
def window(qtbot, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    w = main_window.MainWindow()
    qtbot.addWidget(w)
    yield w
    from visual_excitons.gui.theme import themeManager
    themeManager().setMode('System')


def select(window, qIndex, excIndex):
    window.calculations.selectedExciton = (qIndex, excIndex, 2.0)
    window.calculations.excitonSelected.emit(qIndex, excIndex, 2.0)


@pytest.mark.data
def test_composition_panel(window, qtbot, tmp_path):
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    panel, calc = window.compositionPanel, window.calculations
    window.panels.docks['composition'].toggleView(False)

    # Closed: nothing computed when an exciton is selected
    select(window, 11, 1)
    assert calc.composition is None
    # Shown (the button of the Selected exciton section): computed for it
    window.spectra.inspector.showCompositionButton.click()
    assert window.panels.isShown('composition')
    qtbot.waitUntil(lambda: calc.composition is not None, timeout=60000)
    c = calc.composition
    assert (c['qIndex'], c['excIndex']) == (11, 1) and panel.composition is c
    assert 'Q12' in panel.infoLabel.text() and 'k−Q' in panel.infoLabel.text()
    assert panel.pairsTable.rowCount() > 1 and panel.pairsTable.item(0, 2).text().endswith('%')
    assert any(panel.kpointsTable.item(r, 0).text() == 'Hole' for r in range(panel.kpointsTable.rowCount()))

    # Bulk: the zone in 3D by default, the points above the threshold drawn
    assert not panel.isLayer() and panel.is3D() and not panel.viewComboBox.isHidden()
    from visual_excitons.gui.sorted_mesh_item import SortedMeshItem
    spheres = [item for item in panel.view3D.items3D if isinstance(item, SortedMeshItem)]
    assert len(spheres) == 1                                 # one mesh of translucent spheres
    drawn = panel.spheresShown
    panel.thresholdSpinBox.setValue(50.0)
    assert 0 < panel.spheresShown < drawn
    # At finite Q the electron and the hole differ: the particle chosen changes the map
    assert panel.particleComboBox.isEnabled()
    electron = panel.weights().copy()
    panel.particleComboBox.setCurrentText('Hole')
    assert not np.allclose(panel.weights(), electron)
    # The plane through Γ, then the sum over the planes
    panel.viewComboBox.setCurrentText('Plane')
    assert not panel.is3D() and panel.planeSpinBox.value() == 0 and len(panel.tiles.picture.data()) > 0
    panel.planeSpinBox.setValue(panel.planeSpinBox.minimum())
    assert panel.planeSpinBox.text() == 'Sum'
    assert 'summed' in panel.kspaceNote.text()

    # Another exciton of the same Q-point: from the database already read
    cached = dict(calc.compositionCache)
    select(window, 11, 2)
    qtbot.waitUntil(lambda: calc.composition['excIndex'] == 2, timeout=60000)
    assert calc.compositionCache.keys() == cached.keys()
    assert calc.composition['states'][0] == 2
    # Each state alone: the setting of the Selected exciton section, shared (its copy follows)
    window.spectra.inspector.sumDegenerateCheckBox.setChecked(False)
    assert not window.wavefunction.parameters3DWidget.sumDegenerateCheckBox.isChecked()
    qtbot.waitUntil(lambda: not calc.composition['degenerate'], timeout=60000)
    assert calc.composition['states'] == [2]

    # In sessions: shown at once when opened, not computed again
    path = tmp_path / 'composition.vxsession'
    window.writeSessionFile(str(path))
    window.openSession(str(path))
    assert calc.composition is not None and calc.composition['states'] == [2] and panel.composition is calc.composition
    assert panel.viewComboBox.currentText() == 'Plane' and not window.options.sumDegenerate


@pytest.mark.data
def test_layer_has_a_plane_map_only(window, qtbot, monkeypatch, tmp_path):
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('WSe2')))
    panel, calc = window.compositionPanel, window.calculations
    window.showPanel('composition')
    select(window, 0, 1)
    qtbot.waitUntil(lambda: calc.composition is not None, timeout=60000)
    assert panel.isLayer() and not panel.is3D() and panel.viewComboBox.isHidden()
    # At Γ the electron and the hole are at the same k-points: no choice
    assert not panel.particleComboBox.isEnabled() and panel.kspaceNote.text().startswith('Electron and hole')
    # The A exciton: at K and K'
    rows = [panel.kpointsTable.item(r, 2).text() for r in range(2)]
    assert sorted(rows) == ['K', 'K′']
    # Exported
    out = tmp_path / 'composition.csv'
    monkeypatch.setattr(main_window.QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (str(out), ''))
    window.exportComposition()
    assert out.read_text().startswith('# Visual Excitons: composition of exciton 1 at Q1')


@pytest.mark.data
def test_problems_are_said_in_the_panel(window, qtbot, tmp_path):
    """Computed on selection: a Q-point not computed is said in the panel, not in a dialog."""
    import visual_excitons.gui.main_window as main_window
    from test_sparse_q_points import partialDataset
    window.openDataset(main_window.findDataset(partialDataset(tmp_path, (1, 2))))
    window.showPanel('composition')
    select(window, 4, 1)                                    # Q5: not in the BSE directory
    assert window.calculations.composition is None
    assert window.compositionPanel.infoLabel.text().startswith('Q-point 5 was not computed')
    select(window, 1, 1)                                    # Q2: there
    qtbot.waitUntil(lambda: window.calculations.composition is not None, timeout=60000)
    assert 'Q2' in window.compositionPanel.infoLabel.text()
