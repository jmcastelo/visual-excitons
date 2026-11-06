"""Options, datasets and the calculation bookkeeping (no Yambo databases needed)."""

import numpy as np
import pyqtgraph as pg
import pytest

from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations, PointData
from visual_excitons.core.dataset import findDataset, datasetName, datasetExists
from visual_excitons.core.style import AbsorptionStyle


# Datasets

def makeDataset(root, name, gw=True):
    for directory, filename in [('save', 'ns.db1'), ('diagos', 'ndb.BS_diago_Q1'), ('qp', 'ndb.QP')][:3 if gw else 2]:
        (root / name / directory).mkdir(parents=True)
        (root / name / directory / filename).touch()
    return root / name


def test_find_dataset(tmp_path):
    folder = makeDataset(tmp_path, 'BiI3')
    dataset = findDataset(folder)
    assert dataset == {'save': str(folder / 'save'), 'diago': str(folder / 'diagos'), 'qp': str(folder / 'qp'), 'gw': True}
    assert datasetName(dataset) == 'BiI3' and datasetExists(dataset)


def test_find_dataset_does_not_mix_systems(tmp_path):
    """Opening a folder with several systems takes the BSE and GW directories next to the SAVE one."""
    makeDataset(tmp_path, 'A_noGW', gw=False)
    makeDataset(tmp_path, 'B_GW', gw=True)
    dataset = findDataset(tmp_path)
    assert dataset['save'].endswith('A_noGW/save') and dataset['diago'].endswith('A_noGW/diagos')
    assert dataset['qp'] is None and dataset['gw'] is False


def test_find_dataset_without_save(tmp_path):
    (tmp_path / 'empty').mkdir()
    dataset = findDataset(tmp_path / 'empty')
    assert dataset['save'] is None and not datasetExists(dataset) and datasetName(dataset) == ''


# Options

@pytest.fixture
def options():
    o = Options()
    o.cell = np.array([[2.0, 0, 0], [1.0, 3.0, 0], [0, 0, 4.0]])
    return o


def test_view_vectors(options):
    np.testing.assert_allclose(options.viewVectorToCartesian([1, 2, 3], 'Cartesian'), [1, 2, 3])
    np.testing.assert_allclose(options.viewVectorToCartesian([1, 1, 0], 'Lattice [uvw]'), [3.0, 3.0, 0])
    # (hkl) normals are perpendicular to the lattice vectors of the plane
    normal = options.viewVectorToCartesian([0, 0, 1], 'Reciprocal (hkl)')
    assert abs(normal @ options.cell[0]) < 1e-12 and abs(normal @ options.cell[1]) < 1e-12
    with pytest.raises(ValueError):
        Options().viewVectorToCartesian([1, 0, 0], 'Lattice [uvw]')


def test_fixed_particle_sits_in_the_central_cell(options):
    options.setParticlePosition([0.5, 0.0, 0.25])
    options.setSupercell([3, 1, 5])
    np.testing.assert_allclose(options.particlePositionCartesian(), options.cell.T @ np.array([1.5, 0.0, 2.25]))


def test_energy_range_stays_consistent(options):
    options.setEnergyMin(25.0)       # above the maximum (20 eV)
    assert options.energyMin < options.energyMax
    options.setEnergyStep(-1.0)
    assert options.energyStep > 0
    options.setExcMinIntensity(3.0)
    assert options.excMinIntensity == 1.0


def test_gw_signal(qtbot, options):
    assert options.gw
    with qtbot.waitSignal(options.gwChanged) as blocker:
        options.setGW(False)
    assert blocker.args == [False]
    with qtbot.assertNotEmitted(options.gwChanged):
        options.setGW(False)


# Calculations

class Point:
    """Stand-in for a clicked pyqtgraph spot."""

    def __init__(self, i, j=1, x=0.0):
        self._data, self._x = PointData(i, j), x

    def data(self):
        return self._data

    def pos(self):
        return pg.Point(self._x, 0.0)


@pytest.fixture
def calculations():
    # Calculations run inline: results are there when the call returns
    calc = Calculations(Options(), synchronous=True)
    calc.qIndices = [4, 7, 9, 0, 2, 3, 5, 6, 8, 1]
    return calc


def test_select_exciton(qtbot, calculations):
    with qtbot.waitSignal(calculations.excitonSelected) as blocker:
        calculations.selectExciton([Point(1, j=3, x=2.25)], True)
    # Path point 1 is Q-point index 7
    assert blocker.args == [7, 3, 2.25] and calculations.selectedExciton == (7, 3, 2.25)

    calculations.resetDataset()
    assert calculations.selectedExciton is None and calculations.qIndices is None
    with qtbot.assertNotEmitted(calculations.excitonSelected):
        calculations.selectExciton([Point(1)], True)


