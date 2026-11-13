from PySide6.QtCore import Qt, Signal, Slot, QSize, QTimer
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import QPushButton, QSizePolicy, QSpinBox, QLineEdit, QGridLayout
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QCheckBox, QLabel, QDoubleSpinBox, QMessageBox
import numpy as np

from visual_excitons.core.calculations import Calculations
from visual_excitons.core.options import Options
from .inspector import Inspector, formLayout, ValueSlider, NoteLabel
from .persistence import DATASET
from .colormaps import COLORMAP_GROUPS, DEFAULT_COLORMAP, makeColormap, colormapIcon
from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR
from visual_excitons.core.memory import availableMemory, formatBytes

# Warn when a calculation would use more than this fraction of the available memory
MEMORY_WARNING_FRACTION = 0.9



class ChoiceSpinBox(QSpinBox):
    """
    A spin box of integers restricted to some values (e.g. the computed
    Q-points): its arrows step between them, other values typed are not
    accepted (corrected to the nearest), and setValue takes the nearest.
    """

    # No choices: any value in the range. A class attribute: Qt calls the
    # overrides below while the spin box is being constructed
    choices = None

    def setChoices(self, values):
        self.choices = sorted(set(int(value) for value in values)) or None
        if self.choices:
            self.setRange(self.choices[0], self.choices[-1])
            if self.value() not in self.choices:
                super().setValue(self.nearest(self.value()))

    def nearest(self, value):
        return min(self.choices, key=lambda choice: (abs(choice - value), choice))

    def setValue(self, value):
        super().setValue(self.nearest(int(value)) if self.choices else int(value))

    def stepBy(self, steps):
        if not self.choices:
            return super().stepBy(steps)
        index = self.choices.index(self.nearest(self.value()))
        super().setValue(self.choices[max(0, min(len(self.choices) - 1, index + steps))])

    def validate(self, text, position):
        state, text, position = super().validate(text, position)
        if self.choices and state == QValidator.State.Acceptable and self.valueFromText(text) not in self.choices:
            state = QValidator.State.Intermediate
        return state, text, position

    def fixup(self, text):
        if self.choices:
            try:
                return str(self.nearest(int(text)))
            except ValueError:
                return str(self.value())
        return super().fixup(text)

