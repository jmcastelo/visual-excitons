"""The main window and its panels, on Qt's offscreen platform."""

import numpy as np
import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QFormLayout, QLabel, QTableWidgetItem

import visual_excitons.gui.main_window as main_window
from visual_excitons.gui.main_window import MainWindow, SYSTEM_PAGE, SPECTRA_PAGE, WAVEFUNCTION_PAGE
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


def test_navigation(window):
    for index in (SPECTRA_PAGE, WAVEFUNCTION_PAGE, SYSTEM_PAGE):
        window.navigation.buttons[index].click()
        assert window.stack.currentIndex() == index and window.pageActions[index].isChecked()
    window.pageActions[WAVEFUNCTION_PAGE].trigger()
    assert window.stack.currentIndex() == WAVEFUNCTION_PAGE
    assert window.navigation.buttons[WAVEFUNCTION_PAGE].isChecked()


def test_side_panel_toggle(window):
    window.inspectorAction.setChecked(False)
    assert window.spectraPage.inspector.isHidden() and window.wavefunctionPage.inspector.isHidden()
    window.inspectorAction.setChecked(True)
    assert not window.spectraPage.inspector.isHidden()


@pytest.mark.parametrize('mode, dark', [('Dark', True), ('Light', False)])
def test_theme(window, mode, dark):
    window.setTheme(mode)
    assert themeManager().isDark() == dark and window.themeActions[mode].isChecked()
    colors = PLOT_COLORS[dark]
    axes = window.dispersionStyle.axesStyle
    assert axes.backgroundColor.color == colors['background'] and axes.axesColor.color == colors['foreground']
    # Default-colored curves follow the theme
    assert window.dispersionStyle.curveStyle.commonPen.color() == colors['foreground']
    background = window.wavefunctionPage.excitonWfWidget.opts['bgcolor']
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

    parameters = window.wavefunctionPage.parameters3DWidget
    assert parameters.qPointSpinBox.value() == 5 and parameters.excitonIndexSpinBox.value() == 2
    assert '2.2284 eV' in parameters.excitonNote.text()
    spectra = window.spectraPage.inspector
    assert spectra.showWavefunctionButton.isEnabled() and 'Q-point 5' in spectra.selectedExcitonNote.text()
    assert 'exciton 2 at Q-point 5' in window.statusBar().currentMessage()

    # Changing the exciton by hand: the note no longer claims it is the selected one
    parameters.excitonIndexSpinBox.setValue(3)
    assert 'Click a bright exciton' in parameters.excitonNote.text()

    spectra.showWavefunctionButton.click()
    assert window.stack.currentIndex() == WAVEFUNCTION_PAGE


def test_compute_passes_the_chosen_exciton(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window.calculations, 'computeExcitonWaveFunction', lambda **kwargs: calls.append(kwargs))
    parameters = window.wavefunctionPage.parameters3DWidget
    window.options.numQPointsChanged.emit(10)
    parameters.qPointSpinBox.setValue(3)
    parameters.excitonIndexSpinBox.setValue(7)
    parameters.xSupercellSpinBox.setValue(3)
    parameters.wfCutoffSpinBox.setValue(5.0)
    parameters.computeWf()
    assert calls[0]['q_index'] == 2 and calls[0]['exc_index'] == 7 and calls[0]['supercell'] == [3, 1, 1]
    assert window.options.wfCutoff() == 5.0


def test_supercell_sizes_are_odd(window):
    parameters = window.wavefunctionPage.parameters3DWidget
    parameters.ySupercellSpinBox.setValue(4)
    assert parameters.ySupercellSpinBox.value() == 5 and window.options.supercell() == [1, 5, 1]


def test_display_rows_follow_the_plot_type(window):
    parameters = window.wavefunctionPage.parameters3DWidget
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
    assert window.options.gw and window.systemPage.calcTypeComboBox.currentText() == 'DFT+GW+BSE'
    assert window.systemPage.parameterLabels['a'].text() == '8.15801 Å'
    assert window.recentMenu.actions()[0].text() == 'BiI3_Bulk_8x8x8'
    # The lattice is drawn: atoms (one mesh per cell) and bonds
    assert window.wavefunctionPage.excitonWfWidget.latticeItems
    assert window.wavefunctionPage.excitonWfWidget.bondsItem is not None


@pytest.mark.data
def test_switching_datasets_resets_calculations(window):
    window.openDataset(main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8')))
    window.calculations.selectedExciton = (1, 1, 1.0)
    window.calculations.waveFunction = np.zeros((2, 2, 2))
    window.openDataset(main_window.findDataset(datasetPath('BN')))
    assert window.calculations.selectedExciton is None and window.calculations.waveFunction is None
    assert not window.options.gw and window.systemPage.calcTypeComboBox.currentText() == 'DFT+BSE'
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
    ring = window.spectraPage.dispersionWidget.highlight.item
    assert list(zip(*ring.getData())) == [(1.0, 2.1)] and ring.scene() is not None
    assert len(window.spectraPage.absorptionWidget.highlight.item.getData()[0]) == 0
    # Fake data, not to be replotted (e.g. by the theme reset at teardown)
    calc.dispPoints, calc.qIndices = [], None


def test_automatic_absorption_range_control(window, qtbot):
    inspector = window.spectraPage.inspector
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
    system = window.systemPage
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
    assert restored.systemPage.interpolationComboBox.currentIndex() == 1
    assert restored.systemPage.densitySpin.value() == 12.5
    assert restored.options.extraHighSymmetryPoints == {'M': [0.25, 0.25, 0.0]}
    assert restored.systemPage.hspTable.item(restored.systemPage.hspTable.rowCount() - 1, 0).text() == 'M'
    assert 'restored' in restored.statusBar().currentMessage()
    restored.close()


@pytest.mark.data
def test_invalid_saved_q_path_is_dropped(window):
    dataset = main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8'))
    dataset['qPath'] = {'ibrav': -5, 'path': 'NOPE', 'sampling': 'points', 'points': 100, 'density': 10.0, 'extraPoints': {}}
    window.openDataset(dataset)
    assert window.options.qBZ is None and 'qPath' not in window.recentDatasets()[0]
    assert window.systemPage.qPathLineEdit.text() == window.options.defaultPath
    assert 'could not be restored' in window.statusBar().currentMessage()


def test_image_export_dialog(window):
    from visual_excitons.gui.image_export import ImageExportDialog
    view = window.wavefunctionPage.excitonWfWidget
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
