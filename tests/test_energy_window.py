"""
The states summed with the selected exciton: those degenerate with it, or an
energy window around it weighted by oscillator strength (an absorption peak
made of many close states).
"""

import contextlib
import io
from types import SimpleNamespace

import numpy as np
import pytest

from conftest import datasetPath
from visual_excitons.core.calculations import (Calculations, stateSum, sameStateSum, describeStateSum, stateNames,
                                               weightedAkcv)
from visual_excitons.yambopy_ext.bse.exciton_kspace import summed_states, state_weights


def fakeDB(energies, intensities, ntransitions=4, seed=0):
    """A YamboExcitonDB-like object: energies (eV), intensities |l r| per state, random eigenvectors."""
    rng = np.random.default_rng(seed)
    vectors = rng.normal(size=(len(energies), ntransitions)) + 1j * rng.normal(size=(len(energies), ntransitions))
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    energies = np.asarray(energies, dtype=float)

    def get_degenerate(index, eps=1e-4, rtol=1e-3):
        return [int(i) + 1 for i in np.nonzero(np.abs(energies - energies[index - 1]) <= eps)[0]]
    return SimpleNamespace(eigenvalues=energies, eigenvectors=vectors, l_residual=np.sqrt(intensities),
                           r_residual=np.sqrt(intensities), get_degenerate=get_degenerate)


ENERGIES = [1.60, 1.70, 1.70, 2.30, 2.34, 2.35, 2.36, 2.40, 2.50]
INTENSITIES = [0.0, 1.0, 1.0, 0.0, 2.0, 6.0, 0.0, 2.0, 5.0]


def test_degenerate_and_alone():
    db = fakeDB(ENERGIES, INTENSITIES)
    assert summed_states(db, 2)[0] == [2, 3]
    states, shares, used = summed_states(db, 2, degenerate=False)
    assert states == [2] and np.allclose(shares, [1.0]) and used == 'equal'


def test_window_by_oscillator_strength():
    db = fakeDB(ENERGIES, INTENSITIES)
    states, shares, used = summed_states(db, 6, window=0.05, weighting='oscillator')
    assert states == [4, 5, 6, 7, 8] and used == 'oscillator'
    assert np.allclose(shares, np.array([0, 2, 6, 0, 2]) / 10)
    # Equally
    states, shares, used = summed_states(db, 6, window=0.05, weighting='equal')
    assert np.allclose(shares, 0.2) and used == 'equal'
    # The window's edge counts: 2.35 ± 0.01 takes 2.34 and 2.36
    assert summed_states(db, 6, window=0.01)[0] == [5, 6, 7]


def test_a_degenerate_group_shares_its_intensity():
    """
    The bright doublet's two states have different intensities for one field
    direction (an arbitrary mixture of K and K'): they share the group's total.
    """
    db = fakeDB(ENERGIES, [0.0, 1.0, 0.2, 0.0, 2.0, 6.0, 0.0, 2.0, 5.0])
    states, shares, used = summed_states(db, 2, window=0.2, weighting='oscillator')
    assert states == [1, 2, 3] and used == 'oscillator' and np.allclose(shares, [0.0, 0.5, 0.5])


def test_a_window_with_no_bright_state_is_weighted_equally():
    """At finite Q the residuals vanish: oscillator weighting falls back to equal, and says so."""
    db = fakeDB(ENERGIES, INTENSITIES)
    states, shares, used = summed_states(db, 1, window=0.05, weighting='oscillator')
    assert states == [1] and used == 'equal'
    dark = fakeDB(ENERGIES, np.zeros(len(ENERGIES)))
    states, shares, used = summed_states(dark, 6, window=0.05, weighting='oscillator')
    assert used == 'equal' and np.allclose(shares, 0.2)


def test_state_weights_with_shares():
    db = fakeDB(ENERGIES, INTENSITIES)
    weights = state_weights(db.eigenvectors, [5, 6], [0.25, 0.75])
    expected = 0.25 * np.abs(db.eigenvectors[4]) ** 2 + 0.75 * np.abs(db.eigenvectors[5]) ** 2
    assert np.allclose(weights, expected) and weights.sum() == pytest.approx(1.0)
    # Equal shares by default, as before
    assert np.allclose(state_weights(db.eigenvectors, [2, 3]),
                       (np.abs(db.eigenvectors[1]) ** 2 + np.abs(db.eigenvectors[2]) ** 2) / 2)
    with pytest.raises(ValueError):
        state_weights(db.eigenvectors, [2, 3], [1.0])


def test_densities_add_up_with_the_shares():
    """Each state's coefficients times the square root of its share: |A|^2 summed is the shares' sum."""
    db = fakeDB(ENERGIES, INTENSITIES)
    db.get_Akcv = lambda: db.eigenvectors.reshape(len(ENERGIES), 1, 1, 2, 2, 1)
    Akcv, states, shares, used = weightedAkcv(db, 6, True, 0.05, 'oscillator')
    perState = np.sum(np.abs(Akcv) ** 2, axis=tuple(range(1, Akcv.ndim)))
    assert np.allclose(perState, shares) and np.sum(np.abs(Akcv) ** 2) == pytest.approx(1.0)


