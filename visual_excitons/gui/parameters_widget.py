from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QVBoxLayout, QSizePolicy, QComboBox,
                               QHBoxLayout, QWidget)

from .inspector import Inspector, formLayout, NoteLabel
from .persistence import DATASET


class ParametersWidget(Inspector):
    """Inspector of the spectra page."""

    absorptionParametersChanged = Signal()
    # Asks the main window to switch to the wave-function page
    computeWavefunctionRequested = Signal()
    # Asks the main window to export the plots as a publication figure
    exportFigureRequested = Signal()

    def __init__(self, options, calculations):
        Inspector.__init__(self)

        # All options are contained in this object
        self.options = options
        self.calculations = calculations

        # Dispersion

        self.nExcitonsSpinBox = QSpinBox(minimum=1, maximum=999)
        self.nExcitonsSpinBox.setValue(self.options.nExcitons)
        self.nExcitonsSpinBox.setToolTip('Number of lowest-energy excitons whose dispersion is computed')
        self.nExcitonsSpinBox.valueChanged.connect(self.options.setNExcitons)
        self.nExcitonsSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self.calculateDispersionButton = QPushButton('Compute dispersion')

        form = formLayout()
        form.addRow('Excitons:', self.nExcitonsSpinBox)
        form.addRow(self.calculateDispersionButton)
        form.addRow(NoteLabel('Click a point of the dispersion to show the absorption spectrum at its Q-point; '
                              'Ctrl-click to keep several spectra.'))
        # E.g. only some Q-points computed: what the dispersion shows
        self.dispersionNote = NoteLabel()
        self.dispersionNote.hide()
        form.addRow(self.dispersionNote)
        self.calculations.dispersionNoteChanged.connect(self.setDispersionNote)
        self.addSection('Dispersion', form)

        # Absorption

        def energySpinBox(value):
            spinBox = QDoubleSpinBox(minimum=0.0, maximum=1000.0, singleStep=0.1, decimals=3, suffix=' eV')
            spinBox.setValue(value)
            # Recompute when editing is finished or an arrow is clicked, not on every key
            spinBox.setKeyboardTracking(False)
            spinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            return spinBox

        self.energyMinSpinBox = energySpinBox(self.options.energyMin)
        self.energyMaxSpinBox = energySpinBox(self.options.energyMax)
        self.energyStepSpinBox = energySpinBox(self.options.energyStep)
        self.energyStepSpinBox.setSingleStep(0.005)
        self.energyStepSpinBox.setMinimum(0.001)

        self.autoRangeCheckBox = QCheckBox('Automatic range')
        self.autoRangeCheckBox.setChecked(self.options.absorptionAutoRange)
        self.autoRangeCheckBox.setToolTip('Each spectrum spans its excitons, plus a margin of five broadenings\n'
                                          '(0.5 eV) on both sides. Untick to set the range by hand.')
        self.autoRangeCheckBox.toggled.connect(self.setAutoRange)
        self.rangeNote = NoteLabel()
        self.rangeNote.hide()

        self.energyMinSpinBox.valueChanged.connect(self.updateEnergyMin)
        self.energyMaxSpinBox.valueChanged.connect(self.updateEnergyMax)
        self.energyStepSpinBox.valueChanged.connect(self.updateEnergyStep)

        self.excMinIntensitySpinBox = QDoubleSpinBox(minimum=0.0, maximum=1.0, singleStep=0.05, decimals=3)
        self.excMinIntensitySpinBox.setValue(self.options.excMinIntensity)
        self.excMinIntensitySpinBox.setKeyboardTracking(False)
        self.excMinIntensitySpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.excMinIntensitySpinBox.setToolTip('Excitons with at least this intensity (relative to the brightest)\n'
                                               'are marked as bright on the spectrum; the rest are dark')
        self.excMinIntensitySpinBox.valueChanged.connect(self.updateExcMinIntensity)

        self.showLabelsCheckBox = QCheckBox('Label bright excitons')
        self.showLabelsCheckBox.setToolTip('Show (index, intensity) next to each bright exciton')

        # The spectrum at any computed Q-point, on the path or not
        self.qPointComboBox = QComboBox()
        self.qPointComboBox.setToolTip('The computed Q-points (the files ndb.BS_diago_Q<n>)')
        self.qPointComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.addSpectrumButton = QPushButton('Add spectrum')
        self.addSpectrumButton.setToolTip('Show the absorption spectrum at this Q-point, with those shown')
        self.addSpectrumButton.clicked.connect(
            lambda: self.qPointComboBox.count() and self.calculations.showQPointAbsorption(self.qPointComboBox.currentData()))
        qPointRow = QHBoxLayout()
        qPointRow.setContentsMargins(0, 0, 0, 0)
        qPointRow.addWidget(self.qPointComboBox)
        qPointRow.addWidget(self.addSpectrumButton)
        qPointRow.addStretch(1)
        qPointWidget = QWidget()
        qPointWidget.setLayout(qPointRow)
        self.options.qPointsChanged.connect(self.setQPoints)
        self.addSpectrumButton.setEnabled(False)

        form = formLayout()
        form.addRow('Q-point:', qPointWidget)
        form.addRow(self.autoRangeCheckBox)
        form.addRow('From:', self.energyMinSpinBox)
        form.addRow('To:', self.energyMaxSpinBox)
        form.addRow('Step:', self.energyStepSpinBox)
        form.addRow(self.rangeNote)
        form.addRow('Bright threshold:', self.excMinIntensitySpinBox)
        form.addRow(self.showLabelsCheckBox)
        self.addSection('Absorption', form)

        # Selected exciton, shared with the wave function controls: its wave
        # function in one click, with the memory it needs

        self.selectedExcitonNote = NoteLabel()
        self.computeWavefunctionButton = QPushButton('Compute its wave function')
        self.computeWavefunctionButton.setToolTip('Compute the wave function of this exciton with the settings of the\n'
                                                  'Wave function controls, and show it')
        self.computeWavefunctionButton.clicked.connect(self.computeWavefunctionRequested)
        self.wfEstimateNote = NoteLabel()
        self.wfEstimateNote.hide()

        layout = QVBoxLayout()
        layout.addWidget(self.selectedExcitonNote)
        layout.addWidget(self.computeWavefunctionButton)
        layout.addWidget(self.wfEstimateNote)
        self.addSection('Selected exciton', layout)

        self.calculations.excitonSelected.connect(self.onExcitonSelected)
        self.calculations.excitonAbsorptionReady.connect(self.updateRangeNote)
        self.setAutoRange(self.autoRangeCheckBox.isChecked(), recompute=False)
        self.onExcitonSelected()

        # Publication figures with Matplotlib
        exportButton = QPushButton('Export figure…')
        exportButton.setToolTip('The plots as a publication figure (PDF, SVG, PNG...) or a Python script\n'
                                'that recreates it with Matplotlib (Ctrl+Shift+F)')
        exportButton.clicked.connect(self.exportFigureRequested)
        layout = QVBoxLayout()
        layout.addWidget(exportButton)
        layout.addWidget(NoteLabel('Any of the three plots, alone or combined, with the colors and styles of the '
                                    'Appearance panel.'))
        self.addSection('Export', layout, expanded=False)

        self.alignLabels()

        # Kept between sessions: the spectra settings with the dataset (they
        # depend on its energies), the labels as a preference
        for key, widget in (('excitons', self.nExcitonsSpinBox), ('autoRange', self.autoRangeCheckBox),
                            ('brightThreshold', self.excMinIntensitySpinBox)):
            self.remember(key, widget, DATASET)
        # The range as a whole: set one bound at a time, it would be clamped by the old other one
        self.remember('energyRange', scope=DATASET,
                      get=lambda: [self.options.energyMin, self.options.energyMax, self.options.energyStep],
                      set=lambda values: self.setEnergyRange(*values))
        self.remember('labels', self.showLabelsCheckBox)

    def _syncEnergies(self):
        """Show the energies as clamped by the options."""
        for spinBox, value in ((self.energyMinSpinBox, self.options.energyMin),
                               (self.energyMaxSpinBox, self.options.energyMax),
                               (self.energyStepSpinBox, self.options.energyStep)):
            spinBox.blockSignals(True)
            spinBox.setValue(value)
            spinBox.blockSignals(False)
        self.absorptionParametersChanged.emit()

    def setEnergyRange(self, energyMin, energyMax, energyStep):
        """Set the whole manual range at once, if it is valid."""
        energyMin, energyMax, energyStep = float(energyMin), float(energyMax), float(energyStep)
        if not (0.0 <= energyMin < energyMax and 0.0 < energyStep <= energyMax - energyMin):
            raise ValueError('invalid energy range')
        self.options.energyMin, self.options.energyMax, self.options.energyStep = energyMin, energyMax, energyStep
        self._syncEnergies()

    @Slot(float)
    def updateEnergyMin(self, value):
        self.options.setEnergyMin(value)
        self._syncEnergies()

    @Slot(float)
    def updateEnergyMax(self, value):
        self.options.setEnergyMax(value)
        self._syncEnergies()

    @Slot(float)
    def updateEnergyStep(self, value):
        self.options.setEnergyStep(value)
        self._syncEnergies()

    @Slot(bool)
    def setAutoRange(self, auto: bool, recompute: bool = True):
        self.options.setAbsorptionAutoRange(auto)
        self.energyMinSpinBox.setEnabled(not auto)
        self.energyMaxSpinBox.setEnabled(not auto)
        self.updateRangeNote()
        if recompute:
            self.absorptionParametersChanged.emit()

    @Slot()
    def updateRangeNote(self, *args):
        """With the automatic range, show the range of the spectra plotted."""
        ranges = [data['range'] for data in self.calculations.excAbsData if 'range' in data]
        if self.options.absorptionAutoRange and ranges:
            low, high = min(r[0] for r in ranges), max(r[1] for r in ranges)
            self.rangeNote.setText(f'Spectra from {low:.1f} to {high:.1f} eV.')
            self.rangeNote.show()
        else:
            self.rangeNote.hide()

    @Slot(float)
    def updateExcMinIntensity(self, value):
        self.options.setExcMinIntensity(value)
        self.absorptionParametersChanged.emit()

    @Slot(str, bool)
    def setWaveFunctionEstimate(self, text: str, warning: bool):
        """The memory of computing the selected exciton (from the wave function controls)."""
        self.wfEstimateNote.setText(text)
        self.wfEstimateNote.setWarning(warning)
        self.wfEstimateNote.setVisible(bool(text) and self.calculations.selectedExciton is not None)

    @Slot(str)
    def setDispersionNote(self, text):
        self.dispersionNote.setText(text)
        self.dispersionNote.setVisible(bool(text))

    @Slot(list)
    def setQPoints(self, qPoints):
        """The computed Q-points to choose a spectrum from (indices from 0)."""
        current = self.qPointComboBox.currentData()
        self.qPointComboBox.clear()
        for q in qPoints:
            self.qPointComboBox.addItem(f'Q{q + 1}', q)
        if current in qPoints:
            self.qPointComboBox.setCurrentIndex(qPoints.index(current))
        self.addSpectrumButton.setEnabled(bool(qPoints))

    @Slot()
    def onExcitonSelected(self, *args):
        selected = self.calculations.selectedExciton
        if selected is None:
            self.selectedExcitonNote.setText('Click a bright exciton in an absorption spectrum to select it.')
            self.computeWavefunctionButton.setEnabled(False)
        else:
            qIndex, excIndex, energy = selected
            self.selectedExcitonNote.setText(f'Exciton {excIndex} at Q-point {qIndex + 1}, E = {energy:.4f} eV')
            self.computeWavefunctionButton.setEnabled(True)
