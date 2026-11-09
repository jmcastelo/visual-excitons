"""Publication figures of the 2D plots, with Matplotlib, and their scripts."""

import subprocess
import sys
import warnings

import numpy as np
import pytest
from matplotlib.colors import to_hex

from visual_excitons.core import figures
from visual_excitons.core.figures import buildFigure, saveFigure, saveData, loadData, availablePanels, sharedEnergyRange
from visual_excitons.core.figure_script import writeFigureScript


def sampleData():
    x = np.linspace(0, 3, 40)
    path = np.linspace(0, 3, 12)
    points = np.stack([np.stack([path, 2.1 + 0.05 * k + 0.08 * np.cos(2 * path)], axis=1) for k in range(3)])
    energy = np.linspace(1.5, 3.0, 200)

    def spectrum(q, shift):
        return {'q': q, 'energy': energy, 'absorption': 4 * np.exp(-((energy - 2.15 - shift) / 0.1) ** 2),
                'brightEnergy': np.array([2.14 + shift]), 'brightAbsorption': np.array([3.9]),
                'brightIndices': np.array([2.0]), 'brightIntensities': np.array([1.0]),
                'darkEnergy': np.array([2.1, 2.2, 2.3])}
    return {
        'dispersion': {'points': points, 'xInter': x, 'yInter': np.array([2.1 + 0.05 * k + 0.08 * np.cos(2 * x) for k in range(3)]),
                       'ticks': [0, 1, 2, 3], 'labels': ['L', 'G', 'Z', 'F']},
        'absorption': [spectrum(0, 0.0), spectrum(4, 0.05)],
        'bands': {'k': x, 'bands': np.array([-1 - 0.2 * np.cos(x)]), 'weights': np.array([0.05 + 0 * x]),
                  'ticks': [0, 1, 2, 3], 'labels': ['L', 'G', 'Z', 'F']},
        'selected': {'dispersion': [[1.0, 2.12]], 'absorption': [[2.14, 3.9]]},
    }


STYLES = {'dispersion': {'curves': [{'color': '#d62728', 'width': 1.0, 'dash': '-', 'marker': 'o', 'markerSize': 3}]},
          'absorption': {'curves': [{'color': '#00c853', 'width': 1.0, 'dash': '-', 'marker': 'o', 'markerSize': 3},
                                    {'color': '#ff5722', 'width': 1.0, 'dash': [0, [3, 1, 1, 1]], 'marker': 's',
                                     'markerSize': 3}]},
          'bands': {'curves': [{'color': '#000000', 'width': 1.0, 'dash': '-'}], 'fill': '#ffa500'}}


def dataAxes(figure):
    """The axes with data, in creation order (exciton bars excluded: no y ticks, below the absorption)."""
    return [ax for ax in figure.axes if ax.lines or ax.collections]


def test_available_panels():
    data = sampleData()
    assert availablePanels(data) == ['dispersion', 'absorption', 'bands']
    assert availablePanels({'absorption': [], 'dispersion': {'points': []}}) == []
    with pytest.raises(ValueError, match='Nothing to draw'):
        buildFigure({}, STYLES, {'panels': ['dispersion']})


@pytest.mark.parametrize('arrangement', ['row', 'column'])
def test_panels_and_arrangement(arrangement):
    figure = buildFigure(sampleData(), STYLES, {'panels': ['dispersion', 'absorption', 'bands'], 'arrangement': arrangement})
    axes = figure.axes
    assert len(axes) == 4                                    # three panels and the exciton bars
    titles = [ax.get_title(loc='left') for ax in axes]
    assert [t for t in titles if t] == ['(a)', '(b)', '(c)']
    dispersion, absorption, bars, bands = axes[0], axes[1], axes[3], axes[2]
    assert [label.get_text() for label in dispersion.get_xticklabels()] == ['L', r'$\Gamma$', 'Z', 'F']
    assert absorption.get_legend() is not None
    assert [t.get_text() for t in absorption.get_legend().get_texts()] == ['Q-point 1', 'Q-point 5']
    positions = [ax.get_position() for ax in (dispersion, absorption, bands)]
    if arrangement == 'row':
        assert positions[0].x0 < positions[1].x0 < positions[2].x0
    else:
        assert positions[0].y0 > positions[1].y0 > positions[2].y0
    assert figure.get_size_inches() == pytest.approx([8.6 / 2.54, 6.0 / 2.54])


def test_styles_are_carried_over():
    figure = buildFigure(sampleData(), STYLES, {'panels': ['absorption'], 'excitonBars': False, 'highlight': True})
    ax = figure.axes[0]
    curves = [line for line in ax.lines if line.get_label().startswith('Q-point')]
    assert to_hex(curves[0].get_color()) == '#00c853' and to_hex(curves[1].get_color()) == '#ff5722'
    assert curves[1].get_linestyle() != '-'                 # the dash pattern, back from JSON as lists
    rings = [line for line in ax.lines if line.get_markerfacecolor() == 'none']
    assert len(rings) == 1 and to_hex(rings[0].get_markeredgecolor()) == figures.HIGHLIGHT_COLOR
    # Without the highlight, no ring
    figure = buildFigure(sampleData(), STYLES, {'panels': ['absorption'], 'highlight': False})
    assert not [line for line in figure.axes[0].lines if line.get_markerfacecolor() == 'none']


