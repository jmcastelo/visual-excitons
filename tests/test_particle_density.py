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


@pytest.mark.data
def test_placing_the_fixed_particle(window, qtbot, tmp_path):
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    controls, calc = window.wavefunction.controls, window.calculations
    assert controls.densityReadout.text() == 'Not computed yet.' and not controls.placeAtMaximumButton.isEnabled()
    assert controls.computeDensityButton.text() == 'Compute the hole density'
    controls.fullCutoffCheckBox.setChecked(False)
    controls.wfCutoffSpinBox.setValue(5.0)
    controls.excitonIndexSpinBox.setValue(1)
    controls.computeDensityButton.click()
    qtbot.waitUntil(lambda: calc.particleDensity is not None, timeout=120000)
    d = calc.particleDensity
    assert d['particle'] == 'h' and d['cutoff'] == 5.0 and d['density'].shape == (13, 13, 13)
    assert 'Hole density here' in controls.densityReadout.text() and 'from I' in controls.densityReadout.text()

    # At the maximum: a grid point of the density, 100 %
    controls.placeAtMaximumButton.click()
    expected = np.array(d['maxima'][0]) / 13
    assert np.allclose(window.wfParameters.position(), np.round(expected, 4))
    assert '<b>100 %</b>' in controls.densityReadout.text()

    # The electron: another density, not computed
    controls.particleTypeComboBox.setCurrentIndex(1)
    assert controls.computeDensityButton.text() == 'Compute the electron density'
    assert controls.densityReadout.text().startswith('Out of date') and not controls.placeAtMaximumButton.isEnabled()
    controls.particleTypeComboBox.setCurrentIndex(0)
    assert '<b>100 %</b>' in controls.densityReadout.text()

    # In sessions, with the results
    path = tmp_path / 'density.vxsession'
    window.writeSessionFile(str(path))
    window.openSession(str(path))
    assert calc.particleDensity is not None and calc.particleDensity['maxima'][0] == d['maxima'][0]
    assert '<b>100 %</b>' in controls.densityReadout.text()


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
