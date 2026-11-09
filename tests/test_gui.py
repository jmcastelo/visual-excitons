"""The main window and its panels, on Qt's offscreen platform."""

import numpy as np
import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication, QFormLayout, QLabel, QTableWidgetItem, QCheckBox, QPushButton,
                               QSizePolicy)

import visual_excitons.gui.main_window as main_window
from visual_excitons.gui.main_window import MainWindow
from visual_excitons.gui.docking import PANELS, PRESETS, DEFAULT_PRESET
from visual_excitons.gui.inspector import CollapsibleSection, Inspector, formLayout
from visual_excitons.gui.theme import themeManager, PLOT_COLORS
from conftest import datasetPath


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    """Main window with no dataset and fresh settings."""
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    themeManager().setMode('System')


def test_starts_without_dataset(window):
    assert window.windowTitle() == 'Visual Excitons'
    assert window.datasetLabel.text() == 'No dataset'
    assert not window.recentMenu.isEnabled()


def openPanels(window):
    return {key for key, dock in window.panels.docks.items() if not dock.isClosed()}


def test_presets(window):
    assert set(window.panels.docks) == set(PANELS)
    # First run: everything but the analysis (off by default)
    assert openPanels(window) == set(PANELS) - {'analysis'}
    expected = {'System': {'system'},
                'Spectra': {'dispersion', 'absorption', 'bands', 'spectraControls'},
                'Wave function': {'wavefunction', 'wavefunctionControls'},
                'Overview': set(PANELS) - {'analysis'}}
    actions = {action.text(): action for action in window.layoutMenu.actions()}
    for name in PRESETS:
        actions[name].trigger()
        assert openPanels(window) == expected[name], name
    assert actions['Spectra'].shortcut().toString() == 'Ctrl+2'

    # With the analysis on, the presets that have it show it
    window.analysisCheckBox.setChecked(True)
    window.applyPreset('Wave function')
    assert openPanels(window) == {'wavefunction', 'analysis', 'wavefunctionControls'}
    window.applyPreset('Spectra')
    assert 'analysis' not in openPanels(window) and window.analysisCheckBox.isChecked()


def test_panels_open_and_close(window):
    actions = {action.text(): action for action in window.menuBar().findChildren(type(window.layoutMenu))
               if action.title() == '&Panels' for action in action.actions()}
    assert list(actions) == list(PANELS.values())
    actions['Dispersion'].trigger()
    assert window.panels.docks['dispersion'].isClosed()
    actions['Dispersion'].trigger()
    assert not window.panels.docks['dispersion'].isClosed()

    # The analysis panel and its checkbox follow each other
    window.analysisCheckBox.setChecked(True)
    assert window.panels.isShown('analysis')
    window.panels.docks['analysis'].toggleView(False)
    assert not window.analysisCheckBox.isChecked()


def test_layout_is_remembered(window, qtbot, monkeypatch):
    window.applyPreset('Spectra')
    window.panels.docks['bands'].toggleView(False)
    # A layout of my own
    monkeypatch.setattr(main_window.QInputDialog, 'getText', lambda *args: ('Mine', True))
    window.saveLayoutAs()
    assert 'Mine' in [action.text() for action in window.layoutMenu.actions()]
    window.applyPreset('Overview')
    window.close()

    again = MainWindow()
    qtbot.addWidget(again)
    assert openPanels(again) == set(PANELS) - {'analysis'}
    again.openLayout('Mine')
    assert openPanels(again) == {'dispersion', 'absorption', 'spectraControls'}

    # Not over a preset
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, 'warning', lambda *args: shown.append(args[2]))
    monkeypatch.setattr(main_window.QInputDialog, 'getText', lambda *args: ('Overview', True))
    again.saveLayoutAs()
    assert 'preset' in shown[0] and again.panels.layoutNames() == ['Mine']
    again.deleteLayout('Mine')
    assert again.panels.layoutNames() == []
    again.close()


