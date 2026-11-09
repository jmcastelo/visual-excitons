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

    # The Appearance panel shows them
    panel = w2.appearancePanel
    panel.setGraph('dispersion')
    assert panel.lineWidthSpinBox.value() == 4
    assert panel.axesColorButtons['ticksColor'].color.name() == '#884400'
    panel.setGraph('absorption')
    assert panel.legendTextSizeSpinBox.value() == 13 and panel.symbolSizeSpinBox.value() == 11
    panel.setGraph('bands')
    assert panel.weightFactorSpinBox.value() == 3.0
    w2.close()


# The Appearance panel

@pytest.fixture
def panel(qtbot):
    from visual_excitons.gui.appearance_panel import AppearancePanel
    dispersion, absorption, bands = styles()
    widget = AppearancePanel({'dispersion': dispersion, 'absorption': absorption, 'bands': bands})
    qtbot.addWidget(widget)
    return widget


def test_panel_shows_the_sections_of_each_plot(panel):
    shown = lambda: {title for title, section in panel.sections.items() if not section.isHidden()}
    panel.setGraph('dispersion')
    assert shown() == {'Curves', 'Symbols', 'Axes'} and panel.graphTabs.currentIndex() == 0
    panel.setGraph('absorption')
    assert shown() == {'Curves', 'Symbols', 'Axes', 'Legend'}
    panel.setGraph('bands')
    assert shown() == {'Curves', 'Axes', 'Fill'} and panel.graphTabs.tabText(panel.graphTabs.currentIndex()) == 'Band structure'


def test_apply_to_all_or_one_curve(panel):
    dispersion = withCurves(panel.styles['dispersion'], 3)
    panel.setGraph('dispersion')
    panel.refresh()
    combo = panel.curveComboBox
    assert [combo.itemText(i) for i in range(combo.count())] == ['All curves', 'Curve 1', 'Curve 2', 'Curve 3']

    panel.lineWidthSpinBox.setValue(3)
    assert all(pen.width() == 3 for pen in dispersion.curveStyle.curvePens)
    combo.setCurrentIndex(2)
    combo.activated.emit(2)                                      # Curve 2
    assert not dispersion.applyToAllCurves() and dispersion.currentCurveIndex() == 1
    assert panel.curvesForm.isRowVisible(panel.gradientRow) is False
    panel.patternComboBox.setCurrentIndex(1)
    assert [pen.style() for pen in dispersion.curveStyle.curvePens] == [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine,
                                                                         Qt.PenStyle.SolidLine]

    # A curve clicked in a plot: chosen here, the panel on its plot
    panel.setGraph('absorption')
    dispersion.setApplyToAllCurves(True)
    dispersion.setCurrentCurveIndex(2)
    assert panel.graph == 'dispersion' and combo.currentIndex() == 3 and not dispersion.applyToAllCurves()


def test_same_axes_for_all_plots(panel):
    panel.setGraph('dispersion')
    panel.axesWidthSpinBox.setValue(3)
    assert panel.styles['dispersion'].axesStyle.axesWidth == 3 and panel.styles['bands'].axesStyle.axesWidth == 1
    panel.sameAxesCheckBox.setChecked(True)
    panel.axesWidthSpinBox.setValue(2)
    assert all(style.axesStyle.axesWidth == 2 for style in panel.styles.values())


def test_cancel_restores_the_style(panel):
    dispersion = withCurves(panel.styles['dispersion'], 3)
    dispersion.setApplyToAllCurves(False)
    for index, color in enumerate(('#aa0000', '#00aa00', '#0000aa')):
        dispersion.setCurrentCurveIndex(index)
        dispersion.curveStyle.setCurveColor(QColor(color))
    dispersion.setApplyToAllCurves(True)
    panel.setGraph('dispersion')
    panel.curveComboBox.activated.emit(0)                       # all curves
    colors = lambda: [pen.color().name() for pen in dispersion.curveStyle.curvePens]

    panel.lineColorButton.click()
    dialog = panel.colorDialog
    assert dialog.isVisible() and dialog.isModal()
    dialog.setCurrentColor(QColor('#ffcc00'))                   # live preview: all curves
    assert colors() == ['#ffcc00'] * 3
    dialog.reject()
    assert colors() == ['#aa0000', '#00aa00', '#0000aa']        # each curve back to its own color

    # OK keeps it
    panel.lineColorButton.click()
    dialog.setCurrentColor(QColor('#00cccc'))
    dialog.accept()
    assert colors() == ['#00cccc'] * 3
    panel.refresh()
    assert panel.lineColorButton.color.name() == '#00cccc'

    # The gradient too
    panel.startHueButton.click()
    dialog.setCurrentColor(QColor.fromHsv(120, 255, 255))
    assert colors() != ['#00cccc'] * 3
    dialog.reject()
    assert colors() == ['#00cccc'] * 3


def test_cancel_restores_legend_and_shared_axes(panel):
    absorption, bands = panel.styles['absorption'], panel.styles['bands']
    panel.setGraph('absorption')

    # A legend without background gets none again
    panel.legendBackgroundButton.click()
    panel.colorDialog.setCurrentColor(QColor('#336699'))
    assert absorption.legendStyle.backgroundColor is not None
    panel.colorDialog.reject()
    assert absorption.legendStyle.backgroundColor is None

    # Axes for all plots: all of them back to their own colors
    bands.axesStyle.titleColor.setColor(QColor('#123123'))
    panel.sameAxesCheckBox.setChecked(True)
    panel.axesColorButtons['titleColor'].click()
    panel.colorDialog.setCurrentColor(QColor('#ff00ff'))
    assert all(style.axesStyle.titleColor.getColor().name() == '#ff00ff' for style in panel.styles.values())
    panel.colorDialog.reject()
    assert absorption.axesStyle.titleColor.getColor().name() == '#000000'
    assert bands.axesStyle.titleColor.getColor().name() == '#123123'

    # Fonts too
    font = absorption.axesStyle.ticksFont.getFont()
    panel.axesFontButtons['ticksFont'].click()
    panel.fontDialog.setCurrentFont(QFont('Serif', 31))
    assert absorption.axesStyle.ticksFont.getFont().pointSize() == 31
    panel.fontDialog.reject()
    assert absorption.axesStyle.ticksFont.getFont().pointSize() == font.pointSize()
