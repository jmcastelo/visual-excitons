"""The own density of the hole or of the electron, and placing the fixed particle with it."""

import contextlib
import io

import numpy as np
import pytest

from conftest import datasetPath


def quietly(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call(*args, **kwargs)


@pytest.mark.data
def test_density_is_the_weight_of_the_wave_function_computed():
    """
    The identity behind the feature, with yambopy's ex_wf2Real itself: the total
    weight of the wave function computed with a particle fixed at r0, over one
    period (the k-grid: ex_wf2Real makes it odd, 9 x 9 x 9), is the particle's
    density at r0. And a grid point of the density is used as it is.
    """
    from yambopy import YamboLatticeDB, YamboExcitonDB, YamboWFDB
    from yambopy.bse.realSpace_excitonwf import ex_wf2Real
    from visual_excitons.yambopy_ext.bse.exciton_particle_density import exciton_particle_density, density_maxima
    folder = datasetPath('BiI3_Bulk_8x8x8')
    lattice = quietly(YamboLatticeDB.from_db, str(folder / 'save' / 'ns.db1'))
    exc = quietly(YamboExcitonDB.from_db_file, lattice, filename='ndb.BS_diago_Q1', folder=str(folder / 'diagos'),
                  neigs=3)
    bands = [int(np.min(exc.table[:, 1])), int(np.max(exc.table[:, 2]))]
    wfdb = quietly(YamboWFDB, path=str(folder / 'save'), save='.', latdb=lattice, bands_range=[bands[0] - 1, bands[1]])
    Akcv, Qpt = exc.get_Akcv()[[0]], wfdb.ydb.lat @ exc.car_qpoint
    for particle in ('h', 'e'):
        rho, info = exciton_particle_density(Akcv, Qpt, wfdb, bands, particle, 5.0, fraction=1.0)
        box = info['fft_box']
        top = tuple(density_maxima(rho)[0][0])
        middle = np.unravel_index(np.argmin(np.abs(rho - 0.2 * rho.max())), rho.shape)
        weights = []
        for index in (top, middle):
            r0 = np.array(index) / box
            _, _, positions, wf = quietly(ex_wf2Real, Akcv, Qpt, wfdb, bands, fixed_position=list(r0),
                                          fix_particle=particle, supercell=[8, 8, 8], wfcCutoffRy=5.0, block_size=64)
            assert np.allclose((positions[-1] @ np.linalg.inv(lattice.lat) - 4) % 1.0, r0)     # not moved
            density = np.sum(np.abs(wf) ** 2, axis=(0, 1, 2, 3))
            weights.append(density[:8 * box[0], :8 * box[1], :8 * box[2]].sum())               # one period
        assert weights[1] / weights[0] == pytest.approx(rho[middle] / rho[top], rel=2e-3)
        if particle == 'h':
            # Iodine 5p: the largest hole density beside an iodine atom, not on it
            from visual_excitons.core.placement import nearestAtom, gridPosition
            i, distance = nearestAtom(gridPosition(top, box), lattice.lat, lattice.car_atomic_positions)
            assert lattice.atomic_numbers[i] == 53 and 0.5 < distance < 1.2


@pytest.fixture
def window(qtbot):
    from PySide6.QtCore import QSettings
    import visual_excitons.gui.main_window as main_window
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    w = main_window.MainWindow()
    qtbot.addWidget(w)
    yield w
    from visual_excitons.gui.theme import themeManager
    themeManager().setMode('System')


def gridPoint(position, shape):
    return tuple(int(i) for i in np.rint(np.asarray(position) * np.asarray(shape)).astype(int) % np.asarray(shape))


@pytest.mark.data
def test_placing_the_fixed_particle(window, qtbot, tmp_path):
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    controls, calc = window.wavefunction.controls, window.calculations
    assert controls.densityReadout.text() == 'Not computed yet.'
    assert controls.maximaTable.isHidden() and controls.placeHereButton.isHidden()
    assert controls.computeDensityButton.text() == 'Compute the hole density'
    controls.fullCutoffCheckBox.setChecked(False)
    controls.wfCutoffSpinBox.setValue(5.0)
    controls.excitonIndexSpinBox.setValue(1)
    controls.computeDensityButton.click()
    qtbot.waitUntil(lambda: calc.particleDensity is not None, timeout=120000)
    d = calc.particleDensity
    assert d['particle'] == 'h' and d['cutoff'] == 5.0 and d['density'].shape == (13, 13, 13)
    assert 'Hole density here' in controls.densityReadout.text()

    # The distinct maxima: the largest first, near the iodine atoms, equivalent ones once
    groups, table = controls.maximaGroups, controls.maximaTable
    assert not table.isHidden() and table.rowCount() == len(groups) >= 2
    assert table.item(0, 1).text() == '100 %' and table.item(0, 2).text() == 'I'
    assert sum(len(g['members']) for g in groups) <= len(d['maxima'])
    # Selecting one marks its copies in the view; placing puts the particle at one of them
    with qtbot.waitSignal(controls.maximaMarkersChanged) as marked:
        table.selectRow(1)
    assert len(marked.args[0]) == len(groups[1]['members'])
    assert window.wavefunction.markedMaxima == marked.args[0] and controls.placeHereButton.isEnabled()
    # Marks off and on again
    controls.showMaximaCheckBox.setChecked(False)
    assert window.wavefunction.markedMaxima == []
    controls.showMaximaCheckBox.setChecked(True)
    assert len(window.wavefunction.markedMaxima) == len(groups[1]['members'])
    controls.placeHereButton.click()
    assert gridPoint(window.wfParameters.position(), (13, 13, 13)) in groups[1]['members']
    assert table.item(1, 0).text() == '●' and table.item(0, 0).text() == ''
    share = round(100 * groups[1]['share'])
    assert f'<b>{share} %</b>' in controls.densityReadout.text()
    controls.placeAtMaximum()
    assert '<b>100 %</b>' in controls.densityReadout.text() and table.item(0, 0).text() == '●'

    # The electron: another density, not computed
    controls.particleTypeComboBox.setCurrentIndex(1)
    assert controls.computeDensityButton.text() == 'Compute the electron density'
    assert controls.densityReadout.text().startswith('Out of date') and controls.maximaTable.isHidden()
    controls.particleTypeComboBox.setCurrentIndex(0)
    assert '<b>100 %</b>' in controls.densityReadout.text()

    # In sessions, with the results
    path = tmp_path / 'density.vxsession'
    window.writeSessionFile(str(path))
    window.openSession(str(path))
    assert calc.particleDensity is not None and calc.particleDensity['maxima'][0] == d['maxima'][0]
    assert '<b>100 %</b>' in controls.densityReadout.text()


@pytest.mark.data
def test_wave_function_at_the_density_maximum(window, qtbot):
    """
    With 'Fix the particle at its density maximum' (on by default), a new exciton
    is computed with the particle at its maximum; a position chosen afterwards,
    while that density is current, is kept; unticked, the position is used as it is.
    """
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    controls, calc = window.wavefunction.controls, window.calculations
    assert controls.atMaximumCheckBox.isChecked()
    controls.fullCutoffCheckBox.setChecked(False)
    controls.wfCutoffSpinBox.setValue(5.0)
    controls.setSupercell([1, 1, 1])
    controls.excitonIndexSpinBox.setValue(1)
    window.wfParameters.setPosition([0.0, 0.0, 0.0])
    assert controls.computeWf()
    qtbot.waitUntil(lambda: calc.waveFunction is not None, timeout=180000)
    d = calc.particleDensity
    assert d is not None and (d['excIndex'], d['cutoff']) == (1, 5.0)
    groups = controls.maximaGroups
    assert gridPoint(calc.wfFixedPosition, (13, 13, 13)) in groups[0]['members']        # at the largest maximum

    # Another site, chosen while the density is current: kept
    controls.maximaTable.selectRow(1)
    controls.placeAtSelected()
    chosen = window.wfParameters.position()
    calc.waveFunction = None
    assert controls.computeWf()
    qtbot.waitUntil(lambda: calc.waveFunction is not None, timeout=180000)
    assert calc.particleDensity is d and np.allclose(calc.wfFixedPosition, chosen, atol=1e-4)

    # Unticked: a new exciton at the position as it is
    controls.atMaximumCheckBox.setChecked(False)
    controls.excitonIndexSpinBox.setValue(2)
    window.wfParameters.setPosition([0.5, 0.5, 0.5])
    calc.waveFunction = None
    assert controls.computeWf()
    qtbot.waitUntil(lambda: calc.waveFunction is not None, timeout=180000)
    assert calc.particleDensity is d and gridPoint(calc.wfFixedPosition, (13, 13, 13)) == gridPoint([0.5] * 3, (13,) * 3)


@pytest.mark.data
def test_caption_says_what_the_view_shows(window, qtbot):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    assert window.wavefunction.view.captionLabel.text() == ''
    injectResults(window)                 # the electron fixed at (0.5, 0, 0), exciton 2 at Q5
    caption = window.wavefunction.view.captionLabel
    assert caption.text() == 'Hole density of exciton 2 at Q5<br>electron fixed at (0.5000, 0.0000, 0.0000)'
    window.wavefunction.controls.showCaptionChanged.emit(False)
    assert caption.isHidden()