def test_state_sum_settings(qtbot):
    calc = Calculations(synchronous=True)
    assert calc.stateSum() == {'degenerate': True, 'window': 0.0, 'weighting': 'equal'}
    with qtbot.waitSignal(calc.stateSumChanged):
        calc.setEnergyWindow(0.025)
    assert calc.stateSum() == {'degenerate': True, 'window': 0.025, 'weighting': 'oscillator'}
    with qtbot.waitSignal(calc.stateSumChanged):
        calc.setWindowWeighting('equal')
    with qtbot.waitSignal(calc.stateSumChanged):
        calc.setSumDegenerate(False)
    with qtbot.assertNotEmitted(calc.stateSumChanged):
        calc.setEnergyWindow(0.025)
    calc.setEnergyWindow(0.0)
    # Without a window, the weighting does not matter
    with qtbot.assertNotEmitted(calc.stateSumChanged):
        calc.setWindowWeighting('oscillator')
    with pytest.raises(ValueError):
        calc.setWindowWeighting('brightest')


def test_results_match_the_states_asked():
    # Results from before the window say only whether degenerate states were summed
    assert sameStateSum({'degenerate': True}, stateSum(True))
    assert not sameStateSum({'degenerate': True}, stateSum(True, 0.025))
    assert sameStateSum({'degenerate': True, 'window': 0.025, 'weighting': 'oscillator'},
                        stateSum(True, 0.025, 'oscillator'))
    assert not sameStateSum({'degenerate': True, 'window': 0.025, 'weighting': 'equal'},
                            stateSum(True, 0.025, 'oscillator'))


def test_notes():
    assert stateNames([3, 4]) == '3–4' and stateNames([3, 5]) == '3, 5'
    assert describeStateSum({'states': [2], 'degenerate': True}, [2]) == ''
    assert describeStateSum({'states': [2, 3], 'degenerate': True}, [2]) == ', with the degenerate states 2–3'
    note = describeStateSum({'states': [4, 5, 6, 7, 8], 'window': 0.05, 'weighting': 'oscillator',
                             'weightingUsed': 'oscillator'}, [6])
    assert note == ', with the 5 states within ±50 meV (4–8), weighted by oscillator strength'
    note = describeStateSum({'states': [1, 2], 'window': 0.05, 'weighting': 'oscillator', 'weightingUsed': 'equal'}, [1])
    assert 'weighted equally (none is bright)' in note


@pytest.mark.data
def test_window_on_a_dataset():
    """BiI3 at Γ: a window sums the states it holds, the k-space weights still add up to 1."""
    from yambopy import YamboLatticeDB, YamboExcitonDB
    from visual_excitons.yambopy_ext.bse.exciton_kspace import exciton_kspace
    folder = datasetPath('BiI3_Bulk_8x8x8')
    with contextlib.redirect_stdout(io.StringIO()):
        lattice = YamboLatticeDB.from_db(str(folder / 'save' / 'ns.db1'))
        db = YamboExcitonDB.from_db_file(lattice, filename='ndb.BS_diago_Q1', folder=str(folder / 'diagos'), neigs=40)
    energies = np.real(db.eigenvalues)
    result = exciton_kspace(db, 10, window=0.05, weighting='oscillator')
    inside = [i + 1 for i in range(len(energies)) if abs(energies[i] - energies[9]) <= 0.05 + 1e-9]
    assert result['states'] == inside and sum(result['shares']) == pytest.approx(1.0)
    assert result['electron'].sum() == pytest.approx(1.0) and result['hole'].sum() == pytest.approx(1.0)


@pytest.fixture
def window(qtbot):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()          # the test's own settings (see conftest)
    w = main_window.MainWindow()
    qtbot.addWidget(w)
    yield w
    from visual_excitons.gui.theme import themeManager
    themeManager().setMode('System')


def test_window_controls(window):
    """The Selected exciton section sets the window; the absorption plot shades it around the exciton."""
    controls, calc, plot = window.spectra.controls, window.calculations, window.spectra.absorptionPlot
    assert calc.energyWindow == 0.0 and not controls.windowSpinBox.isEnabled()
    controls.windowSpinBox.setValue(50)
    controls.windowCheckBox.setChecked(True)
    assert calc.energyWindow == pytest.approx(0.05) and controls.weightingComboBox.isEnabled()
    controls.weightingComboBox.setCurrentIndex(1)
    assert calc.stateSum()['weighting'] == 'equal'
    plot.setWindow(2.35, calc.energyWindow)
    assert plot.windowRegion.isVisible() and np.allclose(plot.windowRegion.getRegion(), (2.30, 2.40))
    plot.clearData()
    plot.setWindow(None)
    assert not plot.windowRegion.isVisible()
    controls.windowCheckBox.setChecked(False)
    assert calc.energyWindow == 0.0


@pytest.mark.data
def test_bright_excitons_are_the_states_themselves():
    """
    WSe2 at Γ: the bright doublet A (states 3 and 4, 1.687 eV) is listed as
    states 3 and 4 at that energy, with their own intensities (YamboPy's
    get_excitons gave indices 2 and 3, and 1.83 eV for the second).
    """
    from yambopy import YamboLatticeDB, YamboExcitonDB
    from visual_excitons.core.calculations import computeAbsorption
    folder = datasetPath('WSe2_72x72x1')
    with contextlib.redirect_stdout(io.StringIO()):
        lattice = YamboLatticeDB.from_db(str(folder / 'save' / 'ns.db1'))
        spectrum = computeAbsorption(lattice, str(folder / 'diagos_sel'), 0, 0, 0.01, 1.0, 3.0, 0.1, autoRange=True)
        db = YamboExcitonDB.from_db_file(lattice, filename='ndb.BS_diago_Q1', folder=str(folder / 'diagos_sel'),
                                         Load_WF=False)
    energies = np.real(db.eigenvalues)
    assert list(spectrum['brightExcIndices']) == [3, 4]
    assert np.allclose(spectrum['brightExcEnergy'], energies[[2, 3]])
    assert [p.j for p in spectrum['data']] == [3, 4]
    assert len(spectrum['darkExcEnergy']) == len(energies) - 2
