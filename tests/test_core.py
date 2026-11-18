"""The dataset, the parameters and the calculation bookkeeping (no Yambo databases needed)."""

import numpy as np
import pyqtgraph as pg
import pytest

from visual_excitons.core.parameters import SpectraParameters, WavefunctionParameters
from visual_excitons.core.calculations import Calculations, PointData
from visual_excitons.core.dataset import Dataset, findDataset, datasetName, datasetExists
from visual_excitons.core.style import AbsorptionStyle


# Datasets

def makeDataset(root, name, gw=True):
    """A dataset's folders (an empty ns.db1 and BSE file are found by name; a QP database by its content)."""
    from conftest import writeQPDatabase
    for directory, filename in [('save', 'ns.db1'), ('diagos', 'ndb.BS_diago_Q1')]:
        (root / name / directory).mkdir(parents=True)
        (root / name / directory / filename).touch()
    if gw:
        (root / name / 'qp').mkdir(parents=True)
        writeQPDatabase(root / name / 'qp' / 'ndb.QP')
    return root / name


def test_find_dataset(tmp_path):
    folder = makeDataset(tmp_path, 'BiI3')
    dataset = findDataset(folder)
    assert dataset == {'save': str(folder / 'save'), 'diago': str(folder / 'diagos'), 'qp': str(folder / 'qp'), 'gw': True,
                       'qpFile': 'ndb.QP'}
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


# The dataset and the parameters

CELL = np.array([[2.0, 0, 0], [1.0, 3.0, 0], [0, 0, 4.0]])


def test_view_vectors():
    from visual_excitons.core.lattice_info import viewVectorToCartesian
    np.testing.assert_allclose(viewVectorToCartesian([1, 2, 3], 'Cartesian', CELL), [1, 2, 3])
    np.testing.assert_allclose(viewVectorToCartesian([1, 1, 0], 'Lattice [uvw]', CELL), [3.0, 3.0, 0])
    # (hkl) normals are perpendicular to the lattice vectors of the plane
    normal = viewVectorToCartesian([0, 0, 1], 'Reciprocal (hkl)', CELL)
    assert abs(normal @ CELL[0]) < 1e-12 and abs(normal @ CELL[1]) < 1e-12
    with pytest.raises(ValueError):
        viewVectorToCartesian([1, 0, 0], 'Lattice [uvw]', Dataset().cell)      # no dataset: no lattice


def test_fixed_particle_sits_in_the_central_cell():
    parameters = WavefunctionParameters(supercell=[3, 1, 5])
    parameters.setPosition([0.5, 0.0, 0.25])
    assert parameters.holePosition == [0.5, 0.0, 0.25] and parameters.position('e') == [0.0, 0.0, 0.0]
    np.testing.assert_allclose(parameters.positionCartesian(CELL), CELL.T @ np.array([1.5, 0.0, 2.25]))


def test_energy_range_stays_consistent():
    parameters = SpectraParameters()
    parameters.setEnergyMin(25.0)       # above the maximum (20 eV)
    assert parameters.energyMin < parameters.energyMax
    parameters.setEnergyStep(-1.0)
    assert parameters.energyStep > 0


def test_gw_signal(qtbot):
    dataset = Dataset()
    assert dataset.gw
    with qtbot.waitSignal(dataset.gwChanged) as blocker:
        dataset.setGW(False)
    assert blocker.args == [False]
    with qtbot.assertNotEmitted(dataset.gwChanged):
        dataset.setGW(False)


def test_sum_degenerate_signal(qtbot):
    calc = Calculations(synchronous=True)
    assert calc.sumDegenerate
    with qtbot.waitSignal(calc.sumDegenerateChanged) as blocker:
        calc.setSumDegenerate(False)
    assert blocker.args == [False] and not calc.sumDegenerate
    with qtbot.assertNotEmitted(calc.sumDegenerateChanged):
        calc.setSumDegenerate(False)


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
    calc = Calculations(synchronous=True)
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
        # Each spectrum's palette color is that of its Q-point: it identifies its curve
        from visual_excitons.core.style import paletteColor
        styles = [next(q for q in range(10) if pen.color() == paletteColor(q)) for pen in style.curveStyle.curvePens]
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
    dataset = Dataset()
    dataset.setSaveDir(str(datasetPath('BiI3_Bulk_8x8x8') / 'save'))
    dataset.identifyLattice()
    dataset.extraHighSymmetryPoints = {'M': [0.25, 0.25, 0.0]}
    dataset.setBrillouinZone(path='LGZFM', npoints=50)
    assert dataset.qBZ is not None
    dataset.setLatticeData()                # e.g. another dataset
    assert dataset.qBZ is None and dataset.extraHighSymmetryPoints == {}


