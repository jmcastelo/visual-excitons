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

    # A density computed with its own button: the particle goes to its maximum too
    controls.excitonIndexSpinBox.setValue(3)
    window.wfParameters.setPosition([0.0, 0.0, 0.0])
    controls.computeDensityButton.click()
    qtbot.waitUntil(lambda: calc.particleDensity is not d, timeout=180000)
    assert gridPoint(window.wfParameters.position(), (13, 13, 13)) in controls.maximaGroups[0]['members']
    controls.excitonIndexSpinBox.setValue(1)
    calc.particleDensity = d
    controls.updateDensityReadout()

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


# Drawing the particle density (its own layer and settings)

def fakeParticleDensity(calc, shape=(12, 12, 12), particle='h'):
    """A particle density as computeParticleDensity gives it: a peak in the cell."""
    grid = np.indices(shape).transpose(1, 2, 3, 0) / np.asarray(shape)
    density = np.exp(-np.sum((grid - 0.4) ** 2, axis=-1) / 0.01).astype(np.float32)
    calc._applyParticleDensity({'lattice': calc.lattice, 'density': density, 'particle': particle, 'qIndex': 0,
                                'excIndex': 1, 'states': [1], 'degenerate': True, 'cutoff': 10.0,
                                'maxima': [[5, 5, 5]], 'weightKept': 0.999})


@pytest.mark.data
def test_display_tabs_hold_each_density_settings(window):
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    c, display = window.wavefunction.controls, window.wfParameters.display
    assert c.displayLayer() == 'wf' and c.colormapComboBox.currentText() == 'Viridis'
    assert c.displayTabBar.tabText(1) == 'Hole density'
    c.isoLevelSlider.slider.setValue(700)
    assert display['wf'].isoLevel == pytest.approx(0.7) and window.wfParameters.isoLevel == pytest.approx(0.7)

    # The particle density's tab: its own values; editing them leaves the wave function's
    c.displayTabBar.setCurrentIndex(1)
    assert c.displayLayer() == 'particle' and c.colormapComboBox.currentText() == 'Blues'
    assert c.isoLevelSlider.slider.value() == 500 and not c.showDensityCheckBox.isEnabled()   # not computed yet
    c.plotTypeComboBox.setCurrentText('Isosurface set')
    c.colormapComboBox.setCurrentText('Sunset')
    assert display['particle'].plotType == 1 and display['particle'].colormap == 'Sunset'
    assert display['wf'].plotType == 0 and display['wf'].colormap == 'Viridis'
    c.displayTabBar.setCurrentIndex(0)
    assert c.plotTypeComboBox.currentText() == 'Isosurface' and c.isoLevelSlider.slider.value() == 700

    # Kept between sessions: the wave function's under its former keys, the particle density's as well
    values = window.state.values(main_window.GLOBAL)
    assert values['wavefunction/isoLevel'] == 700 and values['wavefunction/colormap'] == 'Viridis'
    assert values['wavefunction/particleDisplay/colormap'] == 'Sunset'
    assert values['wavefunction/particleDisplay/plotType'] == 'Isosurface set'
    window.state.restore(main_window.GLOBAL, {'wavefunction/particleDisplay/colormap': 'Fire',
                                             'wavefunction/colormap': 'Magma'})
    assert display['particle'].colormap == 'Fire' and c.colormapComboBox.currentText() == 'Magma'

    # The tab follows the particle
    c.particleTypeComboBox.setCurrentIndex(1)
    assert c.displayTabBar.tabText(1) == 'Electron density'
    c.particleTypeComboBox.setCurrentIndex(0)


@pytest.mark.data
def test_particle_density_is_drawn_over_the_supercell(window):
    import visual_excitons.gui.main_window as main_window
    from test_session import injectResults
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    panels, c, calc = window.wavefunction, window.wavefunction.controls, window.calculations
    layers = panels.view.layers
    c.setSupercell([3, 1, 1])
    fakeParticleDensity(calc)
    # Drawn in its own layer, repeated over the supercell drawn
    density, transform = panels.particleDisplay.source()
    assert density.shape == (36, 12, 12) and density.max() == pytest.approx(1.0)
    assert np.allclose(transform[:3, 0] * 36, np.asarray(window.dataset.cell)[0] * 3)
    assert layers['particle'].mesh is not None and layers['particle'].mesh.visible()
    assert 'Hole density of exciton 1 at Q1' in panels.view.captionLabel.text()

    # Its own plot type and settings; switched off and on
    c.displayTabBar.setCurrentIndex(1)
    assert c.showDensityCheckBox.isEnabled()
    c.plotTypeComboBox.setCurrentText('Isosurface set')
    assert layers['particle'].meshSet is not None and not layers['particle'].mesh
    c.showDensityCheckBox.setChecked(False)
    assert not layers['particle'].meshSet.visible() and panels.view.captionLabel.text() == ''
    c.showDensityCheckBox.setChecked(True)
    assert layers['particle'].meshSet.visible()

    # With the wave function too: both drawn, each switched on and off by itself
    injectResults(window)
    assert layers['wf'].mesh is not None and layers['particle'].meshSet.visible()
    assert panels.view.captionLabel.text().count('density of') == 2
    c.displayTabBar.setCurrentIndex(0)
    c.showDensityCheckBox.setChecked(False)
    assert not layers['wf'].mesh.visible() and layers['particle'].meshSet.visible()
    assert panels.view.captionLabel.text().startswith('Hole density')
    c.showDensityCheckBox.setChecked(True)

    # A new supercell and cell origin: drawn again over them
    c.setSupercell([1, 1, 1])
    assert panels.particleDisplay.source()[0].shape == (12, 12, 12)
    # Another dataset: gone
    window.openDataset(main_window.findDataset(datasetPath('BN')))
    assert layers['particle'].meshSet is None and layers['particle'].mesh is None