def test_invalid_saved_layout_falls_back_to_the_default(qtbot, monkeypatch, tmp_path):
    settings = QSettings('VisualExcitons', 'VisualExcitons')
    settings.clear()
    settings.setValue('panels', b'not a layout')
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    w = MainWindow()
    qtbot.addWidget(w)
    assert openPanels(w) == {key for key, where, relativeTo in PRESETS[DEFAULT_PRESET]['steps']} - {'analysis'}


@pytest.mark.parametrize('mode, dark', [('Dark', True), ('Light', False)])
def test_theme(window, mode, dark):
    window.setTheme(mode)
    assert themeManager().isDark() == dark and window.themeActions[mode].isChecked()
    colors = PLOT_COLORS[dark]
    axes = window.dispersionStyle.axesStyle
    assert axes.backgroundColor.color == colors['background'] and axes.axesColor.color == colors['foreground']
    # Default-colored curves follow the theme
    assert window.dispersionStyle.curveStyle.commonPen.color() == colors['foreground']
    background = window.wavefunction.excitonWfWidget.opts['bgcolor']
    assert (background[0] < 0.5) == dark


def test_theme_is_remembered(window):
    window.setTheme('Dark')
    window.close()
    assert QSettings('VisualExcitons', 'VisualExcitons').value('theme') == 'Dark'


def test_exciton_selection_reaches_both_pages(window, qtbot):
    window.options.numQPointsChanged.emit(90)
    window.calculations.qIndices = list(range(90))
    window.calculations.selectedExciton = (4, 2, 2.2284)
    window.calculations.excitonSelected.emit(4, 2, 2.2284)

    parameters = window.wavefunction.parameters3DWidget
    assert parameters.qPointSpinBox.value() == 5 and parameters.excitonIndexSpinBox.value() == 2
    assert '2.2284 eV' in parameters.excitonNote.text()
    spectra = window.spectra.inspector
    assert spectra.computeWavefunctionButton.isEnabled() and 'Q-point 5' in spectra.selectedExcitonNote.text()
    assert 'exciton 2 at Q-point 5' in window.statusBar().currentMessage()

    # Changing the exciton by hand: the note no longer claims it is the selected one
    parameters.excitonIndexSpinBox.setValue(3)
    assert 'Click a bright exciton' in parameters.excitonNote.text()



def test_compute_the_selected_exciton_from_the_spectra(window, monkeypatch):
    """One click from an exciton in the spectra to its wave function, with the memory it needs shown."""
    import visual_excitons.gui.parameters_3d_widget as module
    p3, spectra, calc = window.wavefunction.parameters3DWidget, window.spectra.inspector, window.calculations
    estimates = []

    def estimate(qIndex, excIndex, cutoff, supercell, factor):
        estimates.append((qIndex, excIndex))
        return {'peak': 3 * 2 ** 30, 'wavefunctions': 2 ** 30, 'loaded': False, 'fftBox': (18, 18, 18),
                'supercell': [s + 1 - s % 2 for s in supercell], 'states': 2, 'blockSize': 128}
    monkeypatch.setattr(calc, 'estimateWaveFunction', estimate)
    monkeypatch.setattr(module, 'availableMemory', lambda: (16 * 2 ** 30, 8 * 2 ** 30))
    calls = []
    monkeypatch.setattr(calc, 'computeExcitonWaveFunction', lambda **kwargs: calls.append(kwargs))

    # Nothing selected: no button, no estimate
    p3.updateEstimate()
    assert not spectra.computeWavefunctionButton.isEnabled() and spectra.wfEstimateNote.isHidden()

    window.options.numQPointsChanged.emit(90)
    calc.selectedExciton = (4, 2, 2.2284)
    calc.excitonSelected.emit(4, 2, 2.2284)
    p3.ySupercellSpinBox.setValue(3)
    p3.updateEstimate()
    note = spectra.wfEstimateNote
    assert not note.isHidden() and not note.warning
    assert note.text().startswith('Memory: about 3.0 GB at peak; 8.0 GB available.')
    assert 'hole fixed, supercell 1 × 3 × 1, cutoff 10 Ry, 2 degenerate states' in note.text()

    # Another exciton set by hand in the wave function controls: the estimate is still of the selected one
    p3.excitonIndexSpinBox.setValue(5)
    estimates.clear()
    p3.updateEstimate()
    assert estimates == [(4, 5), (4, 2)]

    # Too much for the memory available: in orange
    monkeypatch.setattr(module, 'availableMemory', lambda: (16 * 2 ** 30, 2 * 2 ** 30))
    p3.updateEstimate()
    assert note.warning and note.text().startswith('⚠')

    # The button computes the selected exciton (not the one set by hand) and shows it
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: module.QMessageBox.StandardButton.Yes)
    window.panels.docks['wavefunction'].toggleView(False)
    spectra.computeWavefunctionButton.click()
    assert calls[-1]['q_index'] == 4 and calls[-1]['exc_index'] == 2 and calls[-1]['supercell'] == [1, 3, 1]
    assert p3.excitonIndexSpinBox.value() == 2
    assert window.panels.isShown('wavefunction') and window.panels.docks['wavefunction'].isCurrentTab()

    # Declined for lack of memory: nothing computed, the panels stay as they are
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: module.QMessageBox.StandardButton.No)
    window.panels.docks['wavefunction'].toggleView(False)
    spectra.computeWavefunctionButton.click()
    assert len(calls) == 1 and not window.panels.isShown('wavefunction')


