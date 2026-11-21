"""The dataset, the parameters and the calculation bookkeeping (no Yambo databases needed)."""

import numpy as np
import pyqtgraph as pg
import pytest

from visual_excitons.core.parameters import SpectraParameters, WavefunctionParameters
from visual_excitons.core.calculations import Calculations, PointData
from visual_excitons.core.dataset import (Dataset, findDataset, datasetFromPaths, datasetName, datasetExists,
                                         datasetChoices, projectSteps)
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


def makeWorkflowsProject(root, name='WSe2', projectFile=False):
    """
    A Visual Workflows project after downloading for Visual Excitons: SAVE, GW
    and BSE in step folders of their own; with its project.toml if `projectFile`
    (without it, as a copy of the folders only).
    """
    from conftest import writeQPDatabase
    project = root / name
    for directory, filename in [('01-scf/outputs/WSe2.save', 'data-file-schema.xml'), ('03-p2y/outputs/SAVE', 'ns.db1'),
                                ('05-bse/outputs/diago', 'ndb.BS_diago_Q1')]:
        (project / directory).mkdir(parents=True)
        (project / directory / filename).touch()
    (project / '04-gw/outputs/gw').mkdir(parents=True)
    writeQPDatabase(project / '04-gw/outputs/gw/ndb.QP')
    if projectFile:
        (project / 'project.toml').write_text(
            'format = "workflow-project/1"\nname = "WSe2"\ncluster = "Lynx"\nremote_dir = "WSe2"\n'
            'steps = ["01-scf", "02-nscf", "03-p2y", "04-gw", "05-bse"]\n')
    return project


def test_workflows_project_steps(tmp_path):
    """A project's steps are read from its project.toml: only their outputs/ folders, in order."""
    project = makeWorkflowsProject(tmp_path, projectFile=True)
    assert projectSteps(project) == [project / step / 'outputs' for step in ('01-scf', '03-p2y', '04-gw', '05-bse')]
    assert projectSteps(tmp_path) is None                       # no project.toml
    for text in ('format = "cluster-profile/1"\nsteps = ["x"]\n', 'steps = ["x"]\n', 'not toml = = 1\n',
                 'format = "workflow-project/1"\nsteps = "01-scf"\n'):
        (project / 'project.toml').write_text(text)
        assert projectSteps(project) is None, text
    # Only step folder names: nothing outside the project is searched
    (project / 'project.toml').write_text('format = "workflow-project/2"\nsteps = ["../x", "/tmp", "..", 3, "05-bse"]\n')
    assert projectSteps(project) == [project / '05-bse/outputs']


def test_find_dataset_deeper_in_project_steps(tmp_path):
    """In a project, results deeper than 3 levels from its folder are found: 3 levels below each outputs/ folder."""
    project = makeWorkflowsProject(tmp_path, projectFile=True)
    (project / '03-p2y/outputs/SAVE').rename(tmp_path / 'SAVE')
    (project / '03-p2y/outputs/WSe2.save').mkdir()
    (tmp_path / 'SAVE').rename(project / '03-p2y/outputs/WSe2.save/SAVE')     # p2y run without -O
    (project / '05-bse/outputs/diago').rename(tmp_path / 'diago')
    (project / '05-bse/outputs/bse').mkdir()
    (tmp_path / 'diago').rename(project / '05-bse/outputs/bse/diago')         # -J bse/diago
    dataset = findDataset(project)
    assert dataset['save'] == str(project / '03-p2y/outputs/WSe2.save/SAVE')
    assert dataset['diago'] == str(project / '05-bse/outputs/bse/diago')
    assert dataset['qp'] == str(project / '04-gw/outputs/gw') and dataset['qpFile'] == 'ndb.QP'


