"""Parameters kept between sessions."""

import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QSplitter, QLabel

import visual_excitons.gui.main_window as main_window
from visual_excitons.gui.main_window import MainWindow
from visual_excitons.gui.inspector import ValueSlider, CollapsibleSection
from visual_excitons.gui.persistence import PersistentState, StateRegistry, GLOBAL, DATASET
from conftest import datasetPath


def test_widget_values_round_trip(qtbot):
    combo = QComboBox()
    combo.addItems(['a', 'b', 'c'])
    splitter = QSplitter()
    splitter.addWidget(QLabel('left'))
    splitter.addWidget(QLabel('right'))
    widgets = {
        'check': QCheckBox(), 'combo': combo, 'spin': QSpinBox(maximum=100), 'double': QDoubleSpinBox(maximum=10),
        'line': QLineEdit(), 'slider': ValueSlider(0, 1000, 0, str), 'section': CollapsibleSection('S', expanded=True),
        'splitter': splitter,
    }
    for widget in widgets.values():
        qtbot.addWidget(widget)
    splitter.resize(300, 100)

    state = PersistentState()
    for key, widget in widgets.items():
        state.remember(key, widget)
    custom = {'value': [1, 2]}
    state.remember('custom', scope=DATASET, get=lambda: custom['value'], set=lambda v: custom.update(value=v))

    widgets['check'].setChecked(True)
    combo.setCurrentText('c')
    widgets['spin'].setValue(42)
    widgets['double'].setValue(2.5)
    widgets['line'].setText('hello')
    widgets['slider'].slider.setValue(333)
    widgets['section'].setExpanded(False)
    splitter.setSizes([250, 50])
    saved = state.values(GLOBAL)
    assert 'custom' not in saved and state.values(DATASET) == {'custom': [1, 2]}

    # Change everything, then restore
    widgets['check'].setChecked(False)
    combo.setCurrentText('a')
    widgets['spin'].setValue(0)
    widgets['double'].setValue(0)
    widgets['line'].clear()
    widgets['slider'].slider.setValue(0)
    widgets['section'].setExpanded(True)
    splitter.setSizes([50, 250])
    hooks = []
    state.afterRestore.append(hooks.append)
    state.restore(GLOBAL, saved)
    assert state.values(GLOBAL) == saved and hooks == [GLOBAL]
    assert splitter.sizes()[0] > splitter.sizes()[1]

    state.restore(DATASET, {'custom': [3]})
    assert custom['value'] == [3]


def test_invalid_and_unknown_values_are_ignored(qtbot):
    spin, combo = QSpinBox(maximum=10), QComboBox()
    combo.addItems(['x', 'y'])
    state = PersistentState()
    state.remember('spin', spin)
    state.remember('combo', combo)
    spin.setValue(5)
    state.restore(GLOBAL, {'spin': 'not a number', 'combo': 'missing item', 'other': 1})
    assert spin.value() == 5 and combo.currentText() == 'x'


def test_registry_prefixes():
    a, b = PersistentState(), PersistentState()
    values = {'a': 1, 'b': 2}
    a.remember('x', get=lambda: values['a'], set=lambda v: values.update(a=v))
    b.remember('x', get=lambda: values['b'], set=lambda v: values.update(b=v))
    registry = StateRegistry()
    registry.add('first', a)
    registry.add('second', b)
    assert registry.values(GLOBAL) == {'first/x': 1, 'second/x': 2}
    registry.restore(GLOBAL, {'first/x': 10, 'second/x': 20})
    assert values == {'a': 10, 'b': 20}
    registry.restore(GLOBAL, 'garbage')   # ignored


# Main window across sessions

@pytest.fixture
def newWindow(qtbot, monkeypatch, tmp_path):
    """Factory of main windows sharing the same settings (one per 'session')."""
    QSettings('VisualExcitons', 'VisualExcitons').clear()
    monkeypatch.setattr(main_window, 'DEFAULT_DATASET_FOLDER', tmp_path / 'missing')
    windows = []

    def make():
        w = MainWindow()
        qtbot.addWidget(w)
        windows.append(w)
        return w
    yield make
    from visual_excitons.gui.theme import themeManager
    themeManager().setMode('System')