def test_compute_passes_the_chosen_exciton(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window.calculations, 'computeExcitonWaveFunction', lambda **kwargs: calls.append(kwargs))
    parameters = window.wavefunction.parameters3DWidget
    window.options.numQPointsChanged.emit(10)
    parameters.qPointSpinBox.setValue(3)
    parameters.excitonIndexSpinBox.setValue(7)
    parameters.xSupercellSpinBox.setValue(3)
    parameters.wfCutoffSpinBox.setValue(5.0)
    parameters.computeWf()
    assert calls[0]['q_index'] == 2 and calls[0]['exc_index'] == 7 and calls[0]['supercell'] == [3, 1, 1]
    assert window.options.wfCutoff() == 5.0


def test_supercell_sizes_are_odd(window):
    parameters = window.wavefunction.parameters3DWidget
    parameters.ySupercellSpinBox.setValue(4)
    assert parameters.ySupercellSpinBox.value() == 5 and window.options.supercell() == [1, 5, 1]


def test_display_rows_follow_the_plot_type(window):
    parameters = window.wavefunction.parameters3DWidget
    for plotType in range(3):
        parameters.plotTypeComboBox.setCurrentIndex(plotType)
        for widget, plotTypes in parameters.plotTypeRows:
            assert parameters.plotFormLayout.isRowVisible(widget) == (plotType in plotTypes)


def test_errors_are_shown(window, monkeypatch):
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, 'critical', lambda parent, title, text: shown.append((title, text)))
    window.calculations.getExcitonDispersion()   # no Q-path yet
    assert shown and 'Q-path' in shown[0][1]
    assert QApplication.overrideCursor() is None and not window.taskWidget.isVisible()


# Inspector

def test_collapsible_section(qtbot):
    section = CollapsibleSection('Section', expanded=False)
    qtbot.addWidget(section)
    section.setContentLayout(formLayout())
    assert section.content.isHidden() and section.header.arrowType() == Qt.ArrowType.RightArrow
    with qtbot.waitSignal(section.toggled) as blocker:
        section.header.click()
    assert blocker.args == [True] and not section.content.isHidden()
    assert section.header.arrowType() == Qt.ArrowType.DownArrow


def test_inspector_aligns_labels(qtbot):
    inspector = Inspector()
    qtbot.addWidget(inspector)
    for labels in (['A:', 'Much longer label:'], ['B:']):
        form = formLayout()
        for text in labels:
            form.addRow(text, QLabel('value'))
        inspector.addSection(labels[0], form)
    inspector.alignLabels()
    widths = {label.minimumWidth() for section in inspector.sections.values()
              for label in section.content.findChildren(QLabel) if label.text().endswith(':')}
    assert len(widths) == 1


# With a real dataset

