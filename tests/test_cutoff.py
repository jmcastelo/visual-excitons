"""The wave-function cutoff in Ry and in RL (Yambo's count of reciprocal lattice vectors)."""

import pytest

from conftest import datasetPath


def shells(name):
    from yambopy import YamboLatticeDB
    from visual_excitons.core.memory import GVectorShells
    folder = datasetPath(name) / 'save'
    return GVectorShells(str(folder), YamboLatticeDB.from_db(str(folder / 'ns.db1'), Expand=False))


@pytest.mark.data
@pytest.mark.parametrize('name, expected', [('BiI3_Bulk_8x8x8', {5: 429, 10: 1213, 20: 3397}),
                                            ('WSe2_72x72x1', {5: 271, 10: 819, 20: 2289})])
def test_ry_and_rl(name, expected):
    s = shells(name)
    for ry, rl in expected.items():
        assert s.rl(ry) == rl
        # Back to Ry: the same G-vectors, just above the energy of the last shell
        cutoff = s.cutoffRy(rl)
        assert s.rl(cutoff) == rl and cutoff <= ry
    assert s.rl(1e6) == s.count


@pytest.mark.data
def test_counts_are_rounded_to_complete_shells():
    s = shells('WSe2_72x72x1')
    assert s.shell(820)[0] == 843 and s.shell(842, down=True)[0] == 819
    assert s.shell(819)[0] == s.shell(819, down=True)[0] == 819
    complete, energy = s.shell(843)
    assert s.rl(energy) < 843 <= s.rl(energy + 1e-3)               # the whole shell, nothing beyond


@pytest.mark.data
def test_linked_fields(qtbot):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    window = main_window.MainWindow()
    qtbot.addWidget(window)
    p3 = window.wavefunction.parameters3DWidget
    assert not p3.wfCutoffRlSpinBox.isEnabled()                      # no dataset: no RL
    window.openDataset(main_window.findDataset(datasetPath('WSe2_72x72x1')))
    assert p3.wfCutoffRlSpinBox.isEnabled()
    p3.wfCutoffSpinBox.setValue(10.0)
    assert p3.wfCutoffRlSpinBox.value() == 819
    p3.wfCutoffRlSpinBox.setValue(820)                               # up: the next shell
    assert p3.wfCutoffRlSpinBox.value() == 843 and window.options.wfCutoff() == pytest.approx(10.086, abs=2e-3)
    p3.wfCutoffRlSpinBox.stepBy(-1)                                  # down: the previous shell
    assert p3.wfCutoffRlSpinBox.value() == 819 and window.options.wfCutoff() < 10.0
    p3.fullCutoffCheckBox.setChecked(True)
    assert not p3.wfCutoffRlSpinBox.isEnabled()