def datasetWithCell(cell):
    from visual_excitons.core.lattice_info import cellParameters
    dataset = Dataset()
    dataset.cell = np.asarray(cell, dtype=float)
    dataset.latticeParameters = cellParameters(dataset.cell)
    return dataset


A = 6.8
@pytest.mark.parametrize('cell, ibrav, variant', [
    (A / 2 * np.array([[-1, 0, 1], [0, 1, 1], [-1, 1, 0]]), 2, 'FCC'),       # Quantum ESPRESSO's vectors
    (A / 2 * np.array([[0, 1, 1], [1, 0, 1], [1, 1, 0]]), 2, 'FCC'),        # other primitive vectors
    (A / 2 * np.array([[1, 1, 1], [-1, 1, 1], [-1, -1, 1]]), 3, 'BCC'),
    (0.9 * np.array([[-2, 2, 4], [2, -2, 4], [2, 2, -4]]), 7, 'BCT2'),
    (np.array([[0, A, 0], [-A, 0, 0], [0, 0, A]]), 1, 'CUB'),                # rotated
    (np.array([[3, 0, 0], [1.5, 1.5 * np.sqrt(3), 0], [0, 0, 5]]), 4, 'HEX'), # 60 degrees
])
def test_lattice_detected_from_the_cell(cell, ibrav, variant):
    """Centred lattices too: the primitive vector lengths alone took an FCC crystal for a rhombohedral one."""
    dataset = datasetWithCell(cell)
    assert dataset.identifyLattice() == ibrav and dataset.ibrav == ibrav
    assert dataset.variant == variant and dataset.symmetryTolerance == 1e-5
    # The Brillouin zone of the cell itself: its special points in the cell's reduced coordinates
    dataset.setBrillouinZone(npoints=40)
    np.testing.assert_allclose(dataset.qBZ.cell, dataset.cell)
    assert dataset.pathString() == dataset.defaultPath


def test_slightly_distorted_cell_is_identified_with_a_looser_tolerance():
    """A hexagonal cell with numerical noise: not hexagonal at the strictest tolerance, hexagonal at a looser one."""
    cell = np.array([[3.0, 0.0, 0.0], [-1.5, 1.5 * np.sqrt(3) * (1 + 2e-5), 0.0], [0.0, 0.0, 5.0]])
    dataset = datasetWithCell(cell)
    assert dataset.identifyLattice() == 4 and dataset.symmetryTolerance > 1e-5
    assert dataset.variant == 'HEX' and dataset.strictVariant.startswith('ORC')


def test_unsupported_lattice_is_not_detected():
    triclinic = [[3.0, 0.1, 0.2], [0.4, 4.1, 0.3], [0.5, 0.6, 5.3]]
    dataset = datasetWithCell(triclinic)
    assert dataset.identifyLattice() is None and dataset.ibrav == -1 and dataset.latticeProblem
    with pytest.raises(ValueError, match='not identified'):
        dataset.setBrillouinZone(npoints=10)


def test_new_dispersion_or_dataset_drops_curve_styles(calculations):
    """Curves and their styles stay parallel when all curves are dropped at once."""
    style = AbsorptionStyle()
    calculations.excitonAbsorptionCurveAppended.connect(style.appendCurveStyle)
    calculations.excitonAbsorptionCurveRemoved.connect(style.removeCurveStyle)
    calculations.qIndices = list(range(10))
    calculations.computeAbsorptionSpectrum = lambda index, q, parameters: {'q': q, 'index': index}
    for i in (1, 2, 3):
        calculations.computeQPointAbsorptionSpectrum([Point(i)], True)
    assert len(style.curveStyle.curvePens) == 3

    calculations.clearAbsorptionCurves()
    assert calculations.excAbsData == [] and style.curveStyle.curvePens == [] and style.common.numCurves == 0

    calculations.computeQPointAbsorptionSpectrum([Point(4)], True)
    calculations.resetDataset()
    assert style.curveStyle.curvePens == [] and calculations.dispPoints == [] and len(calculations.k) == 0