def test_shared_energy_axis():
    data = sampleData()
    figure = buildFigure(data, STYLES, {'panels': ['dispersion', 'absorption'], 'shareEnergy': True})
    dispersion, absorption = figure.axes
    assert absorption.get_shared_y_axes().joined(dispersion, absorption)
    # Rotated absorption: energy along y; the range of the dispersion and the bright excitons
    low, high = sharedEnergyRange(data['dispersion'], data['absorption'])
    assert dispersion.get_ylim() == pytest.approx((low, high))
    assert low < 2.1 and high > 2.2 and high < 2.6           # not the whole 1.5-3 eV of the spectra
    assert len(figure.axes) == 2                             # no exciton bars when sharing


def test_files_and_fonts(tmp_path):
    data = sampleData()
    for font in figures.FONTS:
        figure = buildFigure(data, STYLES, {'panels': ['dispersion', 'bands'], 'font': font})
        with warnings.catch_warnings():
            warnings.filterwarnings('error', message='Glyph')   # a missing character would fail
            for extension in ('pdf', 'svg', 'png', 'eps'):
                saveFigure(figure, tmp_path / f'f.{extension}')
        assert (tmp_path / 'f.pdf').read_bytes().startswith(b'%PDF')
    from PIL import Image
    image = Image.open(tmp_path / 'f.png')
    assert image.size[0] == pytest.approx(8.6 / 2.54 * 300, abs=2)   # 300 dpi


def test_data_round_trip(tmp_path):
    data = sampleData()
    options = {**figures.DEFAULT_OPTIONS, 'width': 12.0}
    saveData(tmp_path / 'd.npz', data, STYLES, options)
    loaded, styles, loadedOptions = loadData(tmp_path / 'd.npz')
    np.testing.assert_array_equal(loaded['dispersion']['points'], data['dispersion']['points'])
    np.testing.assert_array_equal(loaded['absorption'][1]['energy'], data['absorption'][1]['energy'])
    assert loaded['absorption'][1]['q'] == 4 and loaded['dispersion']['labels'] == ['L', 'G', 'Z', 'F']
    assert styles == STYLES and loadedOptions['width'] == 12.0


def test_exported_script_runs_on_its_own(tmp_path):
    """The script needs only NumPy, Matplotlib and its data file: run it in a separate, isolated Python."""
    script, dataFile = writeFigureScript(tmp_path / 'my figure.py', sampleData(), STYLES,
                                         {'panels': ['dispersion', 'absorption'], 'width': 12.9}, figureFormat='png',
                                         programVersion='0.1.0')
    text = script.read_text()
    assert 'import visual_excitons' not in text and 'from visual_excitons' not in text
    assert 'Visual Excitons 0.1.0' in text
    assert "'width': 12.9" in text and dataFile.name == 'my figure.npz'
    # Run from elsewhere, isolated: no access to this program
    result = subprocess.run([sys.executable, '-I', str(script)], cwd=tmp_path.parent, capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr
    output = tmp_path / 'my figure.png'
    assert output.is_file() and output.stat().st_size > 10_000


# The dialog

def test_export_dialog(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings, Qt
    from visual_excitons.gui import figure_export
    QSettings('VisualExcitons', 'VisualExcitons').remove('figureExport')
    data = sampleData()
    del data['bands']
    dialog = figure_export.FigureExportDialog(data, STYLES, defaultName='test')
    qtbot.addWidget(dialog)
    items = {dialog.panelList.item(i).data(Qt.ItemDataRole.UserRole): dialog.panelList.item(i)
             for i in range(dialog.panelList.count())}
    assert not (items['bands'].flags() & Qt.ItemFlag.ItemIsEnabled)     # no data: disabled
    assert dialog.options()['panels'] == ['dispersion', 'absorption']
    assert dialog.preview.pixmap() is not None and not dialog.preview.pixmap().isNull()

    dialog.widthComboBox.setCurrentIndex(2)
    assert dialog.widthSpinBox.value() == 17.8 and not dialog.widthSpinBox.isEnabled()
    dialog.checkBoxes['panelLabels'].setChecked(False)
    items['absorption'].setCheckState(Qt.CheckState.Unchecked)
    assert dialog.options()['panels'] == ['dispersion']

    target = tmp_path / 'figure'
    monkeypatch.setattr(figure_export.QFileDialog, 'getSaveFileName',
                        lambda *args, **kwargs: (str(target), 'SVG (*.svg)'))
    dialog.saveFigure()
    assert (tmp_path / 'figure.svg').is_file() and dialog.savedFile.endswith('figure.svg')
    monkeypatch.setattr(figure_export.QFileDialog, 'getSaveFileName',
                        lambda *args, **kwargs: (str(tmp_path / 'script.py'), 'Python script (*.py)'))
    dialog.saveScript()
    assert (tmp_path / 'script.py').is_file() and (tmp_path / 'script.npz').is_file()

    # Remembered for next time
    again = figure_export.FigureExportDialog(sampleData(), STYLES)
    qtbot.addWidget(again)
    assert again.widthSpinBox.value() == 17.8 and not again.checkBoxes['panelLabels'].isChecked()
    assert again.options()['panels'] == ['dispersion']


def test_styles_from_the_app(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPen, QColor
    from visual_excitons.gui.figure_export import penStyle
    pen = QPen(QColor('#123456'), 2.0, Qt.PenStyle.DashLine)
    style = penStyle(pen, 'star', 10)
    assert style['color'] == '#123456' and style['dash'] == '--' and style['marker'] == '*'
    assert style['width'] == pytest.approx(1.6) and style['markerSize'] == pytest.approx(5.5)