class Parameters3DWidget(Inspector):
    plotTypeChanged = Signal(int)
    signalReplotLattice = Signal()
    # The supercell changed (not only redrawn): the view is centered again
    supercellResized = Signal()
    # Memory of computing the exciton selected in the spectra (text, warning)
    selectedEstimateChanged = Signal(str, bool)
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
    viewBondsChanged = Signal(Qt.CheckState)
    showCartesianAxesChanged = Signal(bool)
    showLatticeVectorsChanged = Signal(bool)
    showReciprocalVectorsChanged = Signal(bool)
    showAxisLabelsChanged = Signal(bool)
    showCellInfoChanged = Signal(bool)
    isoSetStyleChanged = Signal(int)
    exportImageRequested = Signal()
    colormapChanged = Signal(object)   # pyqtgraph ColorMap
    analysisChanged = Signal()
    smoothingChanged = Signal(int)   # display upsampling factor
    planeFromViewRequested = Signal()
    exportDensityRequested = Signal()

    def __init__(self, options: Options, calculations: Calculations):
        Inspector.__init__(self)

        self.options = options
        self.calculations = calculations
        self.calculations.wfComputed.connect(self.onWfComputed)
        self.calculations.excitonSelected.connect(self.onExcitonSelected)

        self.buildExcitonSection()
        self.buildCalculationSection()
        self.buildDisplaySection()
        self.buildViewSection()
        self.buildStructureSection()
        self.buildAxesSection()
        self.buildAnalysisSection()
        self.buildExportSection()

        self.alignLabels()
        self.persistence.afterRestore.append(self.afterRestore)

    def afterRestore(self, scope):
        """Apply restored values that the widgets do not apply by themselves."""
        if scope == DATASET:
            # Shows the position of the restored particle type and moves the marker
            self.updateParticlePositionWidgets(self.particleTypeComboBox.currentIndex())
        else:
            self.applyView()

    # Sections

    def buildExcitonSection(self):
        self.qPointSpinBox = ChoiceSpinBox(minimum=1, maximum=max(1, self.options.nQpoints))
        self.qPointSpinBox.setToolTip('Q-point of the exciton: the file ndb.BS_diago_Q<n> of the BSE directory '
                                      '(only those computed)')
        self.options.numQPointsChanged.connect(
            lambda n: self.qPointSpinBox.choices is None and self.qPointSpinBox.setMaximum(max(1, n)))
        # Only the Q-points computed, which may be some of them (e.g. Q1, Q5, Q30)
        self.options.qPointsChanged.connect(lambda qPoints: self.qPointSpinBox.setChoices([q + 1 for q in qPoints]))
        if self.options.qPoints:
            self.qPointSpinBox.setChoices([q + 1 for q in self.options.qPoints])

        self.excitonIndexSpinBox = QSpinBox(minimum=1, maximum=99999)
        self.excitonIndexSpinBox.setToolTip('Index of the exciton at that Q-point, in increasing energy')

        for spinBox in (self.qPointSpinBox, self.excitonIndexSpinBox):
            spinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            spinBox.valueChanged.connect(self.updateExcitonNote)

        self.excitonNote = NoteLabel()

        form = formLayout()
        form.addRow('Q-point:', self.qPointSpinBox)
        form.addRow('Exciton:', self.excitonIndexSpinBox)
        form.addRow(self.excitonNote)
        self.addSection('Exciton', form)
        self.remember('qPoint', self.qPointSpinBox, DATASET)
        self.remember('exciton', self.excitonIndexSpinBox, DATASET)
        self.updateExcitonNote()

    def buildCalculationSection(self):
        self.particleTypeComboBox = QComboBox()
        self.particleTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.particleTypeComboBox.addItems(['Hole', 'Electron'])
        self.particleTypeComboBox.currentIndexChanged.connect(self.updateParticlePositionWidgets)

        # Fixed particle position, in crystal coordinates of the unit cell
        self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit = (self.newCoordinateLineEdit() for _ in range(3))
        for lineEdit in (self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit):
            lineEdit.setValidator(QDoubleValidator(0.0, 1.0, 4))
            lineEdit.setToolTip('Crystal coordinates (fractions of a, b, c) in the unit cell')
            lineEdit.editingFinished.connect(self.particlePositionChanged)
        self.updateParticlePositionWidgets(self.particleTypeComboBox.currentIndex())

        particleLayout = QHBoxLayout()
        for lineEdit in (self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit):
            particleLayout.addWidget(lineEdit)

        # Supercell: odd sizes only
        self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox = (QSpinBox(minimum=1, maximum=999, singleStep=2) for _ in range(3))
        supercellLayout = QHBoxLayout()
        for spinBox in (self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox):
            spinBox.setValue(1)
            spinBox.setToolTip('Odd sizes only: the fixed particle is placed in the central cell')
            spinBox.valueChanged.connect(self.supercellChanged)
            supercellLayout.addWidget(spinBox)
        supercellLayout.addStretch(1)

        self.wfCutoffSpinBox = QDoubleSpinBox(minimum=0.1, maximum=10000.0, singleStep=1.0, decimals=1, suffix=' Ry')
        self.wfCutoffSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.wfCutoffSpinBox.setValue(self.options.wfCutoffRy)
        self.wfCutoffSpinBox.setToolTip('Plane-wave cutoff of the wave function: higher values give a finer real-space grid')
        self.wfCutoffSpinBox.valueChanged.connect(self.options.setWfCutoff)

        self.fullCutoffCheckBox = QCheckBox('All plane waves')
        self.fullCutoffCheckBox.setToolTip('No cutoff: all the plane waves of the wave functions in the SAVE database,\n'
                                           'the finest grid possible (and the most memory)')
        self.fullCutoffCheckBox.toggled.connect(self.wfCutoffSpinBox.setDisabled)

        cutoffLayout = QHBoxLayout()
        cutoffLayout.addWidget(self.wfCutoffSpinBox)
        cutoffLayout.addWidget(self.fullCutoffCheckBox)
        cutoffLayout.addStretch(1)

        # Grid and memory of the calculation, updated as its parameters change
        self.estimateNote = NoteLabel()
        self.estimateWarning = False
        self.estimateTimer = QTimer(self)
        self.estimateTimer.setSingleShot(True)
        self.estimateTimer.setInterval(250)
        self.estimateTimer.timeout.connect(self.updateEstimate)
        self.lastEstimate = None
        for signal in (self.wfCutoffSpinBox.valueChanged, self.fullCutoffCheckBox.toggled,
                       self.qPointSpinBox.valueChanged, self.excitonIndexSpinBox.valueChanged,
                       self.xSupercellSpinBox.valueChanged, self.ySupercellSpinBox.valueChanged,
                       self.zSupercellSpinBox.valueChanged, self.calculations.wfComputed,
                       self.particleTypeComboBox.currentIndexChanged,   # named in the selected exciton's estimate
                       self.options.databaseFound, self.options.diagoDirChanged):
            signal.connect(self.requestEstimate)
        # The databases may be busy while a calculation runs: estimate once it ends
        self.calculations.busyChanged.connect(lambda busy: None if busy else self.requestEstimate())

        # Shown after computing: the position is snapped to the wave-function grid
        self.particleGridLabel = NoteLabel()
        self.particleGridLabel.hide()

        computeWfButton = QPushButton('Compute wave function')
        computeWfButton.clicked.connect(self.computeWf)

        form = formLayout()
        form.addRow('Fixed particle:', self.particleTypeComboBox)
        form.addRow('Position (a, b, c):', particleLayout)
        # Spanning both columns, so the wrapped text has the full width of the form
        form.addRow(self.particleGridLabel)
        form.addRow('Supercell:', supercellLayout)
        form.addRow('Cutoff:', cutoffLayout)
        form.addRow(computeWfButton)
        form.addRow(self.estimateNote)
        self.addSection('Calculation', form)

        # Both positions, before the particle type that shows one of them
        def positionSetter(particle):
            return lambda value: self.options.setParticlePositionOf(particle, [float(x) for x in value][:3])
        self.remember('holePosition', scope=DATASET, get=lambda: list(self.options.holePos), set=positionSetter('h'))
        self.remember('electronPosition', scope=DATASET, get=lambda: list(self.options.electronPos), set=positionSetter('e'))
        self.remember('fixedParticle', self.particleTypeComboBox, DATASET)
        self.remember('supercell', scope=DATASET, get=self.supercell, set=self.setSupercell)
        self.remember('cutoff', self.wfCutoffSpinBox, DATASET)
        self.remember('fullCutoff', self.fullCutoffCheckBox, DATASET)

    def buildDisplaySection(self):
        self.plotTypeComboBox = QComboBox()
        self.plotTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.plotTypeComboBox.addItems(['Isosurface', 'Isosurface set', 'Volumetric'])
        self.plotTypeComboBox.currentIndexChanged.connect(self.plotTypeChanged)

        self.isoLevelTickMax = 1000
        self.opacityTickMax = 1000

        def fraction(tickMax):
            return lambda tick: f'{tick / tickMax:.2f}'

        isoLevelSlider = ValueSlider(0, self.isoLevelTickMax, round(self.options.isoLevel() * self.isoLevelTickMax), fraction(self.isoLevelTickMax))
        isoLevelSlider.setToolTip('Probability density of the isosurface, relative to its maximum')
        isoLevelSlider.valueChanged.connect(self.setIsoLevel)

        numIsoLevelsSpinBox = QSpinBox(minimum=1, maximum=999)
        numIsoLevelsSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        numIsoLevelsSpinBox.setValue(self.options.numIsoLevels())
        numIsoLevelsSpinBox.valueChanged.connect(self.setNumIsoLevels)

        isoSetStyleComboBox = QComboBox()
        isoSetStyleComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        isoSetStyleComboBox.addItems(['Lit, edges emphasized', 'Edges only (x-ray)'])
        isoSetStyleComboBox.setToolTip('Shading of the isosurface set')
        isoSetStyleComboBox.currentIndexChanged.connect(self.isoSetStyleChanged)

        isoOpacitySlider = ValueSlider(0, self.opacityTickMax, round(self.options.isoOpacity() * self.opacityTickMax), fraction(self.opacityTickMax))
        isoOpacitySlider.valueChanged.connect(self.setIsoOpacity)

        isoSetOpacitySlider = ValueSlider(0, self.opacityTickMax, round(self.options.isoSetOpacity() * self.opacityTickMax), fraction(self.opacityTickMax))
        isoSetOpacitySlider.valueChanged.connect(self.setIsoSetOpacity)

        volumeOpacitySlider = ValueSlider(0, self.opacityTickMax, round(self.options.volumeOpacity() * self.opacityTickMax), fraction(self.opacityTickMax))
        volumeOpacitySlider.setToolTip('Opacity along the densest line of sight through the density')
        volumeOpacitySlider.valueChanged.connect(self.setVolumeOpacity)

        volumeContrastSpinBox = QDoubleSpinBox(minimum=0.1, maximum=10.0, singleStep=0.1, decimals=2)
        volumeContrastSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        volumeContrastSpinBox.setValue(self.options.volumeContrast())
        volumeContrastSpinBox.setToolTip('Power applied to the density for the opacity:\n'
                                         'above 1 fades low densities so the core stands out,\n'
                                         'below 1 brings out the low-density tails')
        volumeContrastSpinBox.valueChanged.connect(self.setVolumeContrast)

        sliceDensitySpinBox = QSpinBox(minimum=1, maximum=999)
        sliceDensitySpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        sliceDensitySpinBox.setValue(self.options.sliceDensity())
        sliceDensitySpinBox.setToolTip('Rendering quality: more slices give a smoother volume')
        sliceDensitySpinBox.valueChanged.connect(self.setSliceDensity)

        # Colormap of the density, for all plot types
        self.colormapComboBox = QComboBox()
        self.colormapComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.colormapComboBox.setIconSize(QSize(48, 12))
        for group, maps in COLORMAP_GROUPS:
            if self.colormapComboBox.count():
                self.colormapComboBox.insertSeparator(self.colormapComboBox.count())
            for label, name, description in maps:
                self.colormapComboBox.addItem(label)
                self.colormapComboBox.setItemData(self.colormapComboBox.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
        self.colormapComboBox.setCurrentText(DEFAULT_COLORMAP)
        self.colormapComboBox.setToolTip('Colors of the probability density, from low to high')

        self.reverseColormapCheckBox = QCheckBox('Reverse')
        self.reverseColormapCheckBox.setToolTip('High densities in the colors of low ones and vice versa')

        colormapLayout = QHBoxLayout()
        colormapLayout.addWidget(self.colormapComboBox)
        colormapLayout.addWidget(self.reverseColormapCheckBox)
        colormapLayout.addStretch(1)

        self.colormapComboBox.currentIndexChanged.connect(self.onColormapChanged)
        self.reverseColormapCheckBox.toggled.connect(self.onColormapChanged)
        self.updateColormapIcons()

        form = formLayout()
        form.addRow('Plot type:', self.plotTypeComboBox)
        form.addRow('Colormap:', colormapLayout)
        self.smoothingComboBox = QComboBox()
        self.smoothingComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.smoothingComboBox.addItems(['None', '2×', '3×'])
        self.smoothingComboBox.setToolTip('Display the density on a grid 2 or 3 times finer, interpolated smoothly:\n'
                                          'smoother isosurfaces and volume, with no new physical detail\n'
                                          '(that needs a higher cutoff). Analysis and exports use the real grid.')
        self.smoothingComboBox.currentIndexChanged.connect(lambda index: self.smoothingChanged.emit(index + 1))
        self.smoothingComboBox.currentIndexChanged.connect(self.requestEstimate)
        form.addRow('Smoothing:', self.smoothingComboBox)
        form.addRow('Iso level:', isoLevelSlider)
        form.addRow('Levels:', numIsoLevelsSpinBox)
        form.addRow('Style:', isoSetStyleComboBox)
        form.addRow('Opacity:', isoOpacitySlider)
        form.addRow('Opacity:', isoSetOpacitySlider)
        form.addRow('Opacity:', volumeOpacitySlider)
        form.addRow('Contrast:', volumeContrastSpinBox)
        form.addRow('Slices per voxel:', sliceDensitySpinBox)

        # Rows shown only for the plot types they apply to
        # (0: isosurface, 1: isosurface set, 2: volumetric)
        self.plotFormLayout = form
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

        self.addSection('Display', form)
        for key, widget in (('plotType', self.plotTypeComboBox), ('colormap', self.colormapComboBox),
                            ('colormapReversed', self.reverseColormapCheckBox), ('smoothing', self.smoothingComboBox),
                            ('isoLevel', isoLevelSlider),
                            ('isoLevels', numIsoLevelsSpinBox), ('isoSetStyle', isoSetStyleComboBox),
                            ('isoOpacity', isoOpacitySlider), ('isoSetOpacity', isoSetOpacitySlider),
                            ('volumeOpacity', volumeOpacitySlider), ('volumeContrast', volumeContrastSpinBox),
                            ('slicesPerVoxel', sliceDensitySpinBox)):
            self.remember(key, widget)

    def colormap(self):
        """The ColorMap chosen."""
        return makeColormap(self.colormapComboBox.currentText(), self.reverseColormapCheckBox.isChecked())

    def updateColormapIcons(self):
        reverse = self.reverseColormapCheckBox.isChecked()
        for index in range(self.colormapComboBox.count()):
            label = self.colormapComboBox.itemText(index)
            if label:   # not a separator
                self.colormapComboBox.setItemIcon(index, colormapIcon(makeColormap(label, reverse)))

    @Slot()
    def onColormapChanged(self, *args):
        self.updateColormapIcons()
        self.colormapChanged.emit(self.colormap())

    def buildViewSection(self):
        # View direction: basis, presets and custom direction / up vectors
        self.viewBasisComboBox = QComboBox()
        self.viewBasisComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.viewBasisComboBox.addItems(self.options.viewBases)
        self.viewBasisComboBox.setToolTip('Basis of the direction and up vectors:\n'
                                          'Cartesian: x, y, z\n'
                                          'Lattice [uvw]: u a + v b + w c\n'
                                          'Reciprocal (hkl): h a* + k b* + l c*, normal to the (hkl) planes')
        self.viewBasisComboBox.currentIndexChanged.connect(self.onViewBasisChanged)

        self.viewPresetComboBox = QComboBox()
        self.viewPresetComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
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
        applyViewButton.clicked.connect(self.applyView)

        centerViewButton = QPushButton('Center')
        centerViewButton.setToolTip('Center the view on the plotted cells')
        centerViewButton.clicked.connect(self.centerViewClicked)

        buttonsLayout = QHBoxLayout()
        buttonsLayout.addWidget(applyViewButton)
        buttonsLayout.addWidget(centerViewButton)
        buttonsLayout.addStretch(1)

        self.reverseViewCheckBox = QCheckBox('View from the opposite side')
        self.reverseViewCheckBox.setToolTip('Look along minus the direction, i.e. with it pointing towards the viewer')
        self.reverseViewCheckBox.setChecked(True)
        self.reverseViewCheckBox.toggled.connect(self.applyView)

        projectionCheckBox = QCheckBox('Orthographic projection')
        projectionCheckBox.setCheckState(Qt.CheckState.Checked)
        projectionCheckBox.checkStateChanged.connect(self.projectionChanged)

        self.viewStatusLabel = QLabel()
        self.viewStatusLabel.setStyleSheet('color: #e05050')
        self.viewStatusLabel.setWordWrap(True)
        self.viewStatusLabel.setVisible(False)

        form = formLayout()
        form.addRow('Basis:', self.viewBasisComboBox)
        form.addRow('Preset:', self.viewPresetComboBox)
        form.addRow('Direction:', viewDirLayout)
        form.addRow('Up:', viewUpLayout)
        form.addRow('', buttonsLayout)
        form.addRow(self.viewStatusLabel)
        form.addRow(self.reverseViewCheckBox)
        form.addRow(projectionCheckBox)

        # Lattice bases need the cell from the SAVE database
        self.setLatticeBasesEnabled(self.options.hasCell())
        self.options.databaseFound.connect(self.onDatabaseFound)

        self.populateViewPresets()
        self.viewPresetComboBox.setCurrentText('x + y + z')
        self.onViewPresetActivated(self.viewPresetComboBox.currentIndex(), apply=False)

        self.addSection('View', form)

        # Basis, then its presets, then the vectors (applied by afterRestore)
        def vector(lineEdits):
            def setVector(values):
                for lineEdit, value in zip(lineEdits, values):
                    lineEdit.setText(str(value))
            return dict(get=lambda: [lineEdit.text() for lineEdit in lineEdits], set=setVector)
        self.remember('viewBasis', self.viewBasisComboBox)
        self.remember('viewPreset', self.viewPresetComboBox)
        self.remember('viewDirection', **vector(self.viewDirLineEdits))
        self.remember('viewUp', **vector(self.viewUpLineEdits))
        self.remember('viewReversed', self.reverseViewCheckBox)
        self.remember('orthographic', projectionCheckBox)

    def buildStructureSection(self):
        visibilityLayout = QGridLayout()
        visibilityLayout.setContentsMargins(0, 0, 0, 0)
        for i, (text, signal, toolTip) in enumerate([
            ('Atoms', self.viewLatticeChanged, ''),
            ('Atom names', self.viewAtomNamesChanged, ''),
            ('Bonds', self.viewBondsChanged, 'Bonds crossing the supercell boundary are drawn up to their midpoint'),
            ('Cell boundaries', self.viewBoundariesChanged, ''),
        ]):
            box = QCheckBox(text)
            box.setChecked(True)
            box.setToolTip(toolTip)
            box.checkStateChanged.connect(signal)
            visibilityLayout.addWidget(box, i // 2, i % 2)
            self.remember(f'show/{text}', box)

        atomScaleSpinBox = QDoubleSpinBox(minimum=0.05, maximum=1.5, singleStep=0.05, decimals=2)
        atomScaleSpinBox.setValue(self.options.atomScale())
        atomScaleSpinBox.setToolTip('Atom radius as a fraction of its covalent radius\n'
                                    '(1: atoms bonded at their covalent radii touch)')
        atomScaleSpinBox.valueChanged.connect(self.setAtomScale)

        bondToleranceSpinBox = QDoubleSpinBox(minimum=0.5, maximum=2.0, singleStep=0.05, decimals=2)
        bondToleranceSpinBox.setValue(self.options.bondTolerance())
        bondToleranceSpinBox.setToolTip('Atoms are bonded when closer than this factor\n'
                                        'times the sum of their covalent radii')
        bondToleranceSpinBox.valueChanged.connect(self.setBondTolerance)

        bondRadiusSpinBox = QDoubleSpinBox(minimum=0.01, maximum=0.5, singleStep=0.01, decimals=2, suffix=' Å')
        bondRadiusSpinBox.setValue(self.options.bondRadius())
        bondRadiusSpinBox.valueChanged.connect(self.setBondRadius)

        bondColorComboBox = QComboBox()
        bondColorComboBox.addItems(['Atom colors', 'Uniform grey'])
        bondColorComboBox.setCurrentIndex(self.options.bondColoring())
        bondColorComboBox.setToolTip('Atom colors: each half of a bond in the color of its atom')
        bondColorComboBox.currentIndexChanged.connect(self.setBondColoring)

        for widget in (atomScaleSpinBox, bondToleranceSpinBox, bondRadiusSpinBox, bondColorComboBox):
            widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        form = formLayout()
        form.addRow(visibilityLayout)
        form.addRow('Atom radius scale:', atomScaleSpinBox)
        form.addRow('Bond tolerance:', bondToleranceSpinBox)
        form.addRow('Bond radius:', bondRadiusSpinBox)
        form.addRow('Bond color:', bondColorComboBox)
        self.addSection('Structure', form, expanded=False)
        for key, widget in (('atomRadiusScale', atomScaleSpinBox), ('bondTolerance', bondToleranceSpinBox),
                            ('bondRadius', bondRadiusSpinBox), ('bondColor', bondColorComboBox)):
            self.remember(key, widget)

    def buildAxesSection(self):
        layout = QGridLayout()
        for i, (text, signal, checked, tooltip) in enumerate([
            ('Cartesian x, y, z', self.showCartesianAxesChanged, True, 'Grey arrows in the axes gizmo'),
            ('Lattice a, b, c', self.showLatticeVectorsChanged, True, 'Red, green and blue arrows in the axes gizmo'),
            ('Reciprocal a*, b*, c*', self.showReciprocalVectorsChanged, False, 'Light red, green and blue arrows in the axes gizmo'),
            ('Axis labels', self.showAxisLabelsChanged, True, 'Labels at the tips of the gizmo arrows'),
            ('Cell parameters', self.showCellInfoChanged, True, 'Lattice constants and angles in the top-left corner'),
        ]):
            box = QCheckBox(text)
            box.setToolTip(tooltip)
            box.setChecked(checked)
            box.toggled.connect(signal)
            layout.addWidget(box, i // 2, i % 2)
            self.remember(f'axes/{text}', box)

        layout.addWidget(NoteLabel('Each set of arrows is scaled so that its longest vector has the same length.'), 3, 0, 1, 2)
        self.addSection('Axes', layout, expanded=False)

    def buildAnalysisSection(self):
        self.showAnalysisCheckBox = QCheckBox('Show the analysis panel')
        self.showAnalysisCheckBox.setToolTip('The Analysis panel: the density on a plane, and the distribution\n'
                                             'of distances from the fixed particle (exciton radius)')
        self.showAnalysisCheckBox.toggled.connect(self.analysisChanged)

        self.planeBasisComboBox = QComboBox()
        self.planeBasisComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.planeBasisComboBox.addItems(self.options.viewBases)
        self.planeBasisComboBox.setToolTip('Basis of the normal: Cartesian, lattice [uvw] or reciprocal (hkl),\n'
                                           'the last one giving the lattice plane (hkl)')
        self.planeBasisComboBox.currentIndexChanged.connect(self.onPlaneNormalEdited)

        self.planeNormalLineEdits = [self.newVectorLineEdit() for _ in range(3)]
        for lineEdit, value in zip(self.planeNormalLineEdits, ('0', '0', '1')):
            lineEdit.setText(value)
            lineEdit.editingFinished.connect(self.onPlaneNormalEdited)
        normalLayout = QHBoxLayout()
        for lineEdit in self.planeNormalLineEdits:
            normalLayout.addWidget(lineEdit)

        fromViewButton = QPushButton('Perpendicular to the view')
        fromViewButton.setToolTip('The plane of the screen: the cut is seen as the 3D view shows it')
        fromViewButton.clicked.connect(self.planeFromViewRequested)
        # Screen up when the normal was taken from the view: the cut is then
        # oriented as the view (cleared when the normal is edited)
        self.planeUpHint = None

        self.planeOffsetSpinBox = QDoubleSpinBox(minimum=-100.0, maximum=100.0, singleStep=0.1, decimals=2, suffix=' Å')
        self.planeOffsetSpinBox.setToolTip('Distance of the plane from the fixed particle, along its normal')
        self.planeOffsetSpinBox.valueChanged.connect(self.analysisChanged)

        self.planeAtomsSpinBox = QDoubleSpinBox(minimum=0.0, maximum=20.0, singleStep=0.1, decimals=1, suffix=' Å')
        self.planeAtomsSpinBox.setValue(1.0)
        self.planeAtomsSpinBox.setToolTip('Atoms closer than this to the plane are drawn on the cut')
        self.planeAtomsSpinBox.valueChanged.connect(self.analysisChanged)

        for widget in (self.planeOffsetSpinBox, self.planeAtomsSpinBox):
            widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self.showPlaneCheckBox = QCheckBox('Show the plane in the 3D view')
        self.showPlaneCheckBox.setChecked(True)
        self.showPlaneCheckBox.toggled.connect(self.analysisChanged)

        self.planeStatusLabel = QLabel()
        self.planeStatusLabel.setStyleSheet('color: #e05050')
        self.planeStatusLabel.setWordWrap(True)
        self.planeStatusLabel.hide()

        form = formLayout()
        form.addRow(self.showAnalysisCheckBox)
        form.addRow('Plane normal in:', self.planeBasisComboBox)
        form.addRow('Normal:', normalLayout)
        form.addRow('', fromViewButton)
        form.addRow(self.planeStatusLabel)
        form.addRow('Offset:', self.planeOffsetSpinBox)
        form.addRow('Atoms within:', self.planeAtomsSpinBox)
        form.addRow(self.showPlaneCheckBox)
        self.addSection('Analysis', form, expanded=False)

        def vector(lineEdits):
            def setVector(values):
                for lineEdit, value in zip(lineEdits, values):
                    lineEdit.setText(str(value))
            return dict(get=lambda: [lineEdit.text() for lineEdit in lineEdits], set=setVector)
        self.remember('showAnalysis', self.showAnalysisCheckBox)
        self.remember('planeBasis', self.planeBasisComboBox)
        self.remember('planeNormal', **vector(self.planeNormalLineEdits))
        self.remember('planeOffset', self.planeOffsetSpinBox)
        self.remember('planeAtoms', self.planeAtomsSpinBox)
        self.remember('showPlane', self.showPlaneCheckBox)

    @Slot()
    def onPlaneNormalEdited(self, *args):
        self.planeUpHint = None
        self.analysisChanged.emit()

    def setPlaneFromView(self, toViewer, up):
        """Plane of the screen: normal towards the viewer, oriented as the view."""
        self.planeBasisComboBox.blockSignals(True)
        self.planeBasisComboBox.setCurrentText('Cartesian')
        self.planeBasisComboBox.blockSignals(False)
        for lineEdit, value in zip(self.planeNormalLineEdits, toViewer):
            lineEdit.setText(f'{value + 0.0:.4f}')
        self.planeUpHint = list(up)
        self.analysisChanged.emit()

    def planeSettings(self):
        """
        The plane chosen: Cartesian normal, screen-up hint (or None), offset and
        atom distance (Bohr), and whether to show it in 3D. ValueError if invalid.
        """
        try:
            components = [float(e.text().replace(',', '.')) if e.text().strip() else 0.0 for e in self.planeNormalLineEdits]
        except ValueError:
            raise ValueError('Invalid number in the normal of the plane')
        if np.allclose(components, 0.0):
            raise ValueError('The normal of the plane must be a non-zero vector')
        normal = self.options.viewVectorToCartesian(components, self.planeBasisComboBox.currentText())
        return {'normal': np.asarray(normal, dtype=float), 'up': self.planeUpHint,
                'offset': self.planeOffsetSpinBox.value() * ANGSTROM_TO_BOHR,
                'atoms': self.planeAtomsSpinBox.value() * ANGSTROM_TO_BOHR,
                'show3D': self.showPlaneCheckBox.isChecked()}

    def showPlaneStatus(self, message):
        self.planeStatusLabel.setText(message)
        self.planeStatusLabel.setVisible(bool(message))

    def buildExportSection(self):
        imageButton = QPushButton('Image…')
        imageButton.setToolTip('Save the 3D view as an image, at any size (Ctrl+E)')
        imageButton.clicked.connect(self.exportImageRequested)

        self.exportDensityButton = QPushButton('Density…')
        self.exportDensityButton.setToolTip('Save the probability density with the atoms, as a Gaussian cube or\n'
                                            'XSF file for VESTA, VMD, XCrySDen, Ovito... (Ctrl+Shift+E)')
        self.exportDensityButton.setEnabled(False)
        self.exportDensityButton.clicked.connect(self.exportDensityRequested)
        self.calculations.wfComputed.connect(lambda: self.exportDensityButton.setEnabled(True))

        layout = QHBoxLayout()
        layout.addWidget(imageButton)
        layout.addWidget(self.exportDensityButton)
        layout.addStretch(1)
        self.addSection('Export', layout, expanded=False)

    def newCoordinateLineEdit(self):
        lineEdit = QLineEdit()
        lineEdit.setMaximumWidth(70)
        return lineEdit

    # Exciton

    @Slot(int, int, float)
    def onExcitonSelected(self, qIndex: int, excIndex: int, energy: float):
        for spinBox, value in ((self.qPointSpinBox, qIndex + 1), (self.excitonIndexSpinBox, excIndex)):
            spinBox.blockSignals(True)
            spinBox.setValue(value)
            spinBox.blockSignals(False)
        self.updateExcitonNote()
        self.requestEstimate()

    def qPointIndex(self):
        return self.qPointSpinBox.value() - 1

    @Slot()
    def updateExcitonNote(self):
        selected = self.calculations.selectedExciton
        if selected is not None and selected[:2] == (self.qPointIndex(), self.excitonIndexSpinBox.value()):
            self.excitonNote.setText(f'Selected in Spectra: E = {selected[2]:.4f} eV')
        else:
            self.excitonNote.setText('Click a bright exciton in an absorption spectrum to select it here.')

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
                lineEdit.setText(f'{value + 0.0:.4f}')   # + 0.0: no "-0.0000"

        particle = 'Hole' if calc.wfFixedParticle == 'h' else 'Electron'
        self.particleGridLabel.setText(f'{particle} position snapped to the nearest point of the wave-function grid '
                                       f'({calc.wfGrid[0]} × {calc.wfGrid[1]} × {calc.wfGrid[2]} points per cell).')
        self.particleGridLabel.show()
        self.fixedParticlePosChanged.emit()

    @Slot()
    def computeWf(self):
        q_index = self.qPointIndex()
        exc_index = self.excitonIndexSpinBox.value()
        fixed_particle = self.options.particleType()
        fixed_position = self.options.particlePosition()
        cutoff = self.cutoff()
        supercell = [self.xSupercellSpinBox.value(), self.ySupercellSpinBox.value(), self.zSupercellSpinBox.value()]

        if not self.confirmMemory():
            return False
        # k-points per block chosen to fit the available memory (see memory.chooseBlockSize)
        blockSize = self.lastEstimate['blockSize'] if self.lastEstimate else 256
        self.calculations.computeExcitonWaveFunction(block_size=blockSize, q_index=q_index, exc_index=exc_index, fixed_particle=fixed_particle, fixed_position=fixed_position, cutoff_ry=cutoff, supercell=supercell)
        return True

    def computeSelected(self):
        """Compute the exciton selected in the spectra, with the settings of the calculation; whether it started."""
        selected = self.calculations.selectedExciton
        if selected is None:
            return False
        self.onExcitonSelected(*selected)
        return self.computeWf()

    def cutoff(self):
        """Cutoff in Ry, or -1 for all the plane waves."""
        return -1 if self.fullCutoffCheckBox.isChecked() else self.wfCutoffSpinBox.value()

    def smoothingFactor(self):
        return self.smoothingComboBox.currentIndex() + 1

    # Size of the calculation

    @Slot()
    def requestEstimate(self, *args):
        self.estimateTimer.start()

    def estimate(self):
        """Grid and memory of the calculation as set (see Calculations.estimateWaveFunction)."""
        return self.estimateFor(self.qPointIndex(), self.excitonIndexSpinBox.value())

    def estimateFor(self, qIndex, excIndex):
        """Grid and memory of computing another exciton with the settings of the calculation."""
        return self.calculations.estimateWaveFunction(qIndex, excIndex, self.cutoff(), self.supercell(),
                                                      self.smoothingFactor())

    def describeMemory(self, estimate):
        """The memory of a calculation, as text, and whether it is likely too much for the memory available."""
        text = f'about {formatBytes(estimate["peak"])} at peak'
        if estimate['loaded']:
            text += ', the wave functions being already loaded'
        needed, available = self.memoryNeeded(estimate)
        warning = False
        if available is not None:
            text += f'; {formatBytes(available)} available'
            warning = needed > MEMORY_WARNING_FRACTION * available
        return text, warning

    @Slot()
    def updateEstimate(self):
        estimate = self.updateOwnEstimate()
        # The same calculation for the exciton selected in the spectra, unless it
        # is this one
        selected = self.calculations.selectedExciton
        same = selected is not None and selected[:2] == (self.qPointIndex(), self.excitonIndexSpinBox.value())
        self.updateSelectedEstimate(estimate if same else None)

    def updateOwnEstimate(self):
        """Show the estimate of the calculation as set; return it (None if there is none)."""
        try:
            estimate = self.estimate()
        except ValueError as error:
            self.lastEstimate = None
            self.showEstimate(str(error), warning=True)
            return None
        if estimate is None:
            if self.calculations.isBusy():
                return None   # estimated when the calculation ends
            self.lastEstimate = None
            self.showEstimate('')
            return None
        self.lastEstimate = estimate

        box, supercell = estimate['fftBox'], estimate['supercell']
        total = ' × '.join(str(n * s) for n, s in zip(box, supercell))
        states = f', {estimate["states"]} degenerate states' if estimate['states'] > 1 else ''
        memory, warning = self.describeMemory(estimate)
        text = (f'Grid: {box[0]} × {box[1]} × {box[2]} points per cell ({total} in the supercell{states}). '
                f'Memory: {memory}')
        self.showEstimate(('⚠ ' if warning else '') + text + '.', warning)
        return estimate

    def updateSelectedEstimate(self, estimate=None):
        """
        Emit selectedEstimateChanged with the memory of computing the exciton
        selected in the spectra with the settings of the calculation (`estimate`
        if already known).
        """
        selected = self.calculations.selectedExciton
        if selected is None:
            self.selectedEstimateChanged.emit('', False)
            return
        if estimate is None:
            try:
                estimate = self.estimateFor(selected[0], selected[1])
            except ValueError as error:
                self.selectedEstimateChanged.emit(str(error), True)
                return
            if estimate is None:
                if not self.calculations.isBusy():   # otherwise estimated when the calculation ends
                    self.selectedEstimateChanged.emit('', False)
                return
        memory, warning = self.describeMemory(estimate)
        particle = 'hole' if self.options.particleType() == 'h' else 'electron'
        cells = ' × '.join(str(n) for n in estimate['supercell'])
        cutoff = 'all plane waves' if self.cutoff() < 0 else f'cutoff {self.cutoff():g} Ry'
        states = f', {estimate["states"]} degenerate states' if estimate['states'] > 1 else ''
        text = (f'Memory: {memory}. With the settings of the Wave function controls: {particle} fixed, '
                f'supercell {cells}, {cutoff}{states}.')
        self.selectedEstimateChanged.emit(('⚠ ' if warning else '') + text, warning)

    def memoryNeeded(self, estimate):
        """Memory the calculation adds to what is in use (bytes), and the memory available (or None)."""
        memory = availableMemory()
        # Wave functions already loaded are in use already
        needed = estimate['peak'] - (estimate['wavefunctions'] if estimate['loaded'] else 0)
        return needed, (memory[1] if memory else None)

    def showEstimate(self, text, warning=False):
        self.estimateWarning = warning
        self.estimateNote.setText(text)
        self.estimateNote.setVisible(bool(text))
        self.estimateNote.setWarning(warning)

    def confirmMemory(self):
        """Ask before a calculation that likely does not fit in the available memory."""
        try:
            estimate = self.estimate()
        except ValueError:
            return True   # the calculation reports the error
        if estimate is None:
            return True
        self.lastEstimate = estimate   # its block size is used for the calculation
        needed, available = self.memoryNeeded(estimate)
        if available is None or needed <= MEMORY_WARNING_FRACTION * available:
            return True
        answer = QMessageBox.warning(
            self, 'Not enough memory?',
            f'This calculation needs about {formatBytes(needed)} more memory, and only {formatBytes(available)} '
            'are available: the computer may slow down a lot, or the program may be stopped.\n\n'
            'A lower cutoff, a smaller supercell or closing other programs would help. Compute anyway?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

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

    @Slot(float)
    def setAtomScale(self, scale: float):
        self.options.setAtomScale(scale)
        self.signalReplotLattice.emit()

    @Slot(float)
    def setBondTolerance(self, tolerance: float):
        self.options.setBondTolerance(tolerance)
        self.signalReplotLattice.emit()

    @Slot(float)
    def setBondRadius(self, radius: float):
        self.options.setBondRadius(radius)
        self.signalReplotLattice.emit()

    @Slot(int)
    def setBondColoring(self, mode: int):
        self.options.setBondColoring(mode)
        self.signalReplotLattice.emit()

    @Slot(int)
    def updatePlotTypeRows(self, plotType: int):
        for widget, plotTypes in self.plotTypeRows:
            self.plotFormLayout.setRowVisible(widget, plotType in plotTypes)

    def plotType(self):
        return self.plotTypeComboBox.currentIndex()

    def supercell(self):
        return [self.xSupercellSpinBox.value(), self.ySupercellSpinBox.value(), self.zSupercellSpinBox.value()]

    def setSupercell(self, sizes):
        """Set the three sizes at once: one redraw of the lattice."""
        spinBoxes = (self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox)
        for spinBox, size in zip(spinBoxes, sizes):
            spinBox.blockSignals(True)
            spinBox.setValue(int(size))
            spinBox.blockSignals(False)
        self.supercellChanged()

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
        self.supercellResized.emit()
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