@pytest.mark.data
def test_open_dataset(window):
    folder = datasetPath('BiI3_Bulk_8x8x8')
    window.openDataset(main_window.findDataset(folder))
    assert window.windowTitle() == 'BiI3_Bulk_8x8x8 — Visual Excitons'
    assert 'RHL1' in window.datasetLabel.text() and '90 Q-points' in window.datasetLabel.text()
    assert window.options.gw and window.system.calcTypeComboBox.currentText() == 'DFT+GW+BSE'
    assert window.system.parameterLabels['a'].text() == '8.15801 Å'
    assert window.recentMenu.actions()[0].text() == 'BiI3_Bulk_8x8x8'
    # The lattice is drawn: atoms (one mesh per cell) and bonds
    assert window.wavefunction.excitonWfWidget.latticeItems
    assert window.wavefunction.excitonWfWidget.bondsItem is not None


@pytest.mark.data
def test_switching_datasets_resets_calculations(window):
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    window.calculations.selectedExciton = (1, 1, 1.0)
    window.calculations.waveFunction = np.zeros((2, 2, 2))
    window.openDataset(main_window.findDataset(datasetPath('BN')))
    assert window.calculations.selectedExciton is None and window.calculations.waveFunction is None
    assert not window.options.gw and window.system.calcTypeComboBox.currentText() == 'DFT+BSE'
    assert [action.text() for action in window.recentMenu.actions()] == ['BN', 'BiI3_Bulk_8x8x8']


def test_status_bar_shows_and_cancels_a_running_task(window, qtbot):
    import threading, time
    started = threading.Event()

    def compute(context):
        started.set()
        context.stage('Crunching', 1000)
        for _ in range(1000):
            context.advance()
            time.sleep(0.01)

    tasks = window.calculations.tasks
    tasks.submit('Computing something…', compute, lambda result: None)
    tasks.submit('Computing more…', lambda context: None, lambda result: None)
    assert started.wait(5)
    qtbot.waitUntil(lambda: window.taskProgressBar.maximum() == 1000, timeout=5000)
    assert not window.taskWidget.isHidden()
    assert window.taskLabel.text() == 'Computing something — Crunching  (+1 queued)'
    assert QApplication.overrideCursor().shape() == Qt.CursorShape.BusyCursor

    with qtbot.waitSignal(window.calculations.busyChanged, timeout=5000, check_params_cb=lambda busy: not busy):
        window.cancelButton.click()
    assert window.taskWidget.isHidden() and QApplication.overrideCursor() is None
    assert window.statusBar().currentMessage() == 'Cancelled: computing something'


def test_selection_is_highlighted(window):
    calc = window.calculations
    calc.qIndices = [4, 9]
    calc.dispPoints = [[[0, 2.0], [1, 2.1]]]
    calc.selectedExciton = (9, 1, 2.1)
    calc.excitonSelected.emit(9, 1, 2.1)
    ring = window.spectra.dispersionWidget.highlight.item
    assert list(zip(*ring.getData())) == [(1.0, 2.1)] and ring.scene() is not None
    assert len(window.spectra.absorptionWidget.highlight.item.getData()[0]) == 0
    # Fake data, not to be replotted (e.g. by the theme reset at teardown)
    calc.dispPoints, calc.qIndices = [], None


def test_automatic_absorption_range_control(window, qtbot):
    inspector = window.spectra.inspector
    assert inspector.autoRangeCheckBox.isChecked() and not inspector.energyMinSpinBox.isEnabled()
    with qtbot.waitSignal(inspector.absorptionParametersChanged):
        inspector.autoRangeCheckBox.setChecked(False)
    assert not window.options.absorptionAutoRange and inspector.energyMaxSpinBox.isEnabled()

    inspector.autoRangeCheckBox.setChecked(True)
    window.calculations.excAbsData = [{'q': 0, 'range': (1.5, 3.0)}, {'q': 1, 'range': (1.6, 3.2)}]
    inspector.updateRangeNote()
    assert inspector.rangeNote.text() == 'Spectra from 1.5 to 3.2 eV.' and not inspector.rangeNote.isHidden()
    window.calculations.excAbsData = []