def test_preferences_are_resumed(newWindow):
    w = newWindow()
    p3 = w.wavefunction.parameters3DWidget
    p3.plotTypeComboBox.setCurrentText('Volumetric')
    p3.persistence  # noqa: B018
    sliders = [widget for widget, types in p3.plotTypeRows if isinstance(widget, ValueSlider)]
    sliders[0].slider.setValue(700)                     # iso level
    p3.reverseViewCheckBox.setChecked(False)
    p3.viewPresetComboBox.setCurrentText('z')
    p3.onViewPresetActivated(p3.viewPresetComboBox.currentIndex())
    p3.viewUpLineEdits[1].setText('1')
    p3.sections['Structure'].setExpanded(True)
    p3.sections['Display'].setExpanded(False)
    orthographic = next(box for box in p3.findChildren(QCheckBox) if box.text() == 'Orthographic projection')
    orthographic.setChecked(False)
    bonds = next(box for box in p3.findChildren(QCheckBox) if box.text() == 'Bonds')
    bonds.setChecked(False)
    reciprocal = next(box for box in p3.findChildren(QCheckBox) if box.text() == 'Reciprocal a*, b*, c*')
    reciprocal.setChecked(True)
    w.spectra.inspector.showLabelsCheckBox.setChecked(True)
    w.close()

    # Next session
    w2 = newWindow()
    q3 = w2.wavefunction.parameters3DWidget
    assert q3.plotTypeComboBox.currentText() == 'Volumetric'
    assert w2.wavefunction.excitonWfWidget is not None and w2.options.isoLevel() == pytest.approx(0.7)
    assert not q3.reverseViewCheckBox.isChecked() and q3.viewPresetComboBox.currentText() == 'z'
    assert [e.text() for e in q3.viewDirLineEdits] == ['0', '0', '1'] and q3.viewUpLineEdits[1].text() == '1'
    assert q3.sections['Structure'].isExpanded() and not q3.sections['Display'].isExpanded()
    # The restored values are in effect, not only shown
    assert not w2.wavefunction.excitonWfWidget.orthographic
    assert not w2.wavefunction.excitonWfWidget.bondsVisible
    assert w2.wavefunction.excitonWfWidget.gizmo.showReciprocal
    assert w2.calculations.showExcitonLabels
    assert w2.wavefunction.excitonWfWidget.opts['rotation'] is not None


@pytest.mark.data
def test_dataset_parameters_are_resumed_per_dataset(newWindow):
    bii3 = main_window.findDataset(datasetPath('BiI3_Bulk_8x8x8'))
    bn = main_window.findDataset(datasetPath('BN'))

    w = newWindow()
    w.openDataset(bii3)
    spectra, p3 = w.spectra.inspector, w.wavefunction.parameters3DWidget
    spectra.nExcitonsSpinBox.setValue(10)
    spectra.autoRangeCheckBox.setChecked(False)
    spectra.energyMinSpinBox.setValue(1.0)
    spectra.energyMaxSpinBox.setValue(3.5)
    spectra.excMinIntensitySpinBox.setValue(0.25)
    p3.qPointSpinBox.setValue(5)
    p3.excitonIndexSpinBox.setValue(3)
    for edit, value in zip((p3.xParticlePosLineEdit, p3.yParticlePosLineEdit, p3.zParticlePosLineEdit), ('0.5', '0.25', '0')):
        edit.setText(value)
    p3.particlePositionChanged()                       # hole at (0.5, 0.25, 0)
    p3.particleTypeComboBox.setCurrentText('Electron')
    p3.setSupercell([3, 1, 3])
    p3.wfCutoffSpinBox.setValue(20.0)

    # Another dataset starts from the defaults
    w.openDataset(bn)
    assert w.options.supercell() == [1, 1, 1] and p3.particleTypeComboBox.currentText() == 'Hole'
    assert spectra.autoRangeCheckBox.isChecked() and spectra.nExcitonsSpinBox.value() == 6
    p3.setSupercell([5, 5, 1])

    # Back to BiI3: its parameters are back, BN keeps its own
    w.openDataset(bii3)
    assert w.options.supercell() == [3, 1, 3] and w.options.wfCutoff() == 20.0
    assert w.options.nExcitons == 10 and not w.options.absorptionAutoRange and w.options.energyMax == 3.5
    assert w.options.energyMin == 1.0 and w.options.excMinIntensity == 0.25
    assert spectra.energyMaxSpinBox.value() == 3.5
    assert (p3.qPointSpinBox.value(), p3.excitonIndexSpinBox.value()) == (5, 3)
    assert p3.particleTypeComboBox.currentText() == 'Electron' and w.options.holePos == [0.5, 0.25, 0.0]
    w.close()

    # Next session: the last dataset, BiI3, with its parameters
    w2 = newWindow()
    assert w2.options.saveDir == bii3['save'] and w2.options.supercell() == [3, 1, 3]
    assert w2.wavefunction.parameters3DWidget.particleTypeComboBox.currentText() == 'Electron'
    assert w2.options.particleType() == 'e' and w2.options.holePos == [0.5, 0.25, 0.0]
    assert (w2.options.energyMin, w2.options.energyMax) == (1.0, 3.5)
    # Through Open dataset as well, BN gets its own parameters back
    w2.openDataset(main_window.findDataset(datasetPath('BN')))
    assert w2.options.supercell() == [5, 5, 1]


def test_energy_range_is_restored_whole(newWindow):
    """A saved range above the current one is not clamped by the current maximum."""
    w = newWindow()
    spectra = w.spectra.inspector
    spectra.setEnergyRange(1.0, 3.0, 0.01)
    spectra.persistence.restore(DATASET, {'energyRange': [5.0, 10.0, 0.05]})
    assert (w.options.energyMin, w.options.energyMax, w.options.energyStep) == (5.0, 10.0, 0.05)
    assert (spectra.energyMinSpinBox.value(), spectra.energyMaxSpinBox.value()) == (5.0, 10.0)
    spectra.persistence.restore(DATASET, {'energyRange': [10.0, 5.0, 0.05]})   # invalid: ignored
    assert (w.options.energyMin, w.options.energyMax) == (5.0, 10.0)
