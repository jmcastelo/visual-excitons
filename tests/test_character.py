"""The symmetry and spin of excitons (Composition panel, Symmetry and spin tab)."""

import contextlib
import io

import numpy as np
import pytest

from conftest import datasetPath


def quietly(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call(*args, **kwargs)


class Context:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def character(q, exc, tmp_path, axis='z', symmetryCache=None, wavefunctionCache=None):
    from visual_excitons.core.calculations import computeCharacter
    folder = datasetPath('BiI3_Bulk_8x8x8')
    return quietly(computeCharacter, Context(), None, str(folder / 'save'), str(folder / 'diagos'),
                   f'ndb.BS_diago_Q{q}', q - 1, exc, axis=axis,
                   wavefunctionCache={} if wavefunctionCache is None else wavefunctionCache,
                   symmetryCache={} if symmetryCache is None else symmetryCache, diskCache=str(tmp_path / 'cache'))


@pytest.mark.data
def test_trivial_little_group_and_disk_cache(tmp_path, monkeypatch):
    """Q12 = (0, 1/8, -1/8) of BiI3: only the identity leaves it unchanged, so every exciton is A."""
    wavefunctions = {}
    result = character(12, 1, tmp_path, wavefunctionCache=wavefunctions)
    assert result['pointGroup'] == 'C1' and result['irreps'] == 'A' and result['operations'] == 1
    assert len(result['spin']['total']) == len(result['states'])
    assert np.allclose(np.add(result['spin']['electron'], result['spin']['hole']), result['spin']['total'])
    assert list((tmp_path / 'cache').glob('dmat_*_0.npy'))                    # kept on disk

    # Another session: the matrices from the disk, not computed again
    from yambopy.dbs.wfdb import YamboWFDB

    def refuse(*args, **kwargs):
        raise AssertionError('computed again')
    monkeypatch.setattr(YamboWFDB, 'Dmat', refuse)
    again = character(12, 2, tmp_path, wavefunctionCache=wavefunctions)
    assert again['irreps'] == 'A'


@pytest.mark.data
def test_spin_matrix_elements_agree_with_yambopy():
    """On a few bands (YamboPy's own needs 5.9 GB for all 14): the same matrix elements, to 1e-12."""
    from yambopy import YamboLatticeDB
    from yambopy.dbs.wfdb import YamboWFDB
    from visual_excitons.yambopy_ext.bse.exciton_spin import spin_matrix_elements, spin_operator
    folder = datasetPath('BiI3_Bulk_8x8x8')
    lattice = quietly(YamboLatticeDB.from_db_file, str(folder / 'save' / 'ns.db1'))
    wfdb = quietly(YamboWFDB, path=str(folder / 'save'), save='.', latdb=lattice, bands_range=[147, 150])
    for direction in ((0, 0, 1), (1, 0, 0)):
        operator = spin_operator(direction)
        assert np.allclose(spin_matrix_elements(wfdb, operator), quietly(wfdb.get_spin_m_e_BZ, s_z=operator),
                           atol=1e-12)


@pytest.mark.slow
@pytest.mark.data
def test_symmetry_at_gamma(tmp_path):
    """BiI3 at Γ: the little group S6 (the point group of R-3); the lowest exciton is Au (dark: odd under
    inversion, but it is not the dipole-allowed Eu of the bright ones), as YamboPy's compute_exc_rep finds."""
    result = character(1, 1, tmp_path)
    assert result['pointGroup'] == 'S6' and result['irreps'] == 'Au' and result['states'] == [1]
    pair = character(1, 2, tmp_path)
    assert pair['states'] == [2, 3] and pair['irreps'] == 'E_1u + E_2u'


def test_character_in_the_panel_and_sessions(qtbot):
    from visual_excitons.gui.composition_panel import CompositionPanel
    from visual_excitons.core.calculations import jsonableCharacter
    panel = CompositionPanel()
    qtbot.addWidget(panel)
    assert not panel.analyseButton.isEnabled()
    panel.setSelectedExciton((0, 2, 2.1))
    assert panel.analyseButton.isEnabled() and 'not analysed yet' in panel.characterLabel.text()
    requested = []
    panel.characterRequested.connect(requested.append)
    panel.spinAxisComboBox.setCurrentIndex(3)
    panel.analyseButton.click()
    assert requested == ['c']
    result = {'qIndex': 0, 'excIndex': 2, 'states': [2, 3], 'energy': 2.1222, 'axis': 'c', 'notes': [],
              'redQPoint': [0, 0, 0], 'pointGroup': 'S6', 'operations': 6, 'irreps': 'E_1u + E_2u',
              'irrepsError': None, 'spin': {'total': [-0.057, 0.057], 'electron': [0.072, -0.072],
                                            'hole': [-0.129, 0.129]}}
    panel.setCharacter(result)
    assert 'E_1u + E_2u' in panel.characterLabel.text() and 'S6' in panel.characterLabel.text()
    assert panel.spinTable.rowCount() == 2 and panel.spinTable.item(0, 1).text() == '-0.057'
    assert 'third lattice vector' in panel.characterNote.text()
    # Another exciton selected: offered to analyse, the result kept
    panel.setSelectedExciton((0, 4, 2.13))
    assert 'not analysed yet' in panel.characterLabel.text() and panel.spinTable.rowCount() == 0
    # In sessions: JSON-able
    import json
    assert json.loads(json.dumps(jsonableCharacter(result)))['irreps'] == 'E_1u + E_2u'


@pytest.mark.data
def test_summary_in_the_selected_exciton_section(qtbot, tmp_path):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    calc = window.calculations
    calc.selectedExciton = (11, 1, 2.08)
    calc.excitonSelected.emit(11, 1, 2.08)
    cost = window.compositionPanel.characterCostNote.text()
    assert '512 k-points' in cost and 'up to 6 symmetries' in cost
    calc._applyCharacter({'qIndex': 11, 'excIndex': 1, 'states': [1], 'energy': 2.08, 'axis': 'z', 'notes': [],
                          'redQPoint': [0, 0.125, -0.125], 'pointGroup': 'C1', 'operations': 1, 'irreps': 'A',
                          'irrepsError': None, 'spin': {'total': [0.0], 'electron': [0.0], 'hole': [0.0]}})
    summary = window.spectra.controls.characterSummary
    assert not summary.isHidden() and summary.text().startswith('Symmetry A (C1)')
    # Session round trip
    path = tmp_path / 'character.vxsession'
    window.writeSessionFile(str(path))
    calc.character = None
    window.openSession(str(path))
    assert calc.character['irreps'] == 'A' and window.compositionPanel.character['irreps'] == 'A'