@pytest.mark.data
def test_q_path_is_remembered_per_dataset(window, qtbot, monkeypatch, tmp_path):
    folder = datasetPath('BiI3_Bulk_8x8x8')
    window.openDataset(main_window.findDataset(folder))
    system = window.system
    assert window.options.qBZ is None          # nothing saved yet: no path set

    # An extra point, a path through it and density sampling
    row = system.hspTable.rowCount()
    system.hspTable.insertRow(row)
    for column, text in enumerate(['M', '0.25', '0.25', '0.0']):
        system.hspTable.setItem(row, column, QTableWidgetItem(text))
    system.qPathLineEdit.setText('LGZFM')
    system.interpolationComboBox.setCurrentIndex(1)
    system.densitySpin.setValue(12.5)
    assert system.setBrillouinZone()
    window.close()

    # Next session: a new window opens the same dataset (the most recent one)
    restored = MainWindow()
    qtbot.addWidget(restored)
    assert restored.options.saveDir == str(folder / 'save')
    assert restored.options.getPathString() == 'LGZFM'
    assert restored.system.interpolationComboBox.currentIndex() == 1
    assert restored.system.densitySpin.value() == 12.5
    assert restored.options.extraHighSymmetryPoints == {'M': [0.25, 0.25, 0.0]}
    assert restored.system.hspTable.item(restored.system.hspTable.rowCount() - 1, 0).text() == 'M'
    assert 'restored' in restored.statusBar().currentMessage()
    restored.close()


@pytest.mark.data
def test_invalid_saved_q_path_is_dropped(window):
    dataset = main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8'))
    dataset['qPath'] = {'ibrav': -5, 'path': 'NOPE', 'sampling': 'points', 'points': 100, 'density': 10.0, 'extraPoints': {}}
    window.openDataset(dataset)
    assert window.options.qBZ is None and 'qPath' not in window.recentDatasets()[0]
    assert window.system.qPathLineEdit.text() == window.options.defaultPath
    assert 'could not be restored' in window.statusBar().currentMessage()


def test_image_export_dialog(window):
    from visual_excitons.gui.image_export import ImageExportDialog
    view = window.wavefunction.excitonWfWidget
    view.resize(400, 300)
    dialog = ImageExportDialog(view, window)
    dialog.scaleComboBox.setCurrentIndex(2)                 # 3x
    assert dialog.imageSize() == (1200, 900) and not dialog.widthSpinBox.isEnabled()
    dialog.scaleComboBox.setCurrentIndex(len(dialog.SCALES))  # custom: width free, height keeps the proportions
    dialog.widthSpinBox.setValue(1000)
    assert dialog.imageSize() == (1000, 750)
    dialog.transparentCheckBox.setChecked(True)
    dialog.accept()

    again = ImageExportDialog(view, window)
    assert again.imageSize() == (1000, 750) and again.transparentCheckBox.isChecked()


def test_export_density_from_the_window(window, qtbot, monkeypatch, tmp_path):
    calc = window.calculations
    assert not window.exportDensityAction.isEnabled()

    class Lattice:
        lat = np.eye(3) * 8.0
        atomic_numbers = [6]
        car_atomic_positions = np.zeros((1, 3))
    calc.lattice = Lattice()
    calc.waveFunction = np.random.default_rng(0).random((4, 4, 4))
    calc.wfSupercell, calc.wfFixedParticle, calc.wfFixedPosition, calc.wfExciton = [1, 1, 1], 'e', [0, 0, 0], (0, 3)
    calc.wfGrid = [4, 4, 4]
    calc.wfComputed.emit()
    assert window.exportDensityAction.isEnabled()
    assert window.exportBaseName().endswith('_Q1_exciton3')

    target = tmp_path / 'density'
    monkeypatch.setattr(main_window.QFileDialog, 'getSaveFileName',
                        lambda *args, **kwargs: (str(target), 'XCrySDen XSF (*.xsf)'))
    with qtbot.waitSignal(calc.densityExported, timeout=10000) as blocker:
        window.exportDensityAction.trigger()
    assert blocker.args == [str(target) + '.xsf'] and (tmp_path / 'density.xsf').stat().st_size > 0
    assert 'saved' in window.statusBar().currentMessage()
    assert QSettings('VisualExcitons', 'VisualExcitons').value('exportDir') == str(tmp_path)
    calc.waveFunction = None


