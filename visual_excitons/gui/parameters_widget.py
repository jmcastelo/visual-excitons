from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QVBoxLayout, QSizePolicy

from .inspector import Inspector, formLayout, NoteLabel
from .style_widget import StyleWidget


class ParametersWidget(Inspector):
    """Inspector of the spectra page."""

    absorptionParametersChanged = Signal()
    # Asks the main window to switch to the wave-function page
    showWavefunctionRequested = Signal()

    def __init__(self, options, calculations, dispersionStyle, absorptionStyle, bandStructureStyle):
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

        form = formLayout()
        form.addRow('From:', self.energyMinSpinBox)
        form.addRow('To:', self.energyMaxSpinBox)
        form.addRow('Step:', self.energyStepSpinBox)
        form.addRow('Bright threshold:', self.excMinIntensitySpinBox)
        form.addRow(self.showLabelsCheckBox)
        self.addSection('Absorption', form)

        # Selected exciton, shared with the wave-function page

        self.selectedExcitonNote = NoteLabel()
        self.showWavefunctionButton = QPushButton('Wave function of this exciton')
        self.showWavefunctionButton.setToolTip('Go to the wave-function page with this exciton selected')
        self.showWavefunctionButton.clicked.connect(self.showWavefunctionRequested)

        layout = QVBoxLayout()
        layout.addWidget(self.selectedExcitonNote)
        layout.addWidget(self.showWavefunctionButton)
        self.addSection('Selected exciton', layout)

        self.calculations.excitonSelected.connect(self.onExcitonSelected)
        self.onExcitonSelected()

        # Appearance of the plots

        layout = QVBoxLayout()
        layout.addWidget(StyleWidget(dispersionStyle, absorptionStyle, bandStructureStyle))
        self.addSection('Appearance', layout, expanded=False)

        self.alignLabels()

    def _syncEnergies(self):
        """Show the energies as clamped by the options."""
        for spinBox, value in ((self.energyMinSpinBox, self.options.energyMin),
                               (self.energyMaxSpinBox, self.options.energyMax),
                               (self.energyStepSpinBox, self.options.energyStep)):
            spinBox.blockSignals(True)
            spinBox.setValue(value)
            spinBox.blockSignals(False)
        self.absorptionParametersChanged.emit()

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

    @Slot(float)
    def updateExcMinIntensity(self, value):
        self.options.setExcMinIntensity(value)
        self.absorptionParametersChanged.emit()

    @Slot()
    def onExcitonSelected(self, *args):
        selected = self.calculations.selectedExciton
        if selected is None:
            self.selectedExcitonNote.setText('Click a bright exciton in an absorption spectrum to select it.')
            self.showWavefunctionButton.setEnabled(False)
        else:
            qIndex, excIndex, energy = selected
            self.selectedExcitonNote.setText(f'Exciton {excIndex} at Q-point {qIndex + 1}, E = {energy:.4f} eV')
            self.showWavefunctionButton.setEnabled(True)
