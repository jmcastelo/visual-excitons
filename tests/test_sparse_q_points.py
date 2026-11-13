"""Datasets with only some Q-points computed: some ndb.BS_diago_Q<n> files, e.g. Q1, Q2, Q5, Q30, or Q1 alone."""

import contextlib
import io

import pytest

from visual_excitons.core.options import Options, computedQPoints, qPointNames
from visual_excitons.core.calculations import Calculations, PointData
from conftest import datasetPath


def test_computed_q_points_come_from_the_file_numbers(tmp_path):
    for name in ('ndb.BS_diago_Q1', 'ndb.BS_diago_Q30', 'ndb.BS_diago_Q5', 'ndb.BS_diago_Q2',
                 'ndb.BS_diago_Q1_fragment_1', 'ndb.BS_diago_Qx', 'ndb.BS_diago_Q0'):
        (tmp_path / name).touch()
    assert computedQPoints(tmp_path) == [0, 1, 4, 29]
    assert qPointNames([0, 1, 4, 29]) == 'Q1, Q2, Q5, Q30'
    assert qPointNames([0, 1, 2, 3, 9]) == 'Q1–Q4, Q10'
    assert qPointNames(list(range(0, 60, 2)), limit=3) == 'Q1, Q3, Q5, …'


def test_q_point_field_offers_only_computed_ones(qapp):
    from visual_excitons.gui.parameters_3d_widget import ChoiceSpinBox
    spin = ChoiceSpinBox(minimum=1, maximum=10)
    spin.setValue(7)
    assert spin.value() == 7                                   # no choices: any value
    spin.setChoices([1, 2, 5, 30])
    assert (spin.minimum(), spin.maximum()) == (1, 30) and spin.value() == 5
    spin.setValue(3)
    assert spin.value() == 2                                   # the nearest computed one
    spin.stepBy(1)
    assert spin.value() == 5                                   # the arrows skip those not computed
    spin.stepBy(1)
    assert spin.value() == 30
    spin.stepBy(1)
    assert spin.value() == 30
    from PySide6.QtGui import QValidator
    assert spin.validate('3', 1)[0] == QValidator.State.Intermediate
    assert spin.validate('5', 1)[0] == QValidator.State.Acceptable
    assert spin.fixup('29') == '30'


def partialDataset(tmp_path, qNumbers):
    """BiI3 with only the BSE files of `qNumbers`, as symbolic links."""
    source = datasetPath('BiI3_Bulk_8x8x8')
    folder = tmp_path / 'partial'
    (folder / 'diagos').mkdir(parents=True)
    (folder / 'save').symlink_to(source / 'save')
    for n in qNumbers:
        (folder / 'diagos' / f'ndb.BS_diago_Q{n}').symlink_to(source / 'diagos' / f'ndb.BS_diago_Q{n}')
    return folder


def calculationsFor(folder):
    options = Options()
    options.setSaveDir(str(folder / 'save'))
    options.setDiagoDir(str(folder / 'diagos'))
    options.setIbrav(options.detectLatticeType())
    options.setLatticeData(options.ibrav)
    options.setBrillouinZone(path='LGZF', npoints=100)
    calculations = Calculations(options, synchronous=True)
    errors, notes = [], []
    calculations.errorOccurred.connect(lambda title, message: errors.append(message))
    calculations.dispersionNoteChanged.connect(notes.append)
    return options, calculations, errors, notes


def quietly(call, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        call(*args)


@pytest.mark.data
def test_sparse_q_points(tmp_path):
    options, calc, errors, notes = calculationsFor(partialDataset(tmp_path, (1, 2, 5, 30)))
    assert options.qPoints == [0, 1, 4, 29] and options.qPointCount() == '4 of 90 Q-points'
    assert not options.hasAllQPoints()

    # The dispersion: the computed Q-points on the path, not interpolated, and why
    quietly(calc.getExcitonDispersion)
    assert not errors
    assert sorted(set(int(q) for q in calc.qIndices)) == [0, 1, 4]
    assert len(calc.dispXInter) == 0 and len(calc.dispPoints) == options.nExcitons
    assert 'Only Q1, Q2, Q5, Q30 computed (4 of the 90' in notes[-1] and 'not interpolated' in notes[-1]
    assert 'Absorption section' in notes[-1]                   # Q30 is off the path

    # The spectrum at Q30, off the path; selecting one of its excitons gives Q30
    quietly(calc.showQPointAbsorption, 29)
    assert not errors and [data['q'] for data in calc.excAbsData] == [29]
    point = calc.excAbsData[0]['data'][0]
    assert point.q == 29

    class Clicked:
        def data(self):
            return point

        def pos(self):
            from pyqtgraph import Point
            return Point(2.2, 0.0)
    calc.selectExciton([Clicked()], True)
    assert calc.selectedExciton[0] == 29

    # Q-points not computed: said so
    quietly(calc.showQPointAbsorption, 2)
    assert errors[-1].startswith('Q-point 3 was not computed') and 'Q1, Q2, Q5, Q30' in errors[-1]
    with pytest.raises(ValueError, match='Q-point 4 was not computed'):
        calc.estimateWaveFunction(3, 1, 5, [1, 1, 1])
    quietly(lambda: calc.computeExcitonWaveFunction(q_index=3))
    assert errors[-1].startswith('Q-point 4 was not computed')


@pytest.mark.data
def test_only_gamma(tmp_path):
    options, calc, errors, notes = calculationsFor(partialDataset(tmp_path, (1,)))
    counts = []
    calc.dispersionQPointCountChanged.connect(counts.append)
    quietly(calc.getExcitonDispersion)
    assert not errors and counts == [1]                        # one Q-point: lines across the plot
    assert set(int(q) for q in calc.qIndices) == {0}
    assert 'Only Q1 computed' in notes[-1] and 'shows it' in notes[-1] and 'Absorption section' not in notes[-1]
    # The whole path on the axis, not a point
    low, high = calc.dispersionAxes['xRange']
    assert high > low


@pytest.mark.data
def test_no_computed_q_point_on_the_path(tmp_path):
    options, calc, errors, notes = calculationsFor(partialDataset(tmp_path, (30,)))
    quietly(calc.getExcitonDispersion)
    assert 'None of the computed Q-points (Q30) is on the Q-path' in errors[-1]


def test_band_structure_needs_gamma_from_the_q_point():
    """The excitons of a spectrum carry their Q-point: Γ is Q1, whatever their place on the path."""
    calc = Calculations(Options(), synchronous=True)
    applied, submitted = [], []
    calc._applyBandStructure = applied.append
    calc.tasks.submit = lambda *args, **kwargs: submitted.append(args)

    class Clicked:
        def __init__(self, q):
            self._data = PointData(-1, 1, q=q)

        def data(self):
            return self._data
    calc.getExcitonBandStructure([Clicked(29)], None)
    assert applied and applied[-1]['k'] == [] and not submitted   # not Γ: cleared
    calc.getExcitonBandStructure([Clicked(0)], None)
    assert submitted                                               # Γ: computed