def test_colormap_choice(window, qtbot):
    p3 = window.wavefunction.parameters3DWidget
    view = window.wavefunction.excitonWfWidget
    with qtbot.waitSignal(p3.colormapChanged):
        p3.colormapComboBox.setCurrentText('Inferno')
    from visual_excitons.gui.colormaps import makeColormap
    np.testing.assert_allclose(view.colormap.getLookupTable(nPts=16), makeColormap('Inferno').getLookupTable(nPts=16))
    p3.reverseColormapCheckBox.setChecked(True)
    np.testing.assert_allclose(view.colormap.getLookupTable(nPts=16), makeColormap('Inferno', True).getLookupTable(nPts=16))
    # Separators are not colormaps
    assert '' in [p3.colormapComboBox.itemText(i) for i in range(p3.colormapComboBox.count())]
    values = p3.persistence.values('global')
    assert values['colormap'] == 'Inferno' and values['colormapReversed'] is True


def test_side_panels_fit_their_content(window):
    for inspector in (window.spectra.inspector, window.wavefunction.inspector):
        for section in inspector.sections.values():
            assert inspector.minimumWidth() >= section.content.minimumSizeHint().width()
        # Buttons as wide as their text, not stretched to the panel
        buttons = inspector.body.findChildren(QPushButton)
        assert buttons
        for button in buttons:
            assert not button.sizePolicy().horizontalPolicy().value & QSizePolicy.PolicyFlag.GrowFlag.value, button.text()


def fakeWaveFunction(calc, sigma):
    """A Gaussian density around the fixed hole, on a 3 x 3 x 3 supercell of a cubic cell."""
    from visual_excitons.core.analysis import gridPositions

    class Lattice:
        lat = np.eye(3) * 6.0
        atomic_numbers = [83]
        car_atomic_positions = np.array([[3.0, 3.0, 3.0]])
    calc.lattice = Lattice()
    calc.wfSupercell, calc.wfFixedParticle, calc.wfFixedPosition = [3, 3, 3], 'h', [0.5, 0.5, 0.5]
    shape = (36, 36, 36)
    voxels = Lattice.lat * 3 / 36
    center = Lattice.lat.T @ (np.array([0.5, 0.5, 0.5]) + 1)
    r2 = np.sum((gridPositions(shape, voxels) - center) ** 2, axis=-1)
    calc.waveFunction = np.exp(-r2 / (2 * sigma ** 2))
    calc.wfGrid, calc.wfExciton = [12, 12, 12], (0, 1)
    calc.tr4x4 = np.eye(4)
    calc.tr4x4[:3, :3] = voxels.T


