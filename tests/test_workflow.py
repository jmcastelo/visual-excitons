"""
End-to-end calculations on the BiI3 test dataset: dispersion, absorption,
exciton selection and wave function. Slow (about a minute): run with
pytest -m slow.
"""

import numpy as np
import pytest

from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.dataset import findDataset
from conftest import datasetPath

pytestmark = [pytest.mark.slow, pytest.mark.data]


@pytest.fixture(scope='module')
def bii3():
    """Calculations on BiI3 with the dispersion along LGZF computed (once for the module)."""
    dataset = findDataset(datasetPath('BiI3_Bulk_8x8x8'))
    options = Options()
    options.setSaveDir(dataset['save'])
    options.setDiagoDir(dataset['diago'])
    options.setQPDir(dataset['qp'])
    options.setIbrav(options.detectLatticeType())
    options.setLatticeData(options.ibrav)
    options.setBrillouinZone(path='LGZF', npoints=100)

    # Inline: each call returns with its result applied
    calculations = Calculations(options, synchronous=True)
    errors = []
    calculations.errorOccurred.connect(lambda title, message: errors.append(message))
    calculations.getExcitonDispersion()
    assert not errors
    return calculations


class Point:
    def __init__(self, data, x=0.0):
        self._data, self._x = data, x

    def data(self):
        return self._data

    def pos(self):
        import pyqtgraph as pg
        return pg.Point(self._x, 0.0)


def test_dispersion(bii3):
    assert len(bii3.dispPoints) == bii3.options.nExcitons
    energies = np.array([[p[1] for p in curve] for curve in bii3.dispPoints])
    assert np.all((energies > 1.5) & (energies < 3.0))
    # Curves are the excitons in increasing energy
    assert np.all(np.diff(energies, axis=0) >= -1e-9)


def test_absorption_selection_and_wave_function(bii3, monkeypatch):
    # Absorption at the first point of the path
    bii3.computeQPointAbsorptionSpectrum([Point(bii3.dispPointsData[0][0])], False)
    spectrum = bii3.excAbsData[0]
    assert spectrum['q'] == bii3.qIndices[0] and len(spectrum['brightExcEnergy']) > 0
    # Automatic range: around the BiI3 excitons (2.1-2.5 eV), not the default 4-20 eV
    low, high = spectrum['range']
    assert 1.4 <= low <= 1.7 and 2.8 <= high <= 3.1
    assert spectrum['energy'][0] == pytest.approx(low) and np.all(spectrum['brightExcEnergy'] > low)

    # Select its first bright exciton
    point = spectrum['data'][0]
    bii3.selectExciton([Point(point, spectrum['brightExcEnergy'][0])], True)
    qIndex, excIndex, energy = bii3.selectedExciton
    assert qIndex == spectrum['q'] and excIndex == int(spectrum['brightExcIndices'][0])

    # Its wave function is read from the file of its Q-point
    import visual_excitons.core.calculations as module
    original = module.YamboExcitonDB.from_db_file
    opened = []
    monkeypatch.setattr(module.YamboExcitonDB, 'from_db_file',
                        classmethod(lambda cls, *args, **kwargs: opened.append(kwargs['filename']) or original(*args, **kwargs)))

    errors = []
    bii3.errorOccurred.connect(lambda title, message: errors.append(message))
    bii3.computeExcitonWaveFunction(q_index=qIndex, exc_index=excIndex, fixed_particle='h',
                                    fixed_position=[0.3, 0.1, 0.0], cutoff_ry=5, supercell=[2, 1, 1])
    assert not errors
    assert opened == [f'ndb.BS_diago_Q{qIndex + 1}']

    # Even supercell sizes are raised to odd ones
    assert bii3.wfSupercell == [3, 1, 1]
    density = bii3.probabilityDensity()
    assert density.shape == tuple(n * s for n, s in zip(bii3.wfGrid, bii3.wfSupercell))
    assert density.max() == pytest.approx(1.0) and density.min() >= 0.0

    # The hole is snapped to the nearest point of the real-space grid
    grid = np.array(bii3.wfGrid)
    snapped = np.array(bii3.wfFixedPosition)
    np.testing.assert_allclose(snapped * grid, np.round(snapped * grid), atol=1e-6)
    np.testing.assert_allclose(snapped, np.round(np.array([0.3, 0.1, 0.0]) * grid) / grid, atol=1e-6)


def test_wave_function_in_the_background(qtbot, bii3):
    """Real threads: progress comes from yambopy's own loops, and cancelling stops them."""
    calculations = Calculations(bii3.options)
    calculations.lattice = bii3.lattice
    stages = []
    calculations.progressChanged.connect(lambda done, total, stage: stages.append((stage, done, total)))
    arguments = dict(q_index=0, exc_index=1, fixed_particle='h', fixed_position=[0, 0, 0], cutoff_ry=5, supercell=[1, 1, 1])

    with qtbot.waitSignal(calculations.wfComputed, timeout=120000):
        calculations.computeExcitonWaveFunction(**arguments)
    names = [stage for stage, done, total in stages]
    assert {'Loading the wave functions', 'Real-space wave function'} <= set(names)
    # The real-space loop reported its end
    assert any(stage == 'Real-space wave function' and done == total > 0 for stage, done, total in stages)

    # Again: the wave-function database is reused, not loaded again
    stages.clear()
    with qtbot.waitSignal(calculations.wfComputed, timeout=120000):
        calculations.computeExcitonWaveFunction(**dict(arguments, exc_index=2))
    names = {stage for stage, done, total in stages}
    assert 'Real-space wave function' in names and 'Loading the wave functions' not in names

    # Cancel in the middle of loading the wave functions (not cached this time)
    calculations.wavefunctionCache.clear()
    stages.clear()
    calculations.computeExcitonWaveFunction(**arguments)
    qtbot.waitUntil(lambda: any(stage == 'Loading the wave functions' and done > 0 for stage, done, total in stages),
                    timeout=60000)
    computed = []
    calculations.wfComputed.connect(lambda: computed.append(True))
    with qtbot.waitSignal(calculations.taskCancelled, timeout=10000):
        calculations.cancel()
    qtbot.waitUntil(lambda: not calculations.isBusy(), timeout=10000)
    assert not computed
    # It stopped before the real-space calculation
    assert 'Real-space wave function' not in [stage for stage, done, total in stages]
