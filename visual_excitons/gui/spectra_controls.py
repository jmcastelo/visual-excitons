from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import (QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QVBoxLayout, QSizePolicy, QComboBox,
                               QHBoxLayout, QWidget, QLabel)

from .inspector import Inspector, formLayout, NoteLabel
from .persistence import DATASET



# The setting summing degenerate states, as explained in both its checkboxes
DEGENERATE_TIP = ('Sum the states degenerate with the exciton (within 10 meV): in its wave function, its\n'
        'composition and its band structure. A single state of a degenerate group is an arbitrary\n'
        'mixture of them, without the symmetry of the crystal')

# The energy window summed with the selected exciton
WINDOW_TIP = ('Also sum every state within this energy of the exciton (in its wave function, particle\n'
              'density, composition and band structure): an absorption peak made of many close states,\n'
              'as the C and D peaks of transition-metal dichalcogenides. Select the bright exciton at the\n'
              'top of the peak; the window is shaded on the absorption spectra')
WEIGHTINGS = (('By oscillator strength', 'oscillator'), ('Equally', 'equal'))


class SpectraControls(Inspector):
    """Inspector of the spectra page."""

    absorptionParametersChanged = Signal()
    # Asks the main window to switch to the wave-function page
    computeWavefunctionRequested = Signal()
    showCompositionRequested = Signal()
    # Asks the main window to export the plots as a publication figure
    exportFigureRequested = Signal()

    def __init__(self, dataset, parameters, calculations):
        """The controls of the spectra of `dataset`, setting `parameters` (a core.parameters.SpectraParameters)."""
        Inspector.__init__(self)

        self.dataset = dataset
        self.parameters = parameters
        self.calculations = calculations

        # Dispersion

        self.nExcitonsSpinBox = QSpinBox(minimum=1, maximum=999)
        self.nExcitonsSpinBox.setValue(self.parameters.nExcitons)
        self.nExcitonsSpinBox.setToolTip('Number of lowest-energy excitons whose dispersion is computed')
        self.nExcitonsSpinBox.valueChanged.connect(lambda n: setattr(self.parameters, 'nExcitons', n))
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

        self.energyMinSpinBox = energySpinBox(self.parameters.energyMin)
        self.energyMaxSpinBox = energySpinBox(self.parameters.energyMax)
        self.energyStepSpinBox = energySpinBox(self.parameters.energyStep)
        self.energyStepSpinBox.setSingleStep(0.005)
        self.energyStepSpinBox.setMinimum(0.001)

        self.autoRangeCheckBox = QCheckBox('Automatic range')
        self.autoRangeCheckBox.setChecked(self.parameters.absorptionAutoRange)
        self.autoRangeCheckBox.setToolTip('Each spectrum spans its excitons, plus a margin of five broadenings\n'
                                          '(0.5 eV) on both sides. Untick to set the range by hand.')
        self.autoRangeCheckBox.toggled.connect(self.setAutoRange)
        self.rangeNote = NoteLabel()
        self.rangeNote.hide()

        self.energyMinSpinBox.valueChanged.connect(self.updateEnergyMin)
        self.energyMaxSpinBox.valueChanged.connect(self.updateEnergyMax)
        self.energyStepSpinBox.valueChanged.connect(self.updateEnergyStep)

        self.excMinIntensitySpinBox = QDoubleSpinBox(minimum=0.0, maximum=1.0, singleStep=0.05, decimals=3)
        self.excMinIntensitySpinBox.setValue(self.parameters.excMinIntensity)
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
        self.dataset.qPointsChanged.connect(self.setQPoints)
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
        # Its symmetry and spin, once analysed (in the Composition panel)
        self.characterSummary = NoteLabel()
        self.characterSummary.hide()
        # Shared by everything about the selected exciton (Calculations.sumDegenerate); a
        # copy in the Wave function controls' Exciton section, linked to it
        self.sumDegenerateCheckBox = QCheckBox('Sum degenerate states')
        self.sumDegenerateCheckBox.setChecked(self.calculations.sumDegenerate)
        self.sumDegenerateCheckBox.setToolTip(DEGENERATE_TIP)
        self.sumDegenerateCheckBox.toggled.connect(self.calculations.setSumDegenerate)
        self.calculations.sumDegenerateChanged.connect(self.sumDegenerateCheckBox.setChecked)
        # An energy window around it (Calculations.energyWindow), and how its states are weighted
        self.windowCheckBox = QCheckBox('Sum an energy window:')
        self.windowCheckBox.setToolTip(WINDOW_TIP)
        self.windowSpinBox = QDoubleSpinBox(minimum=1.0, maximum=1000.0, singleStep=5.0, decimals=0, value=25.0,
                                            prefix='±', suffix=' meV')
        self.windowSpinBox.setToolTip(WINDOW_TIP)
        self.weightingComboBox = QComboBox()
        for label, weighting in WEIGHTINGS:
            self.weightingComboBox.addItem(label, weighting)
        self.weightingComboBox.setToolTip('How the states of the window add up: by their oscillator strength, as in\n'
                                          'the absorption peak (equally where none is bright, e.g. at finite Q),\n'
                                          'or all the same')
        self.windowCheckBox.toggled.connect(self.applyWindow)
        self.windowSpinBox.valueChanged.connect(self.applyWindow)
        self.weightingComboBox.currentIndexChanged.connect(
            lambda: self.calculations.setWindowWeighting(self.weightingComboBox.currentData()))
        windowRow = QHBoxLayout()
        windowRow.setContentsMargins(0, 0, 0, 0)
        windowRow.addWidget(self.windowCheckBox)
        windowRow.addWidget(self.windowSpinBox)
        windowRow.addStretch(1)
        weightingRow = QHBoxLayout()
        weightingRow.setContentsMargins(0, 0, 0, 0)
        weightingRow.addWidget(QLabel('Weights:'))
        weightingRow.addWidget(self.weightingComboBox)
        weightingRow.addStretch(1)
        self.applyWindow()
        self.computeWavefunctionButton = QPushButton('Compute its wave function')
        self.computeWavefunctionButton.setToolTip('Compute the wave function of this exciton with the settings of the\n'
                                                  'Wave function controls, and show it')
        self.computeWavefunctionButton.clicked.connect(self.computeWavefunctionRequested)
        self.wfEstimateNote = NoteLabel()
        self.wfEstimateNote.hide()
        self.showCompositionButton = QPushButton('Show its composition')
        self.showCompositionButton.setToolTip('Where this exciton lives in reciprocal space and what it is made of\n'
                                              '(bands, k-points), in the Composition panel')
        self.showCompositionButton.clicked.connect(self.showCompositionRequested)

        layout = QVBoxLayout()
        layout.addWidget(self.selectedExcitonNote)
        layout.addWidget(self.characterSummary)
        layout.addWidget(self.sumDegenerateCheckBox)
        layout.addLayout(windowRow)
        layout.addLayout(weightingRow)
        layout.addWidget(self.showCompositionButton)
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
                            ('brightThreshold', self.excMinIntensitySpinBox),
                            ('sumDegenerate', self.sumDegenerateCheckBox), ('energyWindow', self.windowCheckBox),
                            ('energyWindowWidth', self.windowSpinBox), ('windowWeighting', self.weightingComboBox)):
            self.remember(key, widget, DATASET)
        # The range as a whole: set one bound at a time, it would be clamped by the old other one
        self.remember('energyRange', scope=DATASET,
                      get=lambda: [self.parameters.energyMin, self.parameters.energyMax, self.parameters.energyStep],
                      set=lambda values: self.setEnergyRange(*values))
        self.remember('labels', self.showLabelsCheckBox)

    @Slot()
    def applyWindow(self, *args):
        """The energy window as set: its width (eV) when ticked, 0 otherwise."""
        on = self.windowCheckBox.isChecked()
        self.windowSpinBox.setEnabled(on)
        self.weightingComboBox.setEnabled(on)
        self.calculations.setEnergyWindow(self.windowSpinBox.value() / 1000.0 if on else 0.0)

    def _syncEnergies(self):
        """Show the energies as clamped by the parameters."""
        for spinBox, value in ((self.energyMinSpinBox, self.parameters.energyMin),
                               (self.energyMaxSpinBox, self.parameters.energyMax),
                               (self.energyStepSpinBox, self.parameters.energyStep)):
            spinBox.blockSignals(True)
            spinBox.setValue(value)
            spinBox.blockSignals(False)
        self.absorptionParametersChanged.emit()

    def setEnergyRange(self, energyMin, energyMax, energyStep):
        """Set the whole manual range at once, if it is valid."""
        energyMin, energyMax, energyStep = float(energyMin), float(energyMax), float(energyStep)
        if not (0.0 <= energyMin < energyMax and 0.0 < energyStep <= energyMax - energyMin):
            raise ValueError('invalid energy range')
        self.parameters.energyMin, self.parameters.energyMax, self.parameters.energyStep = energyMin, energyMax, energyStep
        self._syncEnergies()

    @Slot(float)
    def updateEnergyMin(self, value):
        self.parameters.setEnergyMin(value)
        self._syncEnergies()

    @Slot(float)
    def updateEnergyMax(self, value):
        self.parameters.setEnergyMax(value)
        self._syncEnergies()

    @Slot(float)
    def updateEnergyStep(self, value):
        self.parameters.setEnergyStep(value)
        self._syncEnergies()

    @Slot(bool)
    def setAutoRange(self, auto: bool, recompute: bool = True):
        self.parameters.absorptionAutoRange = auto
        self.energyMinSpinBox.setEnabled(not auto)
        self.energyMaxSpinBox.setEnabled(not auto)
        self.updateRangeNote()
        if recompute:
            self.absorptionParametersChanged.emit()

    @Slot()
    def updateRangeNote(self, *args):
        """With the automatic range, show the range of the spectra plotted."""
        ranges = [data['range'] for data in self.calculations.excAbsData if 'range' in data]
        if self.parameters.absorptionAutoRange and ranges:
            low, high = min(r[0] for r in ranges), max(r[1] for r in ranges)
            self.rangeNote.setText(f'Spectra from {low:.1f} to {high:.1f} eV.')
            self.rangeNote.show()
        else:
            self.rangeNote.hide()

    @Slot(float)
    def updateExcMinIntensity(self, value):
        self.parameters.excMinIntensity = value
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