def test_analysis_panel(window, qtbot):
    page = window.wavefunction
    p3, analysis, calc = page.parameters3DWidget, page.analysisWidget, window.calculations
    assert not window.panels.isShown('analysis')
    p3.showAnalysisCheckBox.setChecked(True)
    assert window.panels.isShown('analysis') and 'Compute a wave function' in analysis.statistics.text()

    fakeWaveFunction(calc, sigma=2.0)
    calc.wfComputed.emit()
    result = page.radialResult
    assert result['mean'] == pytest.approx(2.0 * np.sqrt(8 / np.pi), rel=0.03)
    assert 'Distance of the electron from the hole' in analysis.statistics.text()
    assert analysis.warning.isHidden()
    # The cut through the hole, and the plane in 3D (a square: normal z in a cubic supercell)
    assert np.isfinite(analysis.image.image).any()
    assert len(page.excitonWfWidget.cutPlaneItems) == 2
    assert len(analysis.atomsItem.data) > 0            # the Bi atoms of the plane z = 9 Bohr

    # Without the plane in 3D
    p3.showPlaneCheckBox.setChecked(False)
    assert page.excitonWfWidget.cutPlaneItems == []

    # Invalid normal: reported, nothing breaks
    for edit in p3.planeNormalLineEdits:
        edit.setText('0')
    p3.onPlaneNormalEdited()
    assert 'non-zero' in p3.planeStatusLabel.text() and not p3.planeStatusLabel.isHidden()

    # Perpendicular to the view: the normal points to the viewer
    page.excitonWfWidget.setViewDirection([0, 0, -1])
    p3.planeFromViewRequested.emit()
    assert [e.text() for e in p3.planeNormalLineEdits] == ['0.0000', '0.0000', '1.0000']
    assert p3.planeBasisComboBox.currentText() == 'Cartesian' and p3.planeUpHint is not None
    assert p3.planeStatusLabel.isHidden()

    # A wide exciton in this small supercell: flagged
    fakeWaveFunction(calc, sigma=12.0)
    calc.wfComputed.emit()
    assert not analysis.warning.isHidden() and 'larger supercell' in analysis.warning.text()

    # A new dataset clears the analysis
    page.onDatasetChanged(False)
    assert page.radialResult is None and page.excitonWfWidget.cutPlaneItems == []
    calc.waveFunction = None
    p3.showAnalysisCheckBox.setChecked(False)
    assert not window.panels.isShown('analysis')


