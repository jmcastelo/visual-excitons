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
    panel.patternComboBox.activated.emit(1)                     # as a user choosing it
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


def test_gradient_keeps_its_direction_and_colors(qapp):
    from visual_excitons.core.style import GRADIENT
    style = withCurves(DispersionStyle(), 3)
    style.curveStyle.setGradientColors(QColor('#0000ff'), QColor('#ffff00'))
    names = lambda: [pen.color().name() for pen in style.curveStyle.curvePens]
    assert names()[0] == '#0000ff' and names()[-1] == '#ffff00' and style.curveStyle.colorMode == GRADIENT
    style.curveStyle.setGradientColors(QColor('#ffff00'), QColor('#0000ff'))
    assert names()[0] == '#ffff00' and names()[-1] == '#0000ff'                  # reversed, not sorted
    # Saturation and brightness of the colors chosen, not only their hue
    style.curveStyle.setGradientColors(QColor('#400000'), QColor('#004000'))
    assert QColor(names()[0]).value() < 80 and QColor(names()[-1]).value() < 80
    # Kept in the state, and read from the older one (hues only)
    restored = withCurves(DispersionStyle(), 3)
    restored.setState(style.state(), curves=True)
    assert restored.curveStyle.startColor.name() == '#400000' and restored.curveStyle.colorMode == GRADIENT
    old = style.state()
    del old['curve']['gradientColors'], old['curve']['colorMode']
    restored.setState(old)
    assert restored.curveStyle.startColor.hsvHue() == style.curveStyle.startHue


def test_new_spectra_follow_the_colors_chosen(qapp):
    from visual_excitons.core.style import paletteColor
    style = AbsorptionStyle()
    style.appendCurveStyle(4)
    style.appendCurveStyle(9)
    colors = lambda: [pen.color().name() for pen in style.curveStyle.curvePens]
    assert colors() == [paletteColor(4).name(), paletteColor(9).name()]         # a color per Q-point
    style.curveStyle.setCurveWidth(3)
    style.curveStyle.setCurveColor(QColor('#008800'))                            # one color for all
    style.pointStyle.setPointSize(11)
    style.appendCurveStyle(2)
    assert colors() == ['#008800'] * 3 and style.curveStyle.curvePens[-1].width() == 3
    assert style.pointStyle.pointSizes[-1] == 11
    style.curveStyle.setGradientColors(QColor('#0000ff'), QColor('#ff0000'))
    style.appendCurveStyle(5)                                                    # the gradient spread again
    assert colors()[0] == '#0000ff' and colors()[-1] == '#ff0000' and len(set(colors())) == 4
    style.curveStyle.setPaletteColors()
    assert colors() == [paletteColor(q).name() for q in (4, 9, 2, 5)]
    style.removeCurveStyle(1)
    style.appendCurveStyle(9)
    assert colors()[-1] == paletteColor(9).name()                                # Q-point 9's color again


def test_panel_dialogs_and_points(qtbot):
    from PySide6.QtWidgets import QColorDialog, QFontDialog
    from visual_excitons.gui.appearance_panel import AppearancePanel
    dispersion, absorption, bands = styles()
    panel = AppearancePanel({'dispersion': dispersion, 'absorption': absorption, 'bands': bands})
    qtbot.addWidget(panel)
    # Qt's own dialogs: native ones may not report the color live
    assert panel.colorDialog.testOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
    assert panel.fontDialog.testOption(QFontDialog.FontDialogOption.DontUseNativeDialog)
    # The value chosen applies on OK even without a live preview
    withCurves(dispersion, 2)
    panel.setGraph('dispersion')
    panel.lineColorButton.click()
    with blockedSignals(panel.colorDialog):
        panel.colorDialog.setCurrentColor(QColor('#123456'))
    panel.colorDialog.accept()
    assert [pen.color().name() for pen in dispersion.curveStyle.curvePens] == ['#123456'] * 2
    # The swatch shows the colors in use
    panel.setGraph('absorption')
    absorption.appendCurveStyle(0)
    absorption.appendCurveStyle(1)
    panel.refresh()
    assert len(panel.lineColorButton.colors) == 2


def blockedSignals(widget):
    from visual_excitons.gui.appearance_panel import blocked
    return blocked(widget)


def test_points_drawn_in_the_color_of_their_curve(qtbot):
    import pyqtgraph as pg
    from visual_excitons.gui.dispersion_plot import DispersionPlot
    from visual_excitons.core.calculations import PointData
    style = withCurves(DispersionStyle(), 2)
    style.curveStyle.setCurveColor(QColor('#aa0000'))
    plot = DispersionPlot(style)
    qtbot.addWidget(plot)
    points = [[[0.0, 2.0], [1.0, 2.1]], [[0.0, 2.3], [1.0, 2.4]]]
    plot.plotData(points, [[PointData(i, j + 1) for i in range(2)] for j in range(2)], [], [])
    scatter = [item for item in plot.getPlotItem().items if isinstance(item, pg.ScatterPlotItem) and item.data.size]
    assert scatter and all(item.opts['brush'].color().name() == '#aa0000' for item in scatter[:2])


def test_lines_are_an_option_of_each_plot(panel):
    from visual_excitons.core.figures import buildFigure
    dispersion, absorption, bands = panel.styles['dispersion'], panel.styles['absorption'], panel.styles['bands']
    panel.setGraph('absorption')
    assert panel.linesCheckBox.isChecked()
    panel.linesCheckBox.setChecked(False)
    assert not absorption.showLines and dispersion.showLines and bands.showLines     # this plot only
    panel.setGraph('dispersion')
    assert panel.linesCheckBox.isChecked()                                           # each plot its own
    restored = AbsorptionStyle()
    restored.setState(absorption.state())
    assert not restored.showLines                                                    # kept with the style

    # Figures: without lines, the spectra are not drawn, their points carry the legend
    from test_figures import sampleData, STYLES
    styles = {**STYLES, 'absorption': {**STYLES['absorption'], 'lines': False}}
    ax = buildFigure(sampleData(), styles, {'panels': ['absorption'], 'excitonBars': False}).axes[0]
    assert all(line.get_linestyle() == 'None' for line in ax.lines if line.get_label().startswith('Q-point'))
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ['Q-point 1', 'Q-point 5']


def test_same_shape_for_all_again(panel):
    dispersion = withCurves(panel.styles['dispersion'], 3)
    panel.setGraph('dispersion')
    panel.refresh()
    assert panel.symbolComboBox.currentText() == 'Circle'
    panel.varySymbolsButton.click()
    panel.refresh()
    assert len(set(dispersion.pointStyle.pointSymbols)) == 3
    assert panel.symbolComboBox.currentIndex() == -1                    # "Different per curve"
    # Choosing a shape, even the one shown before, gives it to all
    panel.symbolComboBox.setCurrentIndex(0)
    panel.symbolComboBox.activated.emit(0)
    assert dispersion.pointStyle.pointSymbols == ['o'] * 3
    panel.refresh()
    assert panel.symbolComboBox.currentText() == 'Circle'

    # Patterns likewise
    dispersion.setApplyToAllCurves(False)
    dispersion.setCurrentCurveIndex(1)
    dispersion.curveStyle.setCurveStyle(1)
    dispersion.setApplyToAllCurves(True)
    panel.curveComboBox.activated.emit(0)
    assert panel.patternComboBox.currentIndex() == -1
    panel.patternComboBox.activated.emit(0)
    assert {pen.style() for pen in dispersion.curveStyle.curvePens} == {Qt.PenStyle.SolidLine}
