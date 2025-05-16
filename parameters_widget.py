# This Python file uses the following encoding: utf-8
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QDoubleSpinBox, QHBoxLayout, QVBoxLayout, QGroupBox, QGridLayout, QSizePolicy


class ParametersWidget(QWidget):
    weightFactorChanged = Signal(float)
    absorptionParametersChanged = Signal()
    toggleStyleDialog = Signal(bool)

    def __init__(self, options):
        QWidget.__init__(self)

        # All options are contained in this object
        self.options = options

        # Dispersion widgets

        nExcitonsLabel = QLabel("Number of Excitons")

        self.nExcitonsLineEdit = QLineEdit()
        self.nExcitonsLineEdit.setValidator(QIntValidator())
        self.nExcitonsLineEdit.setText(str(self.options.nExcitons))
        self.nExcitonsLineEdit.editingFinished.connect(self.updateNExcitons)
        self.nExcitonsLineEdit.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.calculateDispersionButton = QPushButton("Compute Dispersion")
        self.calculateDispersionButton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        dispersionLayout = QGridLayout()
        dispersionLayout.addWidget(nExcitonsLabel, 0, 0)
        dispersionLayout.addWidget(self.nExcitonsLineEdit, 0, 1)
        dispersionLayout.addWidget(self.calculateDispersionButton, 1, 0, 1, 2)

        dispersionGroupBox = QGroupBox("Excitonic Dispersion")
        dispersionGroupBox.setLayout(dispersionLayout)

        # Absorption spectrum widgets

        energyMinLabel = QLabel("Minimum Energy (eV)")
        energyMaxLabel = QLabel("Maximum Energy (eV)")
        energyStepLabel = QLabel("Energy Step (eV)")

        self.energyMinLineEdit = QLineEdit()
        self.energyMinLineEdit.setValidator(QDoubleValidator())
        self.energyMinLineEdit.setText(f"{self.options.energyMin}")
        self.energyMinLineEdit.editingFinished.connect(self.updateEnergyMin)
        self.energyMinLineEdit.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.energyMaxLineEdit = QLineEdit()
        self.energyMaxLineEdit.setValidator(QDoubleValidator())
        self.energyMaxLineEdit.setText(f"{self.options.energyMax}")
        self.energyMaxLineEdit.editingFinished.connect(self.updateEnergyMax)
        self.energyMaxLineEdit.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.energyStepLineEdit = QLineEdit()
        self.energyStepLineEdit.setValidator(QDoubleValidator())
        self.energyStepLineEdit.setText(f"{self.options.energyStep}")
        self.energyStepLineEdit.editingFinished.connect(self.updateEnergyStep)
        self.energyStepLineEdit.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        absorptionGridLayout = QGridLayout()
        absorptionGridLayout.setAlignment(Qt.AlignTop)
        absorptionGridLayout.addWidget(energyMinLabel, 0, 0)
        absorptionGridLayout.addWidget(energyMaxLabel, 1, 0)
        absorptionGridLayout.addWidget(energyStepLabel, 2, 0)
        absorptionGridLayout.addWidget(self.energyMinLineEdit, 0, 1)
        absorptionGridLayout.addWidget(self.energyMaxLineEdit, 1, 1)
        absorptionGridLayout.addWidget(self.energyStepLineEdit, 2, 1)

        absorptionGroupBox = QGroupBox("Excitonic Absorption")
        absorptionGroupBox.setLayout(absorptionGridLayout)

        # Excitons widgets

        excMinIntensityLabel = QLabel("Minimum Intensity")

        self.excMinIntensityLineEdit = QLineEdit()
        self.excMinIntensityLineEdit.setValidator(QDoubleValidator())
        self.excMinIntensityLineEdit.setText(f"{self.options.excMinIntensity}")
        self.excMinIntensityLineEdit.editingFinished.connect(self.updateExcMinIntensity)
        self.excMinIntensityLineEdit.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.showLabelsButton = QPushButton("Show Labels")
        self.showLabelsButton.setCheckable(True)
        self.showLabelsButton.setChecked(False)
        self.showLabelsButton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        excitonsGridLayout = QGridLayout()
        excitonsGridLayout.setAlignment(Qt.AlignTop)
        excitonsGridLayout.addWidget(excMinIntensityLabel, 0, 0)
        excitonsGridLayout.addWidget(self.excMinIntensityLineEdit, 0, 1)
        excitonsGridLayout.addWidget(self.showLabelsButton, 2, 0, 1, 2)

        excitonsGroupBox = QGroupBox("Excitons")
        excitonsGroupBox.setLayout(excitonsGridLayout)

        # Style dialog widgets

        toggleDialogButton = QPushButton("Show Style Dialog")
        toggleDialogButton.setCheckable(True)
        toggleDialogButton.clicked.connect(self.toggleStyleDialog)
        toggleDialogButton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        styleLayout = QVBoxLayout()
        styleLayout.setAlignment(Qt.AlignTop)
        styleLayout.addWidget(toggleDialogButton)

        styleGroupBox = QGroupBox("Style")
        styleGroupBox.setLayout(styleLayout)

        # Main layout

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignTop)
        mainLayout.addWidget(dispersionGroupBox, 2, 0)
        mainLayout.addWidget(absorptionGroupBox, 2, 1)
        mainLayout.addWidget(excitonsGroupBox, 2, 2)
        mainLayout.addWidget(styleGroupBox, 2, 3)

        self.setLayout(mainLayout)

    @Slot()
    def updateNExcitons(self):
        self.options.setNExcitons(int(self.nExcitonsLineEdit.text()))
        self.nExcitonsLineEdit.setText(str(self.options.nExcitons))

    @Slot()
    def updateEnergyMin(self):
        self.options.setEnergyMin(float(self.energyMinLineEdit.text()))
        self.energyMinLineEdit.setText(f"{self.options.energyMin}")
        self.absorptionParametersChanged.emit()

    @Slot()
    def updateEnergyMax(self):
        self.options.setEnergyMax(float(self.energyMaxLineEdit.text()))
        self.energyMaxLineEdit.setText(f"{self.options.energyMax}")
        self.absorptionParametersChanged.emit()

    @Slot()
    def updateEnergyStep(self):
        self.options.setEnergyStep(float(self.energyStepLineEdit.text()))
        self.energyStepLineEdit.setText(f"{self.options.energyStep}")
        self.absorptionParametersChanged.emit()

    @Slot()
    def updateExcMinIntensity(self):
        self.options.setExcMinIntensity(float(self.excMinIntensityLineEdit.text()))
        self.excMinIntensityLineEdit.setText(f"{self.options.excMinIntensity}")
        self.absorptionParametersChanged.emit()