def test_resolution_controls(window, qtbot, monkeypatch):
    p3, page, calc = window.wavefunction.parameters3DWidget, window.wavefunction, window.calculations
    calls = []
    monkeypatch.setattr(calc, 'computeExcitonWaveFunction', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(p3, 'estimate', lambda: None)       # no dataset: no estimate
    p3.fullCutoffCheckBox.setChecked(True)
    assert not p3.wfCutoffSpinBox.isEnabled()
    p3.computeWf()
    assert calls[-1]['cutoff_ry'] == -1 and calls[-1]['block_size'] == 256
    p3.fullCutoffCheckBox.setChecked(False)
    p3.wfCutoffSpinBox.setValue(12.0)
    p3.computeWf()
    assert calls[-1]['cutoff_ry'] == 12.0

    # Smoothing: the display gets the upsampled density, on a scaled transform
    fakeWaveFunction(calc, sigma=2.0)
    p3.smoothingComboBox.setCurrentIndex(1)
    density, transform = page.displayDensity()
    assert density.shape == tuple(2 * n - 1 for n in calc.waveFunction.shape)
    np.testing.assert_allclose(np.array(transform)[:3, :3], calc.tr4x4[:3, :3] / 2)
    p3.smoothingComboBox.setCurrentIndex(0)
    assert page.displayDensity()[0] is calc.waveFunction
    calc.waveFunction = None


def test_memory_warning(window, monkeypatch):
    p3, calc = window.wavefunction.parameters3DWidget, window.calculations
    import visual_excitons.gui.parameters_3d_widget as module
    estimate = {'peak': 12 * 2 ** 30, 'wavefunctions': 2 ** 30, 'loaded': False, 'fftBox': (46, 46, 46),
                'supercell': [3, 3, 3], 'states': 7, 'blockSize': 64}
    monkeypatch.setattr(p3, 'estimate', lambda: estimate)
    monkeypatch.setattr(module, 'availableMemory', lambda: (16 * 2 ** 30, 8 * 2 ** 30))

    p3.updateEstimate()
    assert p3.estimateWarning and p3.estimateNote.text().startswith('⚠')
    assert '138 × 138 × 138 in the supercell, 7 degenerate states' in p3.estimateNote.text()

    calls, answers = [], []
    monkeypatch.setattr(calc, 'computeExcitonWaveFunction', lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: answers.append(args[1]) or module.QMessageBox.StandardButton.No)
    p3.computeWf()
    assert answers == ['Not enough memory?'] and calls == []           # declined: not computed
    monkeypatch.setattr(module.QMessageBox, 'warning', lambda *args: module.QMessageBox.StandardButton.Yes)
    p3.computeWf()
    assert len(calls) == 1 and calls[0]['block_size'] == 64             # the block chosen for the memory

    estimate['peak'] = 2 * 2 ** 30                                        # fits: no question, no warning
    p3.updateEstimate()
    assert not p3.estimateWarning


def test_display_is_prepared_in_the_background_and_only_the_latest_shown(window, qtbot):
    """Heavy plots (smoothing, many levels) do not block the window; outdated results are not shown."""
    page, p3, calc = window.wavefunction, window.wavefunction.parameters3DWidget, window.calculations
    view = page.excitonWfWidget
    fakeWaveFunction(calc, sigma=2.0)
    p3.plotTypeComboBox.setCurrentIndex(1)        # isosurface set
    p3.smoothingComboBox.setCurrentIndex(0)
    calc.wfComputed.emit()                        # 36^3 x 10 levels: inline
    assert not calc.isBusy() and view.wfMeshItemSet is not None
    small = len(view.wfIsoFacesSet)

    # Smoothing 3x: upsampled in the background
    p3.smoothingComboBox.setCurrentIndex(2)
    assert calc.isBusy()
    # Back to none before it finishes: the 3x result must not replace it
    p3.smoothingComboBox.setCurrentIndex(0)
    qtbot.waitUntil(lambda: not calc.isBusy(), timeout=20000)
    qtbot.wait(50)
    assert len(view.wfIsoFacesSet) == small

    p3.smoothingComboBox.setCurrentIndex(1)
    qtbot.waitUntil(lambda: not calc.isBusy(), timeout=20000)
    qtbot.wait(50)
    assert len(view.wfIsoFacesSet) > 2 * small
    p3.smoothingComboBox.setCurrentIndex(0)
    calc.waveFunction = None


def test_structure_toggles_apply_to_items_drawn_later(window):
    """Hidden parts stay hidden when the lattice is redrawn (dataset, supercell, sizes...)."""
    view = window.wavefunction.excitonWfWidget
    p3 = window.wavefunction.parameters3DWidget
    boxes = {box.text(): box for box in p3.findChildren(QCheckBox)}
    for name in ('Atoms', 'Bonds', 'Cell boundaries'):
        boxes[name].setChecked(False)

    lattice = np.eye(3) * 6.0
    view.clearLatticeItems()
    view.clearLatticeBoundaryItems()
    view.plotUnitCellBoundaries(lattice, np.zeros(3))
    view.plotUnitCellAtoms([6], np.zeros((1, 3)), np.zeros(3))
    view.plotBonds(np.zeros((1, 3)), np.ones((1, 3)), [6], 0.2)
    assert not any(item.visible() for item in view.latticeBoundaryItems)
    assert not any(item.visible() for item in view.latticeItems)
    assert not view.bondsItem.visible()

    boxes['Cell boundaries'].setChecked(True)
    assert all(item.visible() for item in view.latticeBoundaryItems)
    view.plotUnitCellBoundaries(lattice, np.ones(3))
    assert all(item.visible() for item in view.latticeBoundaryItems)
    for name in ('Atoms', 'Bonds'):
        boxes[name].setChecked(True)


@pytest.mark.data
def test_hidden_boundaries_stay_hidden_after_a_restart(window, qtbot):
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    p3 = window.wavefunction.parameters3DWidget
    next(box for box in p3.findChildren(QCheckBox) if box.text() == 'Cell boundaries').setChecked(False)
    window.close()

    restarted = MainWindow()
    qtbot.addWidget(restarted)
    view = restarted.wavefunction.excitonWfWidget
    assert view.latticeBoundaryItems and not any(item.visible() for item in view.latticeBoundaryItems)
    box = next(b for b in restarted.wavefunction.parameters3DWidget.findChildren(QCheckBox)
               if b.text() == 'Cell boundaries')
    assert not box.isChecked()
    restarted.wavefunction.parameters3DWidget.setSupercell([3, 1, 1])   # redrawn: still hidden
    assert len(view.latticeBoundaryItems) == 3 and not any(item.visible() for item in view.latticeBoundaryItems)
    box.setChecked(True)
    restarted.close()