def test_dataset_choices_in_a_project(tmp_path):
    """Several BSE steps: all listed in the project's order, the first taken by default."""
    project = makeWorkflowsProject(tmp_path, projectFile=True)
    (project / '06-bse-q/outputs/diago').mkdir(parents=True)
    (project / '06-bse-q/outputs/diago/ndb.BS_diago_Q1').touch()
    (project / 'project.toml').write_text((project / 'project.toml').read_text().replace('"05-bse"', '"05-bse", "06-bse-q"'))
    # Not listed in the project: never searched
    (project / 'old/outputs/diago').mkdir(parents=True)
    (project / 'old/outputs/diago/ndb.BS_diago_Q1').touch()
    choices = datasetChoices(project)
    assert choices['diago'] == [str(project / '05-bse/outputs/diago'), str(project / '06-bse-q/outputs/diago')]
    assert choices['save'] == [str(project / '03-p2y/outputs/SAVE')] and len(choices['qp']) == 1
    assert findDataset(project)['diago'] == str(project / '05-bse/outputs/diago')
    assert datasetChoices(tmp_path) == {'save': [], 'diago': [], 'qp': []}


def test_find_dataset_in_a_workflows_project(tmp_path):
    """With a single SAVE directory, the BSE and GW directories are found anywhere in the folder."""
    project = makeWorkflowsProject(tmp_path)
    dataset = findDataset(project)
    assert dataset == {'save': str(project / '03-p2y/outputs/SAVE'), 'diago': str(project / '05-bse/outputs/diago'),
                       'qp': str(project / '04-gw/outputs/gw'), 'gw': True, 'qpFile': 'ndb.QP'}
    assert datasetName(dataset) == 'WSe2'


def test_find_dataset_prefers_the_directories_next_to_save(tmp_path):
    """BSE directories next to the SAVE one come first, even with others elsewhere in the folder."""
    project = makeWorkflowsProject(tmp_path)
    (project / '03-p2y/outputs/diago').mkdir()
    (project / '03-p2y/outputs/diago/ndb.BS_diago_Q1').touch()
    assert findDataset(project)['diago'] == str(project / '03-p2y/outputs/diago')


def test_find_dataset_does_not_search_further_with_several_systems(tmp_path):
    """With two SAVE directories, the databases of the other system are never taken."""
    makeDataset(tmp_path, 'A', gw=False)
    (tmp_path / 'A/diagos/ndb.BS_diago_Q1').unlink()
    makeDataset(tmp_path, 'B', gw=True)
    dataset = findDataset(tmp_path)
    assert dataset['save'].endswith('A/save') and dataset['diago'] is None and dataset['qp'] is None


def test_dataset_from_paths(tmp_path):
    """Directories given one by one take the place of those found."""
    project = makeWorkflowsProject(tmp_path)
    (project / '06-bse-q/outputs/diago').mkdir(parents=True)
    (project / '06-bse-q/outputs/diago/ndb.BS_diago_Q2').touch()
    dataset = datasetFromPaths(project, bse=project / '06-bse-q/outputs/diago')
    assert dataset['save'] == str(project / '03-p2y/outputs/SAVE')
    assert dataset['diago'] == str(project / '06-bse-q/outputs/diago')
    assert dataset['qp'] == str(project / '04-gw/outputs/gw') and dataset['gw']
    # Without a folder: only what is given; a QP database by its file, renamed or not
    (project / '04-gw/outputs/gw/ndb.QP').rename(project / '04-gw/outputs/gw/ndb.QP_59_66')
    dataset = datasetFromPaths(save=project / '03-p2y/outputs/SAVE', qp=project / '04-gw/outputs/gw/ndb.QP_59_66')
    assert dataset == {'save': str(project / '03-p2y/outputs/SAVE'), 'diago': None, 'qp': str(project / '04-gw/outputs/gw'),
                       'qpFile': 'ndb.QP_59_66', 'gw': True}
    assert datasetFromPaths(qp=project / '04-gw/outputs/gw')['qpFile'] == 'ndb.QP_59_66'


@pytest.mark.parametrize('arguments, message', [
    ({'folder': 'missing'}, 'Not a folder'),
    ({'save': '05-bse/outputs/diago'}, 'No SAVE directory'),
    ({'bse': '03-p2y/outputs/SAVE'}, 'No BSE databases'),
    ({'qp': '05-bse/outputs/diago'}, 'No QP database'),
    ({'qp': '05-bse/outputs/diago/ndb.BS_diago_Q1'}, 'Not a QP database'),
])
def test_dataset_from_paths_refuses_wrong_paths(tmp_path, arguments, message):
    project = makeWorkflowsProject(tmp_path)
    with pytest.raises(ValueError, match=message):
        datasetFromPaths(**{key: project / value for key, value in arguments.items()})


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