def test_calculation_signals(qtbot, calculations):
    """Progress signals of a calculation, and a request that cannot run is rejected at once."""
    events = []
    calculations.busyStarted.connect(lambda message: events.append(('start', message)))
    calculations.busyFinished.connect(lambda: events.append(('finish',)))
    calculations.errorOccurred.connect(lambda title, message: events.append(('error', title, message)))

    calculations.getExcitonDispersion()   # no Q-path
    assert events == [('error', 'Computing the excitonic dispersion failed', 'No Q-path: set one on the System page first.')]

    events.clear()
    calculations.tasks.submit('Working…', lambda context: 1, lambda result: None)
    assert events == [('start', 'Working…'), ('finish',)]


def test_wave_function_needs_existing_exciton_index(qtbot, calculations, monkeypatch, tmp_path):
    """The Q-point picks the file; an index beyond its excitons is an error, not a crash."""
    opened = {}

    class FakeExcitonDB:
        eigenvalues = np.zeros(5)

        @classmethod
        def from_db_file(cls, lattice, filename, folder, neigs):
            opened.update(filename=filename, neigs=neigs)
            return cls()

    import visual_excitons.core.calculations as module
    monkeypatch.setattr(module, 'YamboExcitonDB', FakeExcitonDB)
    calculations.lattice = object()

    with qtbot.waitSignal(calculations.errorOccurred) as blocker:
        calculations.computeExcitonWaveFunction(q_index=4, exc_index=12)
    assert opened == {'filename': 'ndb.BS_diago_Q5', 'neigs': 32}
    assert 'Exciton 12 does not exist' in blocker.args[1]


# Absorption curves and their styles (issue #2)

def test_absorption_curves_keep_their_styles(calculations):
    style = AbsorptionStyle()
    calculations.excitonAbsorptionCurveAppended.connect(style.appendCurveStyle)
    calculations.excitonAbsorptionCurveRemoved.connect(style.removeCurveStyle)
    calculations.qIndices = list(range(10))
    calculations.computeAbsorptionSpectrum = lambda index, q, parameters: {'q': q, 'index': index}

    def click(i, ctrl=False):
        calculations.computeQPointAbsorptionSpectrum([Point(i)], ctrl)
        curves = [data['q'] for data in calculations.excAbsData]
        # Each style was created as pg.mkPen(q): its color identifies its curve
        styles = [next(q for q in range(10) if pen.color() == pg.mkPen(q).color()) for pen in style.curveStyle.curvePens]
        assert styles == curves and style.common.numCurves == len(curves)
        return curves

    assert click(1, ctrl=True) == [1]      # kept
    assert click(0) == [1, 0]              # temporary
    assert click(3, ctrl=True) == [1, 3]   # kept; the temporary curve, not the last one, is dropped
    assert click(5) == [1, 3, 5]
    assert click(6) == [1, 3, 6]           # replaces the temporary curve
    # A kept curve Ctrl-clicked again is dropped, and so are the temporary ones
    assert click(1, ctrl=True) == [3]
    assert click(4) == [3, 4]
    assert click(3) == [3]                 # clicking a kept curve drops the temporary ones


# Automatic absorption range, selection from both plots and its highlight

def test_automatic_absorption_range():
    from visual_excitons.core.calculations import automaticAbsorptionRange
    assert automaticAbsorptionRange([2.09, 2.36, 2.47]) == (1.5, 3.0)
    assert automaticAbsorptionRange([0.2, 0.3], margin=0.5) == (0.0, 0.8)   # never below zero


def test_select_from_dispersion_and_highlight_positions(calculations):
    # Two excitons along a three-point path; Q-point 9 is the middle one
    calculations.qIndices = [4, 9, 2]
    calculations.dispPoints = [[[0, 2.0], [1, 2.1], [2, 2.2]], [[0, 2.5], [1, 2.6], [2, 2.7]]]
    calculations.excAbsData = [{'q': 9, 'brightExcEnergy': np.array([2.6, 3.0]), 'brightExcAbsorption': np.array([5.0, 1.0]),
                                'brightExcIndices': np.array([2.0, 7.0])}]

    point = Point(1, j=2)
    point.pos = lambda: pg.Point(1.0, 2.6)   # dispersion: x along the path, y the energy
    calculations.selectDispersionExciton([point], False)
    assert calculations.selectedExciton == (9, 2, 2.6)
    assert calculations.selectedExcitonPositions() == {'dispersion': [(1, 2.6)], 'absorption': [(2.6, 5.0)]}

    # An exciton beyond the plotted ones, bright in the spectrum: only there
    calculations.selectExciton([Point(1, j=7, x=3.0)], True)
    assert calculations.selectedExcitonPositions() == {'dispersion': [], 'absorption': [(3.0, 1.0)]}


@pytest.mark.data
def test_new_lattice_clears_the_q_path():
    from conftest import datasetPath
    options = Options()
    options.setSaveDir(str(datasetPath('BiI3_Bulk_8x8x8') / 'save'))
    options.setIbrav(options.detectLatticeType())
    options.setLatticeData(options.ibrav)
    options.extraHighSymmetryPoints = {'M': [0.25, 0.25, 0.0]}
    options.setBrillouinZone(path='LGZFM', npoints=50)
    assert options.qBZ is not None
    options.setLatticeData(options.ibrav)   # e.g. another dataset or ibrav
    assert options.qBZ is None and options.extraHighSymmetryPoints == {}
