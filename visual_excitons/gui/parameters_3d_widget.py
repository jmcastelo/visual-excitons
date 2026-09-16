from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QWidget, QPushButton, QSizePolicy, QVBoxLayout, QSpinBox, QLineEdit, QFormLayout
from PySide6.QtWidgets import QSlider, QComboBox, QHBoxLayout, QGroupBox

from visual_excitons.core.calculations import Calculations
from visual_excitons.core.options import Options

class Parameters3DWidget(QWidget):
    plotTypeChanged = Signal(int)
    signalReplotLattice = Signal()
    fixedParticlePosChanged = Signal()
    isoLevelChanged = Signal()
    numIsoLevelsChanged = Signal()
    sliceDensityChanged = Signal()
    opacityChanged = Signal(float)
    centerViewClicked = Signal()

    def __init__(self, options: Options, calculations: Calculations):
        QWidget.__init__(self)

        self.options = options
        self.calculations = calculations

        # Calculation parameters

        # Exciton index selector

        self.excitonIndexSpinBox = QSpinBox(minimum=1, maximum=10)
        self.excitonIndexSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.excitonIndexSpinBox.setValue(1)

        # Particle type selector

        self.particleTypeComboBox = QComboBox()
        self.particleTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.particleTypeComboBox.addItems(['Hole', 'Electron'])
        self.particleTypeComboBox.currentIndexChanged.connect(self.updateParticlePositionWidgets)

        # Particle position widgets

        self.xParticlePosLineEdit = QLineEdit()
        self.xParticlePosLineEdit.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.xParticlePosLineEdit.setValidator(QDoubleValidator(0.0, 1.0, 4))
        self.xParticlePosLineEdit.editingFinished.connect(self.particlePositionChanged)

        self.yParticlePosLineEdit = QLineEdit()
        self.yParticlePosLineEdit.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.yParticlePosLineEdit.setValidator(QDoubleValidator(0.0, 1.0, 4))
        self.yParticlePosLineEdit.editingFinished.connect(self.particlePositionChanged)

        self.zParticlePosLineEdit = QLineEdit()
        self.zParticlePosLineEdit.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.zParticlePosLineEdit.setValidator(QDoubleValidator(0.0, 1.0, 4))
        self.zParticlePosLineEdit.editingFinished.connect(self.particlePositionChanged)

        self.updateParticlePositionWidgets(self.particleTypeComboBox.currentIndex())

        particleLayout = QHBoxLayout()
        particleLayout.addWidget(self.xParticlePosLineEdit)
        particleLayout.addWidget(self.yParticlePosLineEdit)
        particleLayout.addWidget(self.zParticlePosLineEdit)

        # Supercell widgets

        self.xSupercellSpinBox = QSpinBox(minimum=1, maximum=999)
        self.xSupercellSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.xSupercellSpinBox.setValue(1)
        self.xSupercellSpinBox.valueChanged.connect(self.supercellChanged)

        self.ySupercellSpinBox = QSpinBox(minimum=1, maximum=999)
        self.ySupercellSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.ySupercellSpinBox.setValue(1)
        self.ySupercellSpinBox.valueChanged.connect(self.supercellChanged)

        self.zSupercellSpinBox = QSpinBox(minimum=1, maximum=999)
        self.zSupercellSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.zSupercellSpinBox.setValue(1)
        self.zSupercellSpinBox.valueChanged.connect(self.supercellChanged)

        supercellLayout = QHBoxLayout()
        supercellLayout.addWidget(self.xSupercellSpinBox)
        supercellLayout.addWidget(self.ySupercellSpinBox)
        supercellLayout.addWidget(self.zSupercellSpinBox)

        # Wavefunction cutoff (Ry)

        self.wfCutoffLineEdit = QLineEdit()
        self.wfCutoffLineEdit.setValidator(QDoubleValidator())
        self.wfCutoffLineEdit.setText(f"{self.options.wfCutoffRy}")
        self.wfCutoffLineEdit.editingFinished.connect(self.updateWfCutoff)
        self.wfCutoffLineEdit.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        # Wavefunction form layout

        wfFormLayout = QFormLayout()
        wfFormLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        wfFormLayout.addRow('Exciton index:', self.excitonIndexSpinBox)
        wfFormLayout.addRow('Fixed particle type:', self.particleTypeComboBox)
        wfFormLayout.addRow('Particle position [X,Y,Z]:', particleLayout)
        wfFormLayout.addRow('Supercell [X,Y,Z]:', supercellLayout)
        wfFormLayout.addRow('Wave-function cutoff (Ry):', self.wfCutoffLineEdit)

        # Compute wavefunction button

        computeWfButton = QPushButton('Compute WF')
        computeWfButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        computeWfButton.clicked.connect(self.computeWf)

        # Layout and groupbox

        calcParamsLayout = QVBoxLayout()
        calcParamsLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        calcParamsLayout.addLayout(wfFormLayout)
        calcParamsLayout.addWidget(computeWfButton)

        calcParamsGroupBox = QGroupBox('Calculation parameters')
        calcParamsGroupBox.setLayout(calcParamsLayout)

        # Plot parameters

        # Representation type

        self.plotTypeComboBox = QComboBox()
        self.plotTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.plotTypeComboBox.addItems(['Isosurface', 'Isosurface set', 'Volumetric'])
        self.plotTypeComboBox.currentIndexChanged.connect(self.plotTypeChanged)

        # Isosurface level widget

        self.isoLevelTickMax = 1000

        isoLevelSlider = QSlider()
        isoLevelSlider.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        isoLevelSlider.setOrientation(Qt.Orientation.Horizontal)
        isoLevelSlider.setRange(0, self.isoLevelTickMax + 1)
        isoLevelSlider.setValue(self.options.isoLevel() * self.isoLevelTickMax)
        isoLevelSlider.valueChanged.connect(self.setIsoLevel)

        # Isosurface set cardinality widget

        numIsoLevelsSpinBox = QSpinBox(minimum=1, maximum=999)
        numIsoLevelsSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        numIsoLevelsSpinBox.setValue(self.options.numIsoLevels())
        numIsoLevelsSpinBox.valueChanged.connect(self.setNumIsoLevels)

        # Isosurface set opacity widget

        self.opacityTickMax = 1000

        opacitySlider = QSlider()
        opacitySlider.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        opacitySlider.setOrientation(Qt.Orientation.Horizontal)
        opacitySlider.setRange(0, self.opacityTickMax)
        opacitySlider.setValue(self.options.opacity() * self.opacityTickMax)
        opacitySlider.valueChanged.connect(self.setOpacity)

        # Slice density widget

        sliceDensitySpinBox = QSpinBox(minimum=1, maximum=999)
        sliceDensitySpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        sliceDensitySpinBox.setValue(self.options.sliceDensity())
        sliceDensitySpinBox.valueChanged.connect(self.setSliceDensity)

        # Plot form layout

        plotFormLayout = QFormLayout()
        plotFormLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        plotFormLayout.addRow('Plot type:', self.plotTypeComboBox)
        plotFormLayout.addRow('Iso level:', isoLevelSlider)
        plotFormLayout.addRow('Number of levels:', numIsoLevelsSpinBox)
        plotFormLayout.addRow('Isosurface opacity:', opacitySlider)
        plotFormLayout.addRow('Slices per voxel:', sliceDensitySpinBox)

        # Groupbox

        plotParamsGroupBox = QGroupBox('Plot parameters')
        plotParamsGroupBox.setLayout(plotFormLayout)

        # View parameters

        centerViewButton = QPushButton('Center view')
        centerViewButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        centerViewButton.clicked.connect(self.centerViewClicked)

        # View layout

        viewLayout = QVBoxLayout()
        viewLayout.addWidget(centerViewButton)

        # Groupbox

        viewParamsGroupBox = QGroupBox('View')
        viewParamsGroupBox.setLayout(viewLayout)

        # Main layout

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(calcParamsGroupBox)
        mainLayout.addWidget(plotParamsGroupBox)
        mainLayout.addWidget(viewParamsGroupBox)

        self.setLayout(mainLayout)

    @Slot(int)
    def updateParticlePositionWidgets(self, index: int):
        self.options.setParticleType(index)

        position = self.options.particlePosition()

        self.xParticlePosLineEdit.setText(f"{position[0]}")
        self.yParticlePosLineEdit.setText(f"{position[1]}")
        self.zParticlePosLineEdit.setText(f"{position[2]}")

        self.particlePositionChanged()

    @Slot()
    def particlePositionChanged(self):
        position = [float(self.xParticlePosLineEdit.text()), float(self.yParticlePosLineEdit.text()), float(self.zParticlePosLineEdit.text())]
        self.options.setParticlePosition(position)
        self.fixedParticlePosChanged.emit()

    @Slot()
    def updateWfCutoff(self):
        self.options.setWfCutoff(float(self.wfCutoffLineEdit.text()))

    @Slot()
    def computeWf(self):
        exc_index = self.excitonIndexSpinBox.value()
        fixed_particle = self.options.particleType()
        fixed_position = self.options.particlePosition()
        cutoff = self.options.wfCutoff()
        supercell = [self.xSupercellSpinBox.value(), self.ySupercellSpinBox.value(), self.zSupercellSpinBox.value()]

        self.calculations.computeExcitonWaveFunction(exc_index=exc_index, fixed_particle=fixed_particle, fixed_position=fixed_position, cutoff_ry=cutoff, supercell=supercell)

    @Slot(int)
    def setIsoLevel(self, tick: int):
        self.options.setIsoLevel(float(tick / self.isoLevelTickMax))
        self.isoLevelChanged.emit()

        if self.plotTypeComboBox.currentIndex() != 0:
            self.plotTypeComboBox.setCurrentIndex(0)

    @Slot(int)
    def setNumIsoLevels(self, numIsoLevels: int):
        self.options.setNumIsoLevels(numIsoLevels)
        self.numIsoLevelsChanged.emit()

        if self.plotTypeComboBox.currentIndex() != 1:
            self.plotTypeComboBox.setCurrentIndex(1)

    @Slot(int)
    def setOpacity(self, tick: int):
        self.options.setOpacity(float(tick / self.opacityTickMax))
        self.opacityChanged.emit(self.options.opacity())

    @Slot(int)
    def setSliceDensity(self, density):
        self.options.setSliceDensity(density)
        self.sliceDensityChanged.emit()

        if self.plotTypeComboBox.currentIndex() != 2:
            self.plotTypeComboBox.setCurrentIndex(2)

    def plotType(self):
        return self.plotTypeComboBox.currentIndex()

    @Slot()
    def supercellChanged(self):
        self.options.setSupercell([self.xSupercellSpinBox.value(), self.ySupercellSpinBox.value(), self.zSupercellSpinBox.value()])
        self.signalReplotLattice.emit()