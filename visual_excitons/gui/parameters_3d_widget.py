from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QWidget, QPushButton, QSizePolicy, QVBoxLayout, QSpinBox, QLineEdit, QFormLayout
from PySide6.QtWidgets import QSlider, QComboBox, QHBoxLayout, QGroupBox, QCheckBox, QLabel, QDoubleSpinBox
import numpy as np

from visual_excitons.core.calculations import Calculations
from visual_excitons.core.options import Options

class WrappedLabel(QLabel):
    """
    Word-wrapped label that always gets the height its text needs at its current
    width. QFormLayout does not ask labels for their height for a given width, so
    a plain word-wrapped QLabel gets clipped when the panel is narrow.
    """

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)

    def _fitHeight(self):
        height = self.heightForWidth(self.width())
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)

    def setText(self, text):
        super().setText(text)
        self._fitHeight()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fitHeight()


class Parameters3DWidget(QWidget):
    plotTypeChanged = Signal(int)
    signalReplotLattice = Signal()
    fixedParticlePosChanged = Signal()
    isoLevelChanged = Signal()
    numIsoLevelsChanged = Signal()
    sliceDensityChanged = Signal()
    volumeParametersChanged = Signal()
    isoOpacityChanged = Signal(float, float)  # opacity, iso level
    isoSetOpacityChanged = Signal(float)
    centerViewClicked = Signal()
    viewDirChanged = Signal(list, object)  # look direction, up direction or None (Cartesian)
    projectionChanged = Signal(Qt.CheckState)
    viewLatticeChanged = Signal(Qt.CheckState)
    viewAtomNamesChanged = Signal(Qt.CheckState)
    viewBoundariesChanged = Signal(Qt.CheckState)
    showCartesianAxesChanged = Signal(bool)
    showLatticeVectorsChanged = Signal(bool)
    showReciprocalVectorsChanged = Signal(bool)
    showAxisLabelsChanged = Signal(bool)
    showCellInfoChanged = Signal(bool)
    isoSetStyleChanged = Signal(int)

    def __init__(self, options: Options, calculations: Calculations):
        QWidget.__init__(self)

        self.options = options
        self.calculations = calculations
        self.calculations.wfComputed.connect(self.onWfComputed)

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

        self.xSupercellSpinBox = QSpinBox(minimum=1, maximum=999, singleStep=2)
        self.xSupercellSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.xSupercellSpinBox.setValue(1)
        self.xSupercellSpinBox.setToolTip('Odd sizes only: the fixed particle is placed in the central cell')
        self.xSupercellSpinBox.valueChanged.connect(self.supercellChanged)

        self.ySupercellSpinBox = QSpinBox(minimum=1, maximum=999, singleStep=2)
        self.ySupercellSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.ySupercellSpinBox.setValue(1)
        self.ySupercellSpinBox.setToolTip('Odd sizes only: the fixed particle is placed in the central cell')
        self.ySupercellSpinBox.valueChanged.connect(self.supercellChanged)

        self.zSupercellSpinBox = QSpinBox(minimum=1, maximum=999, singleStep=2)
        self.zSupercellSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.zSupercellSpinBox.setValue(1)
        self.zSupercellSpinBox.setToolTip('Odd sizes only: the fixed particle is placed in the central cell')
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

        # Shown after computing: the position is snapped to the wave-function grid
        self.particleGridLabel = WrappedLabel()
        self.particleGridLabel.setStyleSheet('color: gray')
        self.particleGridLabel.hide()
        # Spanning both columns, so the wrapped text has the full width of the form
        wfFormLayout.addRow(self.particleGridLabel)
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

        # Opacity widgets of the single isosurface and of the isosurface set

        self.opacityTickMax = 1000

        isoOpacitySlider = QSlider()
        isoOpacitySlider.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        isoOpacitySlider.setOrientation(Qt.Orientation.Horizontal)
        isoOpacitySlider.setRange(0, self.opacityTickMax)
        isoOpacitySlider.setValue(round(self.options.isoOpacity() * self.opacityTickMax))
        isoOpacitySlider.valueChanged.connect(self.setIsoOpacity)

        isoSetOpacitySlider = QSlider()
        isoSetOpacitySlider.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        isoSetOpacitySlider.setOrientation(Qt.Orientation.Horizontal)
        isoSetOpacitySlider.setRange(0, self.opacityTickMax)
        isoSetOpacitySlider.setValue(round(self.options.isoSetOpacity() * self.opacityTickMax))
        isoSetOpacitySlider.valueChanged.connect(self.setIsoSetOpacity)

        # Slice density widget

        sliceDensitySpinBox = QSpinBox(minimum=1, maximum=999)
        sliceDensitySpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        sliceDensitySpinBox.setValue(self.options.sliceDensity())
        sliceDensitySpinBox.valueChanged.connect(self.setSliceDensity)

        # Volume opacity and contrast widgets

        volumeOpacitySlider = QSlider()
        volumeOpacitySlider.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        volumeOpacitySlider.setOrientation(Qt.Orientation.Horizontal)
        volumeOpacitySlider.setRange(0, self.opacityTickMax)
        volumeOpacitySlider.setValue(round(self.options.volumeOpacity() * self.opacityTickMax))
        volumeOpacitySlider.setToolTip('Opacity along the densest line of sight through the density')
        volumeOpacitySlider.valueChanged.connect(self.setVolumeOpacity)

        volumeContrastSpinBox = QDoubleSpinBox(minimum=0.1, maximum=10.0, singleStep=0.1, decimals=2)
        volumeContrastSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        volumeContrastSpinBox.setValue(self.options.volumeContrast())
        volumeContrastSpinBox.setToolTip('Power applied to the density for the opacity:\n'
                                         'above 1 fades low densities so the core stands out,\n'
                                         'below 1 brings out the low-density tails')
        volumeContrastSpinBox.valueChanged.connect(self.setVolumeContrast)

        # Plot form layout

        plotFormLayout = QFormLayout()
        plotFormLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        plotFormLayout.addRow('Plot type:', self.plotTypeComboBox)
        plotFormLayout.addRow('Iso level:', isoLevelSlider)
        plotFormLayout.addRow('Number of levels:', numIsoLevelsSpinBox)

        isoSetStyleComboBox = QComboBox()
        isoSetStyleComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        isoSetStyleComboBox.addItems(['Lit, edges emphasized', 'Edges only (x-ray)'])
        isoSetStyleComboBox.setToolTip('Shading of the isosurface set')
        isoSetStyleComboBox.currentIndexChanged.connect(self.isoSetStyleChanged)
        plotFormLayout.addRow('Isosurface set style:', isoSetStyleComboBox)
        plotFormLayout.addRow('Isosurface opacity:', isoOpacitySlider)
        plotFormLayout.addRow('Isosurface set opacity:', isoSetOpacitySlider)
        plotFormLayout.addRow('Volume opacity:', volumeOpacitySlider)
        plotFormLayout.addRow('Volume contrast:', volumeContrastSpinBox)
        plotFormLayout.addRow('Slices per voxel:', sliceDensitySpinBox)

        # Rows shown only for the plot types they apply to
        # (0: isosurface, 1: isosurface set, 2: volumetric)
        self.plotFormLayout = plotFormLayout
        self.plotTypeRows = [
            (isoLevelSlider, {0}),
            (numIsoLevelsSpinBox, {1}),
            (isoSetStyleComboBox, {1}),
            (isoOpacitySlider, {0}),
            (isoSetOpacitySlider, {1}),
            (volumeOpacitySlider, {2}),
            (volumeContrastSpinBox, {2}),
            (sliceDensitySpinBox, {2}),
        ]
        self.plotTypeComboBox.currentIndexChanged.connect(self.updatePlotTypeRows)
        self.updatePlotTypeRows(self.plotTypeComboBox.currentIndex())

        # Groupbox

        plotParamsGroupBox = QGroupBox('Plot parameters')
        plotParamsGroupBox.setLayout(plotFormLayout)

        # View parameters

        centerViewButton = QPushButton('Center view')
        centerViewButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        centerViewButton.clicked.connect(self.centerViewClicked)

        # View direction: basis, presets and custom direction / up vectors

        self.viewBasisComboBox = QComboBox()
        self.viewBasisComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.viewBasisComboBox.addItems(self.options.viewBases)
        self.viewBasisComboBox.setToolTip('Basis of the direction and up vectors:\n'
                                          'Cartesian: x, y, z\n'
                                          'Lattice [uvw]: u a + v b + w c\n'
                                          'Reciprocal (hkl): h a* + k b* + l c*, normal to the (hkl) planes')
        self.viewBasisComboBox.currentIndexChanged.connect(self.onViewBasisChanged)

        self.viewPresetComboBox = QComboBox()
        self.viewPresetComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.viewPresetComboBox.activated.connect(self.onViewPresetActivated)

        self.viewDirLineEdits = [self.newVectorLineEdit() for _ in range(3)]
        self.viewUpLineEdits = [self.newVectorLineEdit('auto') for _ in range(3)]
        for lineEdit in self.viewDirLineEdits + self.viewUpLineEdits:
            lineEdit.returnPressed.connect(self.applyView)

        viewDirLayout = QHBoxLayout()
        for lineEdit in self.viewDirLineEdits:
            viewDirLayout.addWidget(lineEdit)

        viewUpLayout = QHBoxLayout()
        for lineEdit in self.viewUpLineEdits:
            viewUpLayout.addWidget(lineEdit)

        applyViewButton = QPushButton('Apply')
        applyViewButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        applyViewButton.clicked.connect(self.applyView)
        viewDirLayout.addWidget(applyViewButton)

        self.reverseViewCheckBox = QCheckBox('View from the opposite side')
        self.reverseViewCheckBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.reverseViewCheckBox.setToolTip('Look along minus the direction, i.e. with it pointing towards the viewer')
        self.reverseViewCheckBox.setChecked(True)
        self.reverseViewCheckBox.toggled.connect(self.applyView)

        self.viewStatusLabel = QLabel()
        self.viewStatusLabel.setStyleSheet('color: red')
        self.viewStatusLabel.setVisible(False)

        viewFormLayout = QFormLayout()
        viewFormLayout.addRow('Basis:', self.viewBasisComboBox)
        viewFormLayout.addRow('Preset:', self.viewPresetComboBox)
        viewFormLayout.addRow('Direction:', viewDirLayout)
        viewFormLayout.addRow('Up (optional):', viewUpLayout)

        # Lattice bases need the cell from the SAVE database
        self.setLatticeBasesEnabled(self.options.hasCell())
        self.options.databaseFound.connect(self.onDatabaseFound)

        self.populateViewPresets()
        self.viewPresetComboBox.setCurrentText('x + y + z')
        self.onViewPresetActivated(self.viewPresetComboBox.currentIndex(), apply=False)

        projectionCheckBox = QCheckBox('Orthographic projection')
        projectionCheckBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        projectionCheckBox.setCheckState(Qt.CheckState.Checked)
        projectionCheckBox.checkStateChanged.connect(self.projectionChanged)

        viewLatticeCheckBox = QCheckBox('View lattice')
        viewLatticeCheckBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        viewLatticeCheckBox.setCheckState(Qt.CheckState.Checked)
        viewLatticeCheckBox.checkStateChanged.connect(self.viewLatticeChanged)

        viewAtomNamesCheckBox = QCheckBox('View atom names')
        viewAtomNamesCheckBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        viewAtomNamesCheckBox.setCheckState(Qt.CheckState.Checked)
        viewAtomNamesCheckBox.checkStateChanged.connect(self.viewAtomNamesChanged)

        viewBoundariesCheckBox = QCheckBox('View boundaries')
        viewBoundariesCheckBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        viewBoundariesCheckBox.setCheckState(Qt.CheckState.Checked)
        viewBoundariesCheckBox.checkStateChanged.connect(self.viewBoundariesChanged)

        # View sublayout

        # View layout

        viewLayout = QVBoxLayout()
        viewLayout.addWidget(centerViewButton)
        viewLayout.addLayout(viewFormLayout)
        viewLayout.addWidget(self.reverseViewCheckBox)
        viewLayout.addWidget(self.viewStatusLabel)
        viewLayout.addWidget(projectionCheckBox)
        viewLayout.addWidget(viewLatticeCheckBox)
        viewLayout.addWidget(viewAtomNamesCheckBox)
        viewLayout.addWidget(viewBoundariesCheckBox)

        # Groupbox

        viewParamsGroupBox = QGroupBox('View')
        viewParamsGroupBox.setLayout(viewLayout)

        # Axes gizmo and cell parameters

        axesLayout = QVBoxLayout()
        for text, signal, checked, tooltip in [
            ('Cartesian axes x, y, z', self.showCartesianAxesChanged, True, 'Grey arrows in the axes gizmo'),
            ('Lattice vectors a, b, c', self.showLatticeVectorsChanged, True, 'Red, green and blue arrows in the axes gizmo'),
            ('Reciprocal vectors a*, b*, c*', self.showReciprocalVectorsChanged, False, 'Light red, green and blue arrows in the axes gizmo'),
            ('Axis labels', self.showAxisLabelsChanged, True, 'Labels at the tips of the gizmo arrows'),
            ('Cell parameters', self.showCellInfoChanged, True, 'Lattice constants and angles in the top-left corner'),
        ]:
            checkBox = QCheckBox(text)
            checkBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            checkBox.setToolTip(tooltip)
            checkBox.setChecked(checked)
            checkBox.toggled.connect(signal)
            axesLayout.addWidget(checkBox)

        axesNoteLabel = QLabel('Each set of arrows is scaled so that its longest vector has the same length.')
        axesNoteLabel.setWordWrap(True)
        axesNoteLabel.setStyleSheet('color: gray')
        axesLayout.addWidget(axesNoteLabel)

        axesGroupBox = QGroupBox('Axes')
        axesGroupBox.setLayout(axesLayout)

        # Main layout

        mainLayout = QVBoxLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(calcParamsGroupBox)
        mainLayout.addWidget(plotParamsGroupBox)
        mainLayout.addWidget(viewParamsGroupBox)
        mainLayout.addWidget(axesGroupBox)

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
    def onWfComputed(self):
        """Show the position and supercell actually used for the wave function."""
        calc = self.calculations

        # Supercell: odd sizes are enforced here, so this only guards against changes
        for spinBox, size in zip((self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox), calc.wfSupercell):
            if spinBox.value() != size:
                spinBox.setValue(size)

        # Fixed particle position snapped to the real-space grid
        self.options.setParticlePositionOf(calc.wfFixedParticle, calc.wfFixedPosition)
        if calc.wfFixedParticle == self.options.particleType():
            for lineEdit, value in zip((self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit), calc.wfFixedPosition):
                lineEdit.setText(f'{value:.4f}')

        particle = 'Hole' if calc.wfFixedParticle == 'h' else 'Electron'
        self.particleGridLabel.setText(f'{particle} position snapped to the nearest point of the wave-function grid '
                                       f'({calc.wfGrid[0]} × {calc.wfGrid[1]} × {calc.wfGrid[2]} points per cell).')
        self.particleGridLabel.show()
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

    @Slot(int)
    def setNumIsoLevels(self, numIsoLevels: int):
        self.options.setNumIsoLevels(numIsoLevels)
        self.numIsoLevelsChanged.emit()

    @Slot(int)
    def setIsoOpacity(self, tick: int):
        self.options.setIsoOpacity(float(tick / self.opacityTickMax))
        self.isoOpacityChanged.emit(self.options.isoOpacity(), self.options.isoLevel())

    @Slot(int)
    def setIsoSetOpacity(self, tick: int):
        self.options.setIsoSetOpacity(float(tick / self.opacityTickMax))
        self.isoSetOpacityChanged.emit(self.options.isoSetOpacity())

    @Slot(int)
    def setSliceDensity(self, density):
        self.options.setSliceDensity(density)
        self.sliceDensityChanged.emit()

    @Slot(int)
    def setVolumeOpacity(self, tick: int):
        self.options.setVolumeOpacity(tick / self.opacityTickMax)
        self.volumeParametersChanged.emit()

    @Slot(float)
    def setVolumeContrast(self, contrast: float):
        self.options.setVolumeContrast(contrast)
        self.volumeParametersChanged.emit()

    @Slot(int)
    def updatePlotTypeRows(self, plotType: int):
        for widget, plotTypes in self.plotTypeRows:
            self.plotFormLayout.setRowVisible(widget, plotType in plotTypes)

    def plotType(self):
        return self.plotTypeComboBox.currentIndex()

    @Slot()
    def supercellChanged(self):
        # Even sizes are increased by 1, as the wave-function calculation does,
        # so that the lattice drawn always matches the wave function
        for spinBox in (self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox):
            if spinBox.value() % 2 == 0:
                spinBox.blockSignals(True)
                spinBox.setValue(spinBox.value() + 1)
                spinBox.blockSignals(False)

        self.options.setSupercell([self.xSupercellSpinBox.value(), self.ySupercellSpinBox.value(), self.zSupercellSpinBox.value()])
        self.signalReplotLattice.emit()
        # The fixed particle sits in the central cell, which moves with the supercell
        self.fixedParticlePosChanged.emit()

    # View direction

    def newVectorLineEdit(self, placeholder=''):
        lineEdit = QLineEdit()
        lineEdit.setValidator(QDoubleValidator())
        lineEdit.setPlaceholderText(placeholder)
        lineEdit.setMaximumWidth(70)
        return lineEdit

    def viewBasis(self):
        return self.viewBasisComboBox.currentText()

    def setLatticeBasesEnabled(self, enabled: bool):
        model = self.viewBasisComboBox.model()
        for i, basis in enumerate(self.options.viewBases):
            if basis != 'Cartesian':
                model.item(i).setEnabled(enabled)
        if not enabled and self.viewBasis() != 'Cartesian':
            self.viewBasisComboBox.setCurrentText('Cartesian')

    @Slot(bool)
    def onDatabaseFound(self, found: bool):
        self.setLatticeBasesEnabled(found)
        # A new cell changes what lattice directions mean in Cartesian space
        if found and self.viewBasis() != 'Cartesian':
            self.applyView()

    def populateViewPresets(self):
        self.viewPresetComboBox.clear()
        self.viewPresetComboBox.addItems(list(self.options.viewPresets[self.viewBasis()].keys()))

    @Slot(int)
    def onViewBasisChanged(self, index: int):
        presetIndex = self.viewPresetComboBox.currentIndex()
        self.populateViewPresets()
        self.viewPresetComboBox.setCurrentIndex(max(presetIndex, 0))
        self.onViewPresetActivated(self.viewPresetComboBox.currentIndex())

    @Slot(int)
    def onViewPresetActivated(self, index: int, apply: bool = True):
        presets = self.options.viewPresets[self.viewBasis()]
        vector = list(presets.values())[index]
        for lineEdit, value in zip(self.viewDirLineEdits, vector):
            lineEdit.setText(f'{value:g}')
        for lineEdit in self.viewUpLineEdits:
            lineEdit.clear()
        if apply:
            self.applyView()

    def readVector(self, lineEdits):
        """Vector from three line edits; empty fields count as 0. None if all are empty."""
        texts = [lineEdit.text().strip() for lineEdit in lineEdits]
        if not any(texts):
            return None
        return [float(text.replace(',', '.')) if text else 0.0 for text in texts]

    def showViewStatus(self, message: str):
        self.viewStatusLabel.setText(message)
        self.viewStatusLabel.setVisible(bool(message))

    @Slot()
    def applyView(self):
        try:
            direction = self.readVector(self.viewDirLineEdits)
            up = self.readVector(self.viewUpLineEdits)
        except ValueError:
            self.showViewStatus('Invalid number in the direction or up vector')
            return

        if direction is None or np.allclose(direction, 0.0):
            self.showViewStatus('The direction must be a non-zero vector')
            return

        if up is not None and np.allclose(up, 0.0):
            up = None

        try:
            lookDir = self.options.viewVectorToCartesian(direction, self.viewBasis())
            upDir = None if up is None else self.options.viewVectorToCartesian(up, self.viewBasis())
        except ValueError as error:
            self.showViewStatus(str(error))
            return

        if self.reverseViewCheckBox.isChecked():
            lookDir = -lookDir

        self.showViewStatus('')
        self.viewDirChanged.emit(lookDir.tolist(), None if upDir is None else upDir.tolist())
