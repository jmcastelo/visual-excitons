"""The excitonic band structure at any Q, and the setting summing degenerate states."""

import contextlib
import io

import numpy as np
import pytest

from conftest import datasetPath
from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations, PointData


def quietly(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call(*args, **kwargs)


class Clicked:
    def __init__(self, q, j=1):
        self._data = PointData(-1, j, q=q)

    def data(self):
        return self._data


@pytest.fixture(scope='module')
def bii3():
    folder = datasetPath('BiI3_Bulk_8x8x8')
    options = Options()
    options.setSaveDir(str(folder / 'save'))
    options.setDiagoDir(str(folder / 'diagos'))
    options.setQPDir(str(folder / 'qp'), 'ndb.QP')
    options.identifyLattice()
    options.setBrillouinZone(path='LGZF', npoints=100)
    return options


def compute(options, q, indices):
    calc = Calculations(options, synchronous=True)
    errors = []
    calc.errorOccurred.connect(lambda title, message: errors.append(message))
    quietly(calc.getExcitonBandStructure, [Clicked(q, j) for j in indices], None)
    assert not errors, errors
    return calc


@pytest.mark.data
def test_at_gamma_the_energies_are_yambopys(bii3):
    """On DFT energies, as YamboExcitonDB.interpolate; on QP energies, its bands one higher (its band range bug)."""
    from yambopy import YamboExcitonDB, YamboElectronsDB, YamboQPDB
    bii3.setGW(False)
    calc = compute(bii3, 0, [1])
    db = YamboExcitonDB.from_db_file(calc.lattice, filename='ndb.BS_diago_Q1', folder=bii3.diagoDir, neigs=3)
    old = quietly(db.interpolate, energies=YamboElectronsDB.from_db_file(folder=bii3.saveDir), excitons=(1,),
                  bz=bii3.qBZ, lpratio=5, verbose=0)
    assert np.allclose(np.transpose(calc.bands), old.bands, atol=1e-6)
    assert calc.bandStructureInfo['states'] == [1] and calc.bandStructureInfo['bands'] == [139, 152]

    # QP energies: ndb.QP has bands 140-157, the BSE 139-152; YamboPy takes its first 14 columns as bands
    # 139-152, one band off, where band 139 is here estimated (outside the QP database)
    bii3.setGW(True)
    calc = compute(bii3, 0, [1])
    old = quietly(db.interpolate, energies=YamboQPDB.from_db(filename='ndb.QP', folder=bii3.qpDir), excitons=(1,),
                  bz=bii3.qBZ, lpratio=5, verbose=0)
    assert np.allclose(np.transpose(calc.bands)[:, 1:], old.bands[:, :-1], atol=1e-4)
    assert calc.bandStructureInfo['estimatedBands'] == [139]
    bii3.setGW(False)


@pytest.mark.data
def test_at_finite_q_the_hole_is_on_the_valence_bands_at_k(bii3):
    from visual_excitons.yambopy_ext.bse.exciton_kspace import state_weights, hole_kpoint_indices
    from visual_excitons.yambopy_ext.bse.exciton_bands import band_kpoint_weights
    from yambopy import YamboExcitonDB
    calc = compute(bii3, 11, [1])                                  # Q12 = (0, 1/8, -1/8)
    info = calc.bandStructureInfo
    assert info['qIndex'] == 11 and np.allclose(info['redQPoint'], [0, 0.125, -0.125])
    weights = np.transpose(calc.weights)                           # (path, bands)
    assert weights.min() >= 0
    # At the points of the path that are grid points: the exact weights, the hole's on the valence bands
    lattice = calc.lattice
    db = YamboExcitonDB.from_db_file(lattice, filename='ndb.BS_diago_Q12', folder=bii3.diagoDir, neigs=3)
    holes = hole_kpoint_indices(lattice.red_kpoints, info['redQPoint'])
    exact = band_kpoint_weights(db.table, state_weights(db.eigenvectors, info['states']), len(holes), 139, 152, holes)
    index = {tuple(np.round((k % 1) * 8).astype(int) % 8): i for i, k in enumerate(lattice.red_kpoints)}
    path = bii3.qBZ.kpoints('red')
    on = [(p, index[tuple(np.round((r % 1) * 8).astype(int) % 8)]) for p, r in enumerate(path)
          if np.allclose(r * 8, np.round(r * 8), atol=1e-6)]
    assert on and all(np.allclose(weights[p], exact[i]) for p, i in on)
    # Not the same as with the hole at the electron's k (what YamboPy does)
    gammaLike = band_kpoint_weights(db.table, state_weights(db.eigenvectors, info['states']), len(holes), 139, 152)
    assert not np.allclose(exact[:, :10], gammaLike[:, :10])


@pytest.mark.data
def test_degenerate_states_follow_the_setting(bii3):
    calc = compute(bii3, 0, [2])                                   # states 2-5 within 10 meV at Γ
    assert calc.bandStructureInfo['states'] == [2, 3, 4, 5]
    try:
        bii3.setSumDegenerate(False)
        quietly(calc.computeBandStructure)
        assert calc.bandStructureInfo['states'] == [2] and not calc.bandStructureInfo['degenerate']
        # The wave function's memory: the exciton alone
        calc.lattice = calc.lattice
        assert quietly(calc.estimateWaveFunction, 0, 2, 5, [1, 1, 1])['states'] == 1
        bii3.setSumDegenerate(True)
        assert quietly(calc.estimateWaveFunction, 0, 2, 5, [1, 1, 1])['states'] == 4
    finally:
        bii3.setSumDegenerate(True)


@pytest.mark.data
def test_band_structure_in_sessions(bii3):
    from visual_excitons.core.session import jsonable
    calc = compute(bii3, 11, [1])
    meta, arrays = calc.resultsSnapshot(includeWaveFunction=False)
    assert meta['bands']['qIndex'] == 11
    restored = Calculations(bii3, synchronous=True)
    restored.restoreResults(jsonable(meta), arrays)
    assert restored.bandStructureInfo['qIndex'] == 11 and np.allclose(restored.bands, calc.bands)


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
def test_title_and_wave_function_note(window, qtbot):
    import visual_excitons.gui.main_window as main_window
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    window.system.qPathLineEdit.setText('LGZF')
    assert window.system.setBrillouinZone()
    calc, widget = window.calculations, window.spectra.bandStructurePlot
    calc.getExcitonBandStructure([Clicked(11)], None)
    qtbot.waitUntil(lambda: calc.bandStructureInfo is not None, timeout=60000)
    note = window.spectra.bandStructureNote
    assert widget.title.endswith('at Q12 = (0, 1/8, -1/8)') and 'k−Q' in note.text() and not note.isHidden()
    calc.getExcitonBandStructure([Clicked(0)], None)
    qtbot.waitUntil(lambda: calc.bandStructureInfo['qIndex'] == 0, timeout=60000)
    assert widget.title.endswith('at Q1 = Γ') and 'k−Q' not in note.text()

    # A wave function computed with the degenerate states: said, and warned once the setting changes
    p3 = window.wavefunction.controls
    calc.waveFunction, calc.wfExciton, calc.wfStates, calc.wfDegenerate = np.zeros((2, 2, 2)), (0, 2), [2, 3], True
    p3.updateWfStatesNote()                    # as on wfComputed (the rest of a wave function is not needed here)
    assert 'with the degenerate states 2–3' in p3.wfStatesNote.text() and 'again' not in p3.wfStatesNote.text()
    window.spectra.controls.sumDegenerateCheckBox.setChecked(False)
    assert not p3.sumDegenerateCheckBox.isChecked() and 'compute it again' in p3.wfStatesNote.text()


@pytest.mark.data
def test_energies_where_skw_fails_are_smooth_and_exact():
    """WSe2 72x72x1: the SKW fit misses its own data by over 1 eV (oscillating); the spline on the grid is used."""
    from yambopy import YamboElectronsDB
    folder = datasetPath('WSe2_72x72x1')
    options = Options()
    options.setSaveDir(str(folder / 'save'))
    options.setDiagoDir(str(folder / 'diagos_sel'))
    options.setGW(False)
    options.identifyLattice()
    options.setBrillouinZone(path='MGKM', npoints=300)
    calc = compute(options, 0, [1])
    assert calc.bandStructureInfo['energyInterpolation'] == 'spline'
    energies = np.transpose(calc.bands)                                # (path, bands)
    assert np.abs(np.diff(energies, 2, axis=0)).max() < 0.1            # no oscillations (they were ~1 eV)
    # At the path points on the grid: the DFT energies
    lattice = calc.lattice
    first, last = calc.bandStructureInfo['bands']
    dft = quietly(YamboElectronsDB.from_db_file, folder=options.saveDir).eigenvalues_ibz[0][:, first - 1:last]
    full = dft[np.asarray(lattice.kpoints_indexes)]
    index = {tuple(np.round((k[:2] % 1) * 72).astype(int) % 72): i for i, k in enumerate(lattice.red_kpoints)}
    path = options.qBZ.kpoints('red')
    on = [(p, index[tuple(np.round((r[:2] % 1) * 72).astype(int) % 72)]) for p, r in enumerate(path)
          if np.allclose(r[:2] * 72, np.round(r[:2] * 72), atol=1e-6)]
    assert on and all(np.allclose(energies[p], full[i], atol=1e-6) for p, i in on)


@pytest.mark.data
def test_skw_is_kept_where_it_fits(bii3):
    bii3.setGW(False)
    calc = compute(bii3, 0, [1])
    assert calc.bandStructureInfo['energyInterpolation'] == 'SKW'


def test_path_axes_have_no_scale_factor(qtbot):
    """The path axes are labelled by their special points: no '(x0.001)' after their title, also after a new path."""
    from visual_excitons.core.style import BandStructureStyle, DispersionStyle
    from visual_excitons.gui.band_structure_plot import BandStructurePlot
    from visual_excitons.gui.dispersion_plot import DispersionPlot
    for widget in (BandStructurePlot(BandStructureStyle()), DispersionPlot(DispersionStyle())):
        qtbot.addWidget(widget)
        widget.setXAxis([0.0, 0.004, 0.009], ['G', 'K', 'M'])
        axis = widget.getAxis('bottom')
        assert not axis.autoSIPrefix and '0.001' not in axis.labelString()
