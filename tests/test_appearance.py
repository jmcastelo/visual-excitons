"""The Appearance of the 2D plots, kept between sessions."""

import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor, QFont

import visual_excitons.gui.main_window as main_window
from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from visual_excitons.gui.appearance import appearanceState, restoreAppearance
from visual_excitons.gui.theme import themeManager, PLOT_COLORS


def styles():
    return DispersionStyle(), AbsorptionStyle(), BandStructureStyle()


def withCurves(style, count):
    style.setNumCurves(count)
    style.applyDefaultStyle()
    return style


def test_style_round_trip(qapp):
    dispersion = withCurves(DispersionStyle(), 3)
    dispersion.curveStyle.setCurveColor(QColor('#123456'))
    dispersion.curveStyle.setCurveWidth(3)
    dispersion.curveStyle.setCurveStyle(2)                       # dots
    dispersion.setApplyToAllCurves(False)
    dispersion.setCurrentCurveIndex(1)
    dispersion.curveStyle.setCurveColor(QColor('#ff0000'))       # the second curve only
    dispersion.pointStyle.setPointSymbol(1)
    dispersion.setApplyToAllCurves(True)
    dispersion.pointStyle.setPointSize(9)
    dispersion.axesStyle.titleColor.setColor(QColor('#00aa00'))
    font = QFont('Serif', 15)
    dispersion.axesStyle.labelsFont.setFont(font)
    dispersion.axesStyle.setAxesWidth(2)
    state = dispersion.state()

    # A new style with as many curves: everything, each curve included
    restored = withCurves(DispersionStyle(), 3)
    changes = []
    restored.styleChanged.connect(lambda: changes.append(True))
    restored.setState(state, curves=True)
    assert changes                                                # the plots are redrawn
    pens = restored.curveStyle.curvePens
    assert [pen.color().name() for pen in pens] == ['#123456', '#ff0000', '#123456']
    assert all(pen.width() == 3 and pen.style() == Qt.PenStyle.DotLine for pen in pens)
    assert restored.curveStyle.commonPen.color().name() == '#123456'
    assert restored.pointStyle.commonPointSize == 9 and restored.pointStyle.pointSymbols[0] == 'o'
    assert restored.axesStyle.titleColor.getColor().name() == '#00aa00' and restored.axesStyle.axesWidth == 2
    assert restored.axesStyle.labelsFont.getFont().family() == font.family()
    assert restored.axesStyle.labelsFont.getFont().pointSize() == 15

    # Another number of curves: the common style only
    other = withCurves(DispersionStyle(), 5)
    other.setState(state, curves=True)
    assert other.curveStyle.commonPen.width() == 3
    assert all(pen.color().name() == '#000000' for pen in other.curveStyle.curvePens)

    # Damaged or partial states change nothing they do not have
    other.setState({'axes': {'width': 'wide'}, 'curve': {'pen': {}}, 'unknown': 1})
    assert other.curveStyle.commonPen.width() == 3


def test_legend_and_fill_round_trip(qapp):
    absorption, bands = AbsorptionStyle(), BandStructureStyle()
    absorption.legendStyle.setTextSize(14)
    absorption.legendStyle.setBackgroundColor(QColor('#eeeeee'))
    absorption.legendStyle.setBorderWidth(2)
    absorption.legendStyle.setOffsetX(80)
    bands.setBrushColor(QColor('#3366ff'))
    bands.setWeightFactor(2.5)

    absorption2, bands2 = AbsorptionStyle(), BandStructureStyle()
    factors = []
    bands2.weightFactorChanged.connect(factors.append)
    absorption2.setState(absorption.state())
    bands2.setState(bands.state())
    legend = absorption2.legendStyle
    assert legend.textSize == 14 and legend.backgroundColor.name() == '#eeeeee'
    assert legend.borderPen.width() == 2 and legend.offset == [80, 30]
    assert bands2.brush.color().name() == '#3366ff' and bands2.weightFactor == 2.5 and factors == [2.5]


def test_theme_colors_follow_the_theme(qapp):
    """Saved on the dark theme with its default colors, restored on the light one: the light defaults."""
    dark, light = PLOT_COLORS[True], PLOT_COLORS[False]
    saved = styles()
    saved[0].axesStyle.axesColor.setColor(dark['foreground'])
    saved[0].axesStyle.backgroundColor.setColor(dark['background'])
    saved[0].axesStyle.titleColor.setColor(QColor('#cc0000'))         # chosen: kept
    state = appearanceState(saved, dark=True)

    restored = styles()
    restoreAppearance(restored, state, dark=False)
    axes = restored[0].axesStyle
    assert axes.axesColor.getColor().rgb() == light['foreground'].rgb()
    assert axes.backgroundColor.getColor().rgb() == light['background'].rgb()
    assert axes.titleColor.getColor().name() == '#cc0000'


@pytest.fixture
def newWindow(qtbot, monkeypatch, tmp_path):
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')

    def make():
        w = main_window.MainWindow()
        qtbot.addWidget(w)
        return w
    yield make
    themeManager().setMode('System')


def test_appearance_is_resumed(newWindow):
    w = newWindow()
    w.setTheme('Light')
    w.dispersionStyle.curveStyle.setCurveWidth(4)
    w.dispersionStyle.axesStyle.ticksColor.setColor(QColor('#884400'))
    w.absorptionStyle.legendStyle.setTextSize(13)
    w.absorptionStyle.pointStyle.setPointSize(11)
    w.bandStructureStyle.setWeightFactor(3.0)
    w.close()

    w2 = newWindow()
    assert w2.dispersionStyle.curveStyle.commonPen.width() == 4
    assert w2.dispersionStyle.axesStyle.ticksColor.getColor().name() == '#884400'
    assert w2.absorptionStyle.legendStyle.textSize == 13
    assert w2.bandStructureStyle.weightFactor == 3.0
    assert w2.calculations.weightFactor == 3.0                     # the band structure uses it

    # The Appearance editor shows them
    editor = w2.spectra.inspector.styleWidget
    assert editor.dispersionStyleWidget.curveStyleWidget.lineWidthSpinBox.value() == 4
    assert editor.absorptionStyleWidget.legendStyleWidget.textSizeSpinBox.value() == 13
    assert editor.absorptionStyleWidget.pointStyleWidget.symbolSizeSpinBox.value() == 11
    assert editor.bandStructureStyleWidget.fillStyleWidget.weightFactorSpin.value() == 3.0
    w2.close()
