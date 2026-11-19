from PySide6.QtCore import Qt, Signal, Slot, QSize, QTimer
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import QPushButton, QSizePolicy, QSpinBox, QLineEdit, QGridLayout
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QCheckBox, QLabel, QDoubleSpinBox, QMessageBox, QWidget, QVBoxLayout
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QTabBar
import numpy as np

from visual_excitons.core.calculations import Calculations, sameStateSum, describeStateSum
from visual_excitons.core.dataset import Dataset
from visual_excitons.core.parameters import WavefunctionParameters
from visual_excitons.core.lattice_info import VIEW_BASES, VIEW_PRESETS, viewVectorToCartesian
from .inspector import Inspector, formLayout, ValueSlider, NoteLabel
from .persistence import DATASET
from .colormaps import COLORMAP_GROUPS, DEFAULT_COLORMAP, makeColormap, colormapIcon
from visual_excitons.core.cellshift import wrapShift
from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR
from visual_excitons.core.memory import availableMemory, formatBytes
from visual_excitons.core.placement import (densityShare, gridIndex, gridPosition, distinctMaxima, groupOf,
                                            directionText, nearestMember)
from visual_excitons.core.atomic_data import chemical_symbols

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

class WavefunctionControls(Inspector):
    plotTypeChanged = Signal(int)
    signalReplotLattice = Signal()
    # The supercell changed (not only redrawn): the view is centered again
    supercellResized = Signal()
    # The origin of the cell shown changed (see cellShift)
    cellShiftChanged = Signal()
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
    showCaptionChanged = Signal(bool)
    # The maxima of the particle density selected in the list (crystal coordinates of the unit cell), to mark
    maximaMarkersChanged = Signal(list)
    isoSetStyleChanged = Signal(int)
    exportImageRequested = Signal()
    colormapChanged = Signal(object)   # pyqtgraph ColorMap
    analysisChanged = Signal()
    smoothingChanged = Signal(int)   # display upsampling factor
    # A display setting of a density changed: its layer ('wf' or 'particle') and the setting (DISPLAY_KEYS)
    displayChanged = Signal(str, str)
    planeFromViewRequested = Signal()
    exportDensityRequested = Signal()

    def __init__(self, dataset: Dataset, parameters: WavefunctionParameters, calculations: Calculations):
        """The controls of the wave function of `dataset`, setting `parameters`."""
        Inspector.__init__(self)

        self.dataset = dataset
        self.parameters = parameters
        self.calculations = calculations
        self.calculations.wfComputed.connect(self.onWfComputed)
        self.calculations.excitonSelected.connect(self.onExcitonSelected)

        self.buildExcitonSection()
        self.buildCalculationSection()
        self.buildPlacementSection()
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
        self.qPointSpinBox = ChoiceSpinBox(minimum=1, maximum=max(1, self.dataset.nQpoints))
        self.qPointSpinBox.setToolTip('Q-point of the exciton: the file ndb.BS_diago_Q<n> of the BSE directory '
                                      '(only those computed)')
        self.dataset.numQPointsChanged.connect(
            lambda n: self.qPointSpinBox.choices is None and self.qPointSpinBox.setMaximum(max(1, n)))
        # Only the Q-points computed, which may be some of them (e.g. Q1, Q5, Q30)
        self.dataset.qPointsChanged.connect(lambda qPoints: self.qPointSpinBox.setChoices([q + 1 for q in qPoints]))
        if self.dataset.qPoints:
            self.qPointSpinBox.setChoices([q + 1 for q in self.dataset.qPoints])

        self.excitonIndexSpinBox = QSpinBox(minimum=1, maximum=99999)
        self.excitonIndexSpinBox.setToolTip('Index of the exciton at that Q-point, in increasing energy')

        for spinBox in (self.qPointSpinBox, self.excitonIndexSpinBox):
            spinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            spinBox.valueChanged.connect(self.updateExcitonNote)

        self.excitonNote = NoteLabel()
        # A copy of the Selected exciton section's checkbox, linked to it (Calculations.sumDegenerate;
        # remembered there): it decides which states a wave function sums
        from .spectra_controls import DEGENERATE_TIP
        self.sumDegenerateCheckBox = QCheckBox('Sum degenerate states')
        self.sumDegenerateCheckBox.setChecked(self.calculations.sumDegenerate)
        self.sumDegenerateCheckBox.setToolTip(DEGENERATE_TIP)
        self.sumDegenerateCheckBox.toggled.connect(self.calculations.setSumDegenerate)
        self.calculations.sumDegenerateChanged.connect(self.sumDegenerateCheckBox.setChecked)
        # The states the wave function shown sums, and whether it is with the setting of now
        self.wfStatesNote = NoteLabel()
        self.wfStatesNote.hide()
        self.calculations.wfComputed.connect(self.updateWfStatesNote)
        self.calculations.stateSumChanged.connect(self.updateWfStatesNote)

        form = formLayout()
        form.addRow('Q-point:', self.qPointSpinBox)
        form.addRow('Exciton:', self.excitonIndexSpinBox)
        form.addRow(self.excitonNote)
        form.addRow(self.sumDegenerateCheckBox)
        form.addRow(self.wfStatesNote)
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
        self.particleComputedWidget = QWidget()
        self.particleComputedWidget.setLayout(particleLayout)
        particleLayout.setContentsMargins(0, 0, 0, 0)

        # The same position as shown, with the cell origin (and layer centring)
        # applied: only while there is a shift; linked to the one computed
        self.shownParticleLineEdits = [self.newCoordinateLineEdit() for _ in range(3)]
        shownLayout = QHBoxLayout()
        shownLayout.setContentsMargins(0, 0, 0, 0)
        for lineEdit in self.shownParticleLineEdits:
            lineEdit.setValidator(QDoubleValidator(0.0, 1.0, 4))
            lineEdit.setToolTip('Where the particle is drawn: crystal coordinates with the cell origin applied.\n'
                                'Editing them sets the position computed (below) accordingly')
            lineEdit.editingFinished.connect(self.shownPositionEdited)
            shownLayout.addWidget(lineEdit)
        self.particleShownWidget = QWidget()
        self.particleShownWidget.setLayout(shownLayout)
        # The shift of what is shown (WavefunctionPanels sets it: snapped to the wave function's grid)
        self.shiftProvider = self.cellShift

        # Supercell: odd sizes only
        self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox = (QSpinBox(minimum=1, maximum=999, singleStep=2) for _ in range(3))
        supercellLayout = QHBoxLayout()
        for spinBox in (self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox):
            spinBox.setValue(1)
            spinBox.setToolTip('Odd sizes only: the fixed particle is placed in the central cell')
            spinBox.valueChanged.connect(self.supercellChanged)
            supercellLayout.addWidget(spinBox)
        supercellLayout.addStretch(1)

        # Three decimals: shells of G-vectors can be a few meV apart
        self.wfCutoffSpinBox = QDoubleSpinBox(minimum=0.1, maximum=10000.0, singleStep=1.0, decimals=3, suffix=' Ry')
        self.wfCutoffSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.wfCutoffSpinBox.setValue(self.parameters.cutoff)
        self.wfCutoffSpinBox.setToolTip('Plane-wave cutoff of the wave function: higher values give a finer real-space grid')
        self.wfCutoffSpinBox.valueChanged.connect(lambda cutoff: setattr(self.parameters, 'cutoff', cutoff))
        # The same cutoff as a count of reciprocal lattice vectors (Yambo's RL), linked to it
        self.gShells = None
        self.lastRl = 0
        self.wfCutoffRlSpinBox = QSpinBox(minimum=1, maximum=1)
        self.wfCutoffRlSpinBox.setSuffix(' RL')
        self.wfCutoffRlSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.wfCutoffRlSpinBox.setToolTip('The cutoff as a number of reciprocal lattice vectors (G-vectors), as Yambo '
                                          'counts them (RL): the plane waves\nat Γ. Rounded to complete shells of '
                                          'G-vectors of the same length; the arrows go from shell to shell')
        self.wfCutoffRlSpinBox.setEnabled(False)
        self.wfCutoffSpinBox.valueChanged.connect(self.cutoffRyChanged)
        self.wfCutoffRlSpinBox.valueChanged.connect(self.cutoffRlChanged)

        self.fullCutoffCheckBox = QCheckBox('All plane waves')
        self.fullCutoffCheckBox.setToolTip('No cutoff: all the plane waves of the wave functions in the SAVE database,\n'
                                           'the finest grid possible (and the most memory)')
        self.fullCutoffCheckBox.toggled.connect(self.wfCutoffSpinBox.setDisabled)
        self.fullCutoffCheckBox.toggled.connect(lambda full: self.wfCutoffRlSpinBox.setEnabled(
            not full and self.gShells is not None))

        cutoffLayout = QHBoxLayout()
        cutoffLayout.addWidget(self.wfCutoffSpinBox)
        cutoffLayout.addWidget(self.wfCutoffRlSpinBox)
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
                       self.dataset.databaseFound, self.dataset.diagoDirChanged,
                       self.calculations.stateSumChanged):      # the number of states summed
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
        form.addRow('Position as shown:', self.particleShownWidget)
        form.addRow('Position (a, b, c):', self.particleComputedWidget)
        self.calculationForm = form
        # Spanning both columns, so the wrapped text has the full width of the form
        form.addRow(self.particleGridLabel)
        form.addRow('Supercell:', supercellLayout)
        form.addRow('Cutoff:', cutoffLayout)
        self.atMaximumCheckBox = QCheckBox('Fix the particle at its density maximum')
        self.atMaximumCheckBox.setChecked(True)
        self.atMaximumCheckBox.setToolTip('For a new exciton (or particle, cutoff, degenerate setting), compute the '
                                          'density of the fixed particle first and put it at its largest maximum.\n'
                                          'A position chosen afterwards, while that density stays current, is kept')
        form.addRow(self.atMaximumCheckBox)
        form.addRow(computeWfButton)
        form.addRow(self.estimateNote)
        self.addSection('Calculation', form)
        self.remember('atMaximum', self.atMaximumCheckBox)
        # Waiting for the particle density to compute the wave function at its maximum (see computeWf)
        self.pendingWaveFunction = False

        # Both positions, before the particle type that shows one of them
        def positionSetter(particle):
            return lambda value: self.parameters.setPosition([float(x) for x in value][:3], particle)
        self.remember('holePosition', scope=DATASET, get=lambda: list(self.parameters.holePosition), set=positionSetter('h'))
        self.remember('electronPosition', scope=DATASET, get=lambda: list(self.parameters.electronPosition), set=positionSetter('e'))
        self.remember('fixedParticle', self.particleTypeComboBox, DATASET)
        self.remember('supercell', scope=DATASET, get=self.supercell, set=self.setSupercell)
        self.remember('cutoff', self.wfCutoffSpinBox, DATASET)
        self.remember('fullCutoff', self.fullCutoffCheckBox, DATASET)
        self.cellShiftChanged.connect(self.updateShownPosition)
        self.fixedParticlePosChanged.connect(self.updateShownPosition)
        self.updateShownPosition()

    def buildPlacementSection(self):
        """The own density of the fixed particle: how good its position is, and where it is largest."""
        self.computeDensityButton = QPushButton()
        self.computeDensityButton.clicked.connect(self.computeParticleDensity)
        self.placeHereButton = QPushButton('Place here')
        self.placeHereButton.setToolTip('Put the fixed particle at the maximum selected in the list (of its copies, the '
                                        'one nearest its position): a point of the grid of the wave function')
        self.placeHereButton.clicked.connect(self.placeAtSelected)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self.showMaximaCheckBox = QCheckBox('Mark in the 3D view')
        self.showMaximaCheckBox.setChecked(True)
        self.showMaximaCheckBox.setToolTip('Mark the copies of the maximum selected in the list in the 3D view')
        self.showMaximaCheckBox.toggled.connect(self.onMaximumSelected)
        buttons.addWidget(self.computeDensityButton)
        buttons.addWidget(self.placeHereButton)
        buttons.addWidget(self.showMaximaCheckBox)
        buttons.addStretch(1)
        self.densityExplanation = NoteLabel()
        self.densityReadout = NoteLabel()
        # The distinct maxima of the density (equivalent ones once), the largest first
        self.maximaTable = QTableWidget(0, 6)
        self.maximaTable.setHorizontalHeaderLabels(['', 'Density', 'Near', 'Distance', 'Direction from the atom',
                                                    'Copies'])
        self.maximaTable.verticalHeader().hide()
        self.maximaTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.maximaTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.maximaTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.maximaTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.maximaTable.horizontalHeader().setStretchLastSection(True)
        self.maximaTable.setToolTip('The maxima of the density, equivalent ones (by symmetry) counted once. Select one to '
                                    'see its copies in the 3D view; double-click it, or Place here, to put the particle '
                                    'there. ● marks the one the particle is at')
        self.maximaTable.itemSelectionChanged.connect(self.onMaximumSelected)
        self.maximaTable.cellDoubleClicked.connect(lambda row, column: self.placeAtSelected())
        self.maximaGroups, self.maximaDensity = [], None
        form = formLayout()
        form.addRow(self.densityExplanation)
        form.addRow(buttons)
        form.addRow(self.densityReadout)
        form.addRow(self.maximaTable)
        self.addSection('Placing the fixed particle', form)
        self.remember('showMaxima', self.showMaximaCheckBox)
        self.calculations.particleDensityReady.connect(self.onDensityForWaveFunction)
        self.calculations.errorOccurred.connect(self.dropPendingWaveFunction)
        self.calculations.taskCancelled.connect(self.dropPendingWaveFunction)
        # Whatever changes the density asked for, or the position it is read at
        for signal in (self.particleTypeComboBox.currentIndexChanged, self.qPointSpinBox.valueChanged,
                       self.excitonIndexSpinBox.valueChanged, self.wfCutoffSpinBox.valueChanged,
                       self.fullCutoffCheckBox.toggled, self.fixedParticlePosChanged,
                       self.calculations.particleDensityReady, self.calculations.stateSumChanged,
                       self.calculations.wfComputed):
            signal.connect(self.updateDensityReadout)
        self.dataset.databaseFound.connect(self.updateDensityReadout)
        self.updateDensityReadout()

    def particleNames(self):
        """The fixed particle and the other one: ('hole', 'electron') or ('electron', 'hole')."""
        return ('hole', 'electron') if self.parameters.particle == 'h' else ('electron', 'hole')

    def densityRequest(self):
        """What the density would be computed for now: Q-point, exciton, particle, cutoff (and states summed, see currentDensity)."""
        return (self.qPointIndex(), self.excitonIndexSpinBox.value(), self.parameters.particle, float(self.cutoff()))

    def currentDensity(self):
        """The particle density computed, if it is the one asked for now; else None."""
        d = self.calculations.particleDensity
        if d is None:
            return None
        computed = (d['qIndex'], d['excIndex'], d['particle'], float(d['cutoff']))
        return d if computed == self.densityRequest() and sameStateSum(d, self.calculations.stateSum()) else None

    @Slot()
    def computeParticleDensity(self):
        q, exc, particle, cutoff = self.densityRequest()
        self.calculations.computeParticleDensity(q, exc, particle, cutoff)

    @Slot()
    def updateDensityReadout(self, *args):
        fixed, other = self.particleNames()
        self.computeDensityButton.setText(f'Compute the {fixed} density')
        self.computeDensityButton.setEnabled(bool(self.dataset.saveDir and self.dataset.diagoDir))
        self.densityExplanation.setText(
            f'The {fixed} density: where the {fixed} is, wherever the {other} is. Where it is small, the {other}\'s '
            f'density computed is weak and noisy; for bands of p or d character it vanishes on the atoms.')
        d = self.currentDensity()
        self.updateMaximaTable(d)
        if d is None:
            old = self.calculations.particleDensity
            if old is None:
                self.densityReadout.setText('Not computed yet.')
            else:
                name = 'hole' if old['particle'] == 'h' else 'electron'
                cutoff = 'all plane waves' if old['cutoff'] < 0 else f'{old["cutoff"]:g} Ry'
                self.densityReadout.setText(f'Out of date: computed for the {name} of exciton {old["excIndex"]} at '
                                            f'Q{old["qIndex"] + 1} ({cutoff}{describeStateSum(old, [old["excIndex"]])}). '
                                            'Compute it again for the settings of now.')
            return
        density = np.asarray(d['density'])
        share = densityShare(density, self.parameters.position())
        text = f'{fixed.capitalize()} density here: <b>{100 * share:.0f} %</b> of its largest'
        if len(d['states']) > 1:
            text += f'; states {d["states"][0]}–{d["states"][-1]} summed'
        self.densityReadout.setText(text + '.')

    def updateMaximaTable(self, d):
        """The distinct maxima of the density `d` (None: not current), and which one the particle is at."""
        density = None if d is None else np.asarray(d['density'])
        if density is not self.maximaDensity:
            self.maximaDensity = density
            self.maximaGroups = []
            if density is not None and self.dataset.hasCell():
                layer = self.layer[0] if getattr(self, 'layer', None) is not None else None
                self.maximaGroups = distinctMaxima(density, d['maxima'], self.dataset.cell,
                                                   self.dataset.atomicPositions, self.dataset.atomicNumbers, layer)
            self.maximaTable.blockSignals(True)
            self.maximaTable.clearSelection()
            self.maximaTable.setRowCount(len(self.maximaGroups))
            for row, g in enumerate(self.maximaGroups):
                cells = ['', f'{100 * g["share"]:.0f} %', chemical_symbols[g['element']], f'{g["distance"]:.2f} Å',
                         directionText(g, chemical_symbols), f'×{len(g["members"])}']
                for column, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if column in (1, 3, 5):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.maximaTable.setItem(row, column, item)
            self.maximaTable.blockSignals(False)
            self.onMaximumSelected()
        self.maximaTable.setVisible(bool(self.maximaGroups))
        self.placeHereButton.setVisible(bool(self.maximaGroups))
        self.showMaximaCheckBox.setVisible(bool(self.maximaGroups))
        self.placeHereButton.setEnabled(bool(self.maximaTable.selectedItems()))
        if self.maximaGroups:
            here = groupOf(self.maximaGroups, gridIndex(self.parameters.position(), density.shape))
            for row in range(self.maximaTable.rowCount()):
                self.maximaTable.item(row, 0).setText('●' if row == here else '')
            self.maximaTable.setFixedHeight(self.maximaTable.horizontalHeader().height()
                                            + sum(self.maximaTable.rowHeight(r) for r in range(min(6, len(self.maximaGroups))))
                                            + 2 * self.maximaTable.frameWidth())

    def selectedMaximum(self):
        rows = {item.row() for item in self.maximaTable.selectedItems()}
        return self.maximaGroups[rows.pop()] if len(rows) == 1 and self.maximaGroups else None

    @Slot()
    def onMaximumSelected(self):
        g = self.selectedMaximum()
        self.placeHereButton.setEnabled(g is not None)
        shape = None if self.maximaDensity is None else self.maximaDensity.shape
        marked = g is not None and self.showMaximaCheckBox.isChecked()
        self.maximaMarkersChanged.emit([gridPosition(i, shape) for i in g['members']] if marked else [])

    def placeAt(self, group):
        """Put the particle at the copy of the maximum `group` nearest its position."""
        index = nearestMember(group, self.parameters.position(), self.maximaDensity.shape, self.dataset.cell)
        for lineEdit, value in zip((self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit),
                                   gridPosition(index, self.maximaDensity.shape)):
            lineEdit.setText(f'{value + 0.0:.4f}')
        self.particlePositionChanged()

    @Slot()
    def placeAtSelected(self):
        g = self.selectedMaximum()
        if g is not None and self.currentDensity() is not None:
            self.placeAt(g)

    @Slot()
    def placeAtMaximum(self):
        """Put the particle at the largest maximum of its density (if current)."""
        d = self.currentDensity()
        self.updateMaximaTable(d)
        if d is not None and self.maximaGroups:
            self.placeAt(self.maximaGroups[0])

    @Slot()
    def onDensityForWaveFunction(self, *args):
        """
        A particle density computed: with 'Fix the particle at its density
        maximum', the particle goes to its maximum (whichever button computed
        it; not one restored from a session or the kept results, which comes
        with its own position), and the wave function asked for by computeWf
        follows.
        """
        pending, self.pendingWaveFunction = self.pendingWaveFunction, False
        if self.currentDensity() is None:          # not the one asked for now (or the settings changed meanwhile)
            return
        if self.atMaximumCheckBox.isChecked() and not self.calculations.restoringResults:
            self.placeAtMaximum()
        if pending:
            self.computeWf()

    @Slot()
    def dropPendingWaveFunction(self, *args):
        self.pendingWaveFunction = False

    # The densities drawn, each with its own settings (DisplaySettings): the Display section shows those of
    # the tab chosen. Setting keys as kept between sessions (the wave function's unchanged; the particle
    # density's prefixed with 'particleDisplay/'), and their widgets' values
    PLOT_TYPES = ['Isosurface', 'Isosurface set', 'Volumetric']
    SMOOTHINGS = ['None', '2×', '3×']
    ISO_SET_STYLES = ['Lit, edges emphasized', 'Edges only (x-ray)']
    LAYERS = ['wf', 'particle']

    def buildDisplaySection(self):
        self.isoLevelTickMax = 1000
        self.opacityTickMax = 1000

        def fraction(tickMax):
            return lambda tick: f'{tick / tickMax:.2f}'

        self.displayTabBar = QTabBar()
        self.displayTabBar.addTab('Wave function')
        self.displayTabBar.addTab('Hole density')
        self.displayTabBar.setDocumentMode(True)
        self.displayTabBar.setExpanding(False)
        self.displayTabBar.setToolTip('The density whose settings are shown: the wave function\'s, or the fixed '
                                      'particle\'s own (Placing the fixed particle)')
        self.showDensityCheckBox = QCheckBox('Show in the 3D view')

        self.plotTypeComboBox = QComboBox()
        self.plotTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.plotTypeComboBox.addItems(self.PLOT_TYPES)

        self.isoLevelSlider = ValueSlider(0, self.isoLevelTickMax, 500, fraction(self.isoLevelTickMax))
        self.isoLevelSlider.setToolTip('Density of the isosurface, relative to its maximum')
        self.numIsoLevelsSpinBox = QSpinBox(minimum=1, maximum=999)
        self.numIsoLevelsSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.isoSetStyleComboBox = QComboBox()
        self.isoSetStyleComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.isoSetStyleComboBox.addItems(self.ISO_SET_STYLES)
        self.isoSetStyleComboBox.setToolTip('Shading of the isosurface set')
        self.isoOpacitySlider = ValueSlider(0, self.opacityTickMax, 300, fraction(self.opacityTickMax))
        self.isoSetOpacitySlider = ValueSlider(0, self.opacityTickMax, 100, fraction(self.opacityTickMax))
        self.volumeOpacitySlider = ValueSlider(0, self.opacityTickMax, 800, fraction(self.opacityTickMax))
        self.volumeOpacitySlider.setToolTip('Opacity along the densest line of sight through the density')
        self.volumeContrastSpinBox = QDoubleSpinBox(minimum=0.1, maximum=10.0, singleStep=0.1, decimals=2)
        self.volumeContrastSpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.volumeContrastSpinBox.setToolTip('Power applied to the density for the opacity:\n'
                                              'above 1 fades low densities so the core stands out,\n'
                                              'below 1 brings out the low-density tails')
        self.sliceDensitySpinBox = QSpinBox(minimum=1, maximum=999)
        self.sliceDensitySpinBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.sliceDensitySpinBox.setToolTip('Rendering quality: more slices give a smoother volume')

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
        self.colormapComboBox.setToolTip('Colors of the density, from low to high')
        self.reverseColormapCheckBox = QCheckBox('Reverse')
        self.reverseColormapCheckBox.setToolTip('High densities in the colors of low ones and vice versa')
        colormapLayout = QHBoxLayout()
        colormapLayout.addWidget(self.colormapComboBox)
        colormapLayout.addWidget(self.reverseColormapCheckBox)
        colormapLayout.addStretch(1)

        self.smoothingComboBox = QComboBox()
        self.smoothingComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.smoothingComboBox.addItems(self.SMOOTHINGS)
        self.smoothingComboBox.setToolTip('Display the density on a grid 2 or 3 times finer, interpolated smoothly:\n'
                                          'smoother isosurfaces and volume, with no new physical detail\n'
                                          '(that needs a higher cutoff). Analysis and exports use the real grid.')

        form = formLayout()
        form.addRow(self.displayTabBar)
        form.addRow(self.showDensityCheckBox)
        form.addRow('Plot type:', self.plotTypeComboBox)
        form.addRow('Colormap:', colormapLayout)
        form.addRow('Smoothing:', self.smoothingComboBox)
        form.addRow('Iso level:', self.isoLevelSlider)
        form.addRow('Levels:', self.numIsoLevelsSpinBox)
        form.addRow('Style:', self.isoSetStyleComboBox)
        form.addRow('Opacity:', self.isoOpacitySlider)
        form.addRow('Opacity:', self.isoSetOpacitySlider)
        form.addRow('Opacity:', self.volumeOpacitySlider)
        form.addRow('Contrast:', self.volumeContrastSpinBox)
        form.addRow('Slices per voxel:', self.sliceDensitySpinBox)

        # Rows shown only for the plot types they apply to (0: isosurface, 1: isosurface set, 2: volumetric)
        self.plotFormLayout = form
        self.plotTypeRows = [
            (self.isoLevelSlider, {0}),
            (self.numIsoLevelsSpinBox, {1}),
            (self.isoSetStyleComboBox, {1}),
            (self.isoOpacitySlider, {0}),
            (self.isoSetOpacitySlider, {1}),
            (self.volumeOpacitySlider, {2}),
            (self.volumeContrastSpinBox, {2}),
            (self.sliceDensitySpinBox, {2}),
        ]
        self.addSection('Display', form)

        # Each setting: (key, widget, its widget's value from the field, the field from the widget's value)
        ticks = lambda tickMax: (lambda value: round(value * tickMax), lambda tick: float(tick) / tickMax)
        self.displaySettings = [
            ('show', 'shown', self.showDensityCheckBox, bool, bool),
            ('plotType', 'plotType', self.plotTypeComboBox, lambda i: self.PLOT_TYPES[i], self.PLOT_TYPES.index),
            ('colormap', 'colormap', self.colormapComboBox, str, str),
            ('colormapReversed', 'reversed', self.reverseColormapCheckBox, bool, bool),
            ('smoothing', 'smoothing', self.smoothingComboBox, lambda f: self.SMOOTHINGS[f - 1],
             lambda text: self.SMOOTHINGS.index(text) + 1),
            ('isoLevel', 'isoLevel', self.isoLevelSlider, *ticks(self.isoLevelTickMax)),
            ('isoLevels', 'numIsoLevels', self.numIsoLevelsSpinBox, int, int),
            ('isoSetStyle', 'isoSetStyle', self.isoSetStyleComboBox, lambda i: self.ISO_SET_STYLES[i],
             self.ISO_SET_STYLES.index),
            ('isoOpacity', 'isoOpacity', self.isoOpacitySlider, *ticks(self.opacityTickMax)),
            ('isoSetOpacity', 'isoSetOpacity', self.isoSetOpacitySlider, *ticks(self.opacityTickMax)),
            ('volumeOpacity', 'volumeOpacity', self.volumeOpacitySlider, *ticks(self.opacityTickMax)),
            ('volumeContrast', 'volumeContrast', self.volumeContrastSpinBox, float, float),
            ('slicesPerVoxel', 'sliceDensity', self.sliceDensitySpinBox, int, int),
        ]
        self.loadingDisplay = False
        for key, name, widget, toWidget, toField in self.displaySettings:
            self.widgetChangeSignal(widget).connect(lambda *args, key=key: self.onDisplayWidgetChanged(key))
        self.colormapComboBox.currentIndexChanged.connect(self.updateColormapIcons)
        self.reverseColormapCheckBox.toggled.connect(self.updateColormapIcons)
        self.plotTypeComboBox.currentIndexChanged.connect(self.updatePlotTypeRows)
        self.displayTabBar.currentChanged.connect(lambda index: self.loadDisplayWidgets())
        self.calculations.particleDensityReady.connect(self.updateDisplayTabs)
        self.particleTypeComboBox.currentIndexChanged.connect(self.updateDisplayTabs)
        self.loadDisplayWidgets()

        # Kept between sessions: each density's settings, whichever tab is shown
        for layer in self.LAYERS:
            for key, name, widget, toWidget, toField in self.displaySettings:
                stored = key if layer == 'wf' else f'particleDisplay/{key}'
                self.remember(stored, get=lambda layer=layer, name=name, toWidget=toWidget:
                              toWidget(getattr(self.parameters.display[layer], name)),
                              set=lambda value, layer=layer, key=key: self.setDisplayValue(layer, key, value))

    @staticmethod
    def widgetChangeSignal(widget):
        if isinstance(widget, QCheckBox):
            return widget.toggled
        if isinstance(widget, QComboBox):
            return widget.currentIndexChanged
        if isinstance(widget, ValueSlider):
            return widget.valueChanged
        return widget.valueChanged

    @staticmethod
    def widgetValue(widget):
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, ValueSlider):
            return widget.slider.value()
        return widget.value()

    @staticmethod
    def setWidgetValue(widget, value):
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QComboBox):
            if widget.findText(str(value)) >= 0:
                widget.setCurrentText(str(value))
        elif isinstance(widget, ValueSlider):
            widget.slider.setValue(int(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        else:
            widget.setValue(int(value))

    def displayLayer(self):
        """The density whose settings the Display section shows: 'wf' or 'particle'."""
        return self.LAYERS[max(0, self.displayTabBar.currentIndex())]

    def loadDisplayWidgets(self):
        """Show the settings of the density of the tab chosen."""
        settings = self.parameters.display[self.displayLayer()]
        self.loadingDisplay = True
        try:
            for key, name, widget, toWidget, toField in self.displaySettings:
                self.setWidgetValue(widget, toWidget(getattr(settings, name)))
        finally:
            self.loadingDisplay = False
        self.updatePlotTypeRows(settings.plotType)
        self.updateColormapIcons()
        self.updateDisplayTabs()

    @Slot()
    def updateDisplayTabs(self, *args):
        """The particle density's tab, named after its particle; it can be shown once computed."""
        d = self.calculations.particleDensity
        particle = d['particle'] if d is not None else self.parameters.particle
        name = 'Hole density' if particle == 'h' else 'Electron density'
        self.displayTabBar.setTabText(1, name)
        for combo in (getattr(self, 'cutDensityComboBox', None), getattr(self, 'exportDensityComboBox', None)):
            if combo is not None:
                combo.setItemText(1, name)
        particleTab = self.displayLayer() == 'particle'
        self.showDensityCheckBox.setEnabled(not particleTab or d is not None)
        self.showDensityCheckBox.setToolTip('Compute it first (Placing the fixed particle)' if particleTab and d is None
                                            else 'Draw this density in the 3D view, with or without the other')

    def onDisplayWidgetChanged(self, key):
        """A widget of the Display section edited: the setting of the density of the tab chosen."""
        if self.loadingDisplay:
            return
        widget = next(w for k, n, w, tw, tf in self.displaySettings if k == key)
        self.setDisplayValue(self.displayLayer(), key, self.widgetValue(widget), fromWidget=True)

    def setDisplayValue(self, layer, key, value, fromWidget=False):
        """Set a display setting of `layer` from its widget's value; its widget follows if its tab is shown."""
        key, name, widget, toWidget, toField = next(entry for entry in self.displaySettings if entry[0] == key)
        try:
            field = toField(value)
        except (ValueError, TypeError):
            return                              # e.g. a name no longer offered
        setattr(self.parameters.display[layer], name, field)
        if not fromWidget and layer == self.displayLayer():
            self.loadingDisplay = True
            try:
                self.setWidgetValue(widget, value)
            finally:
                self.loadingDisplay = False
            if key == 'plotType':
                self.updatePlotTypeRows(field)
            if key in ('colormap', 'colormapReversed'):
                self.updateColormapIcons()
        self.displayChanged.emit(layer, key)
        if layer == 'wf':
            self.emitWaveFunctionDisplay(key)

    def emitWaveFunctionDisplay(self, key):
        """The signals of the wave function's display, as before the particle density had its own."""
        d = self.parameters.display['wf']
        if key == 'plotType':
            self.plotTypeChanged.emit(d.plotType)
        elif key in ('colormap', 'colormapReversed'):
            self.colormapChanged.emit(self.colormap())
        elif key == 'smoothing':
            self.smoothingChanged.emit(d.smoothing)
            self.requestEstimate()
        elif key == 'isoLevel':
            self.isoLevelChanged.emit()
        elif key == 'isoLevels':
            self.numIsoLevelsChanged.emit()
        elif key == 'isoSetStyle':
            self.isoSetStyleChanged.emit(d.isoSetStyle)
        elif key == 'isoOpacity':
            self.isoOpacityChanged.emit(d.isoOpacity, d.isoLevel)
        elif key == 'isoSetOpacity':
            self.isoSetOpacityChanged.emit(d.isoSetOpacity)
        elif key == 'slicesPerVoxel':
            self.sliceDensityChanged.emit()
        elif key in ('volumeOpacity', 'volumeContrast'):
            self.volumeParametersChanged.emit()

    def colormap(self, layer='wf'):
        """The ColorMap chosen for a density."""
        settings = self.parameters.display[layer]
        return makeColormap(settings.colormap, settings.reversed)

    def updateColormapIcons(self, *args):
        reverse = self.reverseColormapCheckBox.isChecked()
        for index in range(self.colormapComboBox.count()):
            label = self.colormapComboBox.itemText(index)
            if label:   # not a separator
                self.colormapComboBox.setItemIcon(index, colormapIcon(makeColormap(label, reverse)))

    def buildViewSection(self):
        # View direction: basis, presets and custom direction / up vectors
        self.viewBasisComboBox = QComboBox()
        self.viewBasisComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.viewBasisComboBox.addItems(VIEW_BASES)
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
        self.setLatticeBasesEnabled(self.dataset.hasCell())
        self.dataset.databaseFound.connect(self.onDatabaseFound)

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
        atomScaleSpinBox.setValue(self.parameters.atomScale)
        atomScaleSpinBox.setToolTip('Atom radius as a fraction of its covalent radius\n'
                                    '(1: atoms bonded at their covalent radii touch)')
        atomScaleSpinBox.valueChanged.connect(self.setAtomScale)

        bondToleranceSpinBox = QDoubleSpinBox(minimum=0.5, maximum=2.0, singleStep=0.05, decimals=2)
        bondToleranceSpinBox.setValue(self.parameters.bondTolerance)
        bondToleranceSpinBox.setToolTip('Atoms are bonded when closer than this factor\n'
                                        'times the sum of their covalent radii')
        bondToleranceSpinBox.valueChanged.connect(self.setBondTolerance)

        bondRadiusSpinBox = QDoubleSpinBox(minimum=0.01, maximum=0.5, singleStep=0.01, decimals=2, suffix=' Å')
        bondRadiusSpinBox.setValue(self.parameters.bondRadius)
        bondRadiusSpinBox.valueChanged.connect(self.setBondRadius)

        bondColorComboBox = QComboBox()
        bondColorComboBox.addItems(['Atom colors', 'Uniform grey'])
        bondColorComboBox.setCurrentIndex(self.parameters.bondColoring)
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
        self.buildCellOriginRows(form)
        self.addSection('Structure', form, expanded=False)
        for key, widget in (('atomRadiusScale', atomScaleSpinBox), ('bondTolerance', bondToleranceSpinBox),
                            ('bondRadius', bondRadiusSpinBox), ('bondColor', bondColorComboBox)):
            self.remember(key, widget)
        # With each dataset: its layer centred or not, and its origin (the layer first: it fixes one axis)
        self.remember('centreLayer', self.centreLayerCheckBox, scope=DATASET)
        self.remember('cellOrigin', scope=DATASET, get=self.cellOrigin, set=self.setCellOrigin)

    def buildCellOriginRows(self, form):
        """
        Which part of the periodic crystal is shown: the origin of the cell, in
        fractions of a, b, c (core/cellshift.py), and the centring of a layer.
        """
        self.layer = None              # (axis, shift) of the vacuum of a layered cell, if any
        self.centreLayerCheckBox = QCheckBox('Centre the layer in the cell')
        self.centreLayerCheckBox.setChecked(True)
        self.centreLayerCheckBox.setToolTip('A layer computed with vacuum around it may sit on a face of the cell,\n'
                                            'and be drawn in two halves: put the vacuum on the faces instead')
        self.centreLayerCheckBox.toggled.connect(self.updateLayerCentring)
        self.centreLayerCheckBox.setEnabled(False)

        self.originSpinBoxes = []
        originRow = QHBoxLayout()
        originRow.setContentsMargins(0, 0, 0, 0)
        for axis in 'abc':
            spinBox = QDoubleSpinBox(minimum=-0.5, maximum=0.5, singleStep=0.05, decimals=3)
            spinBox.setPrefix(f'{axis} ')
            spinBox.setKeyboardTracking(False)
            spinBox.setToolTip('Shift of what is shown along this lattice vector, in fractions of it: the atoms and the\n'
                               'wave function move together, wrapped in the cell (positions in the controls are\n'
                               'still those of the calculation)')
            spinBox.valueChanged.connect(self.cellShiftChanged)
            originRow.addWidget(spinBox)
            self.originSpinBoxes.append(spinBox)
        originRow.addStretch(1)
        originWidget = QWidget()
        originWidget.setLayout(originRow)

        centreParticleButton = QPushButton('Centre on the fixed particle')
        centreParticleButton.setToolTip('Shift so that the fixed particle is in the middle of what is shown')
        centreParticleButton.clicked.connect(self.centreOnFixedParticle)
        resetButton = QPushButton('Reset')
        resetButton.setToolTip('The cell of the calculation (the layer still centred, if ticked)')
        resetButton.clicked.connect(lambda: self.setCellOrigin([0.0, 0.0, 0.0]))
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(centreParticleButton)
        buttons.addWidget(resetButton)
        buttons.addStretch(1)
        buttonsWidget = QWidget()
        buttonsWidget.setLayout(buttons)

        self.cellOriginNote = NoteLabel()
        self.cellOriginNote.hide()
        form.addRow(self.centreLayerCheckBox)
        form.addRow('Cell origin:', originWidget)
        form.addRow(buttonsWidget)
        form.addRow(self.cellOriginNote)

    def cellOrigin(self):
        return [spinBox.value() for spinBox in self.originSpinBoxes]

    def setCellOrigin(self, values):
        """Set the origin (fractions of a, b, c) at once; the axis of a centred layer keeps its centring."""
        locked = self.lockedAxis()
        changed = False
        for axis, (spinBox, value) in enumerate(zip(self.originSpinBoxes, values)):
            if axis == locked:
                continue
            value = wrapShift(float(value))
            if abs(spinBox.value() - value) > 1e-9:
                spinBox.blockSignals(True)
                spinBox.setValue(value)
                spinBox.blockSignals(False)
                changed = True
        if changed:
            self.cellShiftChanged.emit()

    def cellShift(self):
        """The shift of what is shown (fractions of a, b, c)."""
        return self.cellOrigin()

    def lockedAxis(self):
        """The axis whose origin the layer centring sets, or None."""
        return self.layer[0] if self.layer is not None and self.centreLayerCheckBox.isChecked() else None

    def setLayer(self, layer):
        """The vacuum found in the cell of the dataset ((axis, shift), or None): centred if ticked."""
        self.layer = layer
        self.centreLayerCheckBox.setEnabled(layer is not None)
        if layer is None:
            self.centreLayerCheckBox.setToolTip('No vacuum found in the cell: it is not a layer')
        else:
            self.centreLayerCheckBox.setToolTip(f'Vacuum along {"abc"[layer[0]]}: put on the faces of the cell, the '
                                                'layer in the middle')
        self.updateLayerCentring()

    @Slot()
    def updateLayerCentring(self):
        locked = self.lockedAxis()
        for axis, spinBox in enumerate(self.originSpinBoxes):
            spinBox.setEnabled(axis != locked)
        if self.layer is not None:
            axis, shift = self.layer
            value = shift if locked is not None else 0.0
            spinBox = self.originSpinBoxes[axis]
            if abs(spinBox.value() - value) > 1e-9:
                spinBox.blockSignals(True)
                spinBox.setValue(value)
                spinBox.blockSignals(False)
        self.cellShiftChanged.emit()

    @Slot()
    def centreOnFixedParticle(self):
        position = np.asarray(self.parameters.position(), dtype=float)
        self.setCellOrigin([0.5 - p for p in position])

    def showCellOriginNote(self, text):
        self.cellOriginNote.setText(text)
        self.cellOriginNote.setVisible(bool(text))

    def buildAxesSection(self):
        layout = QGridLayout()
        for i, (text, signal, checked, tooltip) in enumerate([
            ('Cartesian x, y, z', self.showCartesianAxesChanged, True, 'Grey arrows in the axes gizmo'),
            ('Lattice a, b, c', self.showLatticeVectorsChanged, True, 'Red, green and blue arrows in the axes gizmo'),
            ('Reciprocal a*, b*, c*', self.showReciprocalVectorsChanged, False, 'Light red, green and blue arrows in the axes gizmo'),
            ('Axis labels', self.showAxisLabelsChanged, True, 'Labels at the tips of the gizmo arrows'),
            ('Cell parameters', self.showCellInfoChanged, True, 'Lattice constants and angles in the top-left corner'),
            ('Caption', self.showCaptionChanged, True, 'What the view shows, in the top-right corner: the density of '
             'which particle, the other one fixed where'),
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
        self.planeBasisComboBox.addItems(VIEW_BASES)
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

        # Which density the plane cut shows (the distance distribution is the wave function's)
        self.cutDensityComboBox = QComboBox()
        self.cutDensityComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.cutDensityComboBox.addItems(['Wave function', 'Hole density'])
        self.cutDensityComboBox.setToolTip('The density on the plane: the wave function\'s, through its fixed particle '
                                           'as computed; or the fixed particle\'s own, through it as set')
        self.cutDensityComboBox.currentIndexChanged.connect(self.analysisChanged)

        form = formLayout()
        form.addRow(self.showAnalysisCheckBox)
        form.addRow('Plane cut of:', self.cutDensityComboBox)
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
        self.remember('cutDensity', get=lambda: self.cutLayer(),
                      set=lambda layer: self.cutDensityComboBox.setCurrentIndex(1 if layer == 'particle' else 0))
        self.remember('planeBasis', self.planeBasisComboBox)
        self.remember('planeNormal', **vector(self.planeNormalLineEdits))
        # The orientation of the cut taken from the view (after the normal, which
        # does not clear it when restored: no editing signal)
        self.remember('planeUp', get=lambda: self.planeUpHint,
                      set=lambda up: setattr(self, 'planeUpHint', [float(c) for c in up] if up else None))
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
        normal = viewVectorToCartesian(components, self.planeBasisComboBox.currentText(), self.dataset.cell)
        return {'normal': np.asarray(normal, dtype=float), 'up': self.planeUpHint,
                'offset': self.planeOffsetSpinBox.value() * ANGSTROM_TO_BOHR,
                'atoms': self.planeAtomsSpinBox.value() * ANGSTROM_TO_BOHR,
                'show3D': self.showPlaneCheckBox.isChecked()}

    def cutLayer(self):
        """The density of the plane cut: 'wf' or 'particle'."""
        return 'particle' if self.cutDensityComboBox.currentIndex() == 1 else 'wf'

    def exportLayer(self):
        """The density exported: 'wf' or 'particle'."""
        return 'particle' if self.exportDensityComboBox.currentIndex() == 1 else 'wf'

    @Slot()
    def updateExportDensity(self, *args):
        """Density… is enabled when the density chosen exists."""
        if not hasattr(self, 'exportDensityComboBox'):
            return
        calc = self.calculations
        exists = calc.waveFunction is not None if self.exportLayer() == 'wf' else calc.particleDensity is not None
        self.exportDensityButton.setEnabled(exists)

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
        # Which density: the wave function's, or the fixed particle's own (over the supercell drawn)
        self.exportDensityComboBox = QComboBox()
        self.exportDensityComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.exportDensityComboBox.addItems(['Wave function', 'Hole density'])
        self.exportDensityComboBox.setToolTip('The density saved by Density…: the wave function\'s, or the fixed '
                                              'particle\'s own, repeated over the supercell drawn')
        self.exportDensityComboBox.currentIndexChanged.connect(self.updateExportDensity)
        self.calculations.wfComputed.connect(self.updateExportDensity)
        self.calculations.particleDensityReady.connect(self.updateExportDensity)
        self.calculations.resultsChanged.connect(self.updateExportDensity)

        layout = QHBoxLayout()
        layout.addWidget(imageButton)
        layout.addWidget(self.exportDensityButton)
        layout.addStretch(1)
        # The density files with the cell origin shown, or that of the calculation
        self.exportShiftedCheckBox = QCheckBox('Density as shown (cell origin applied)')
        self.exportShiftedCheckBox.setChecked(True)
        self.exportShiftedCheckBox.setToolTip('Untick for the cell of the calculation, unshifted')
        self.remember('exportShifted', self.exportShiftedCheckBox)
        densityRow = QHBoxLayout()
        densityRow.addWidget(QLabel('Density:'))
        densityRow.addWidget(self.exportDensityComboBox)
        densityRow.addStretch(1)
        self.remember('exportDensity', get=lambda: self.exportLayer(),
                      set=lambda layer: self.exportDensityComboBox.setCurrentIndex(1 if layer == 'particle' else 0))
        column = QVBoxLayout()
        column.addLayout(layout)
        column.addLayout(densityRow)
        column.addWidget(self.exportShiftedCheckBox)
        self.addSection('Export', column, expanded=False)

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

    # The cutoff in Ry and in RL

    def setGVectorShells(self, found):
        """The G-vectors of the dataset, to give the cutoff in RL too (none without a dataset)."""
        self.gShells = None
        if found and self.dataset.saveDir:
            from visual_excitons.core.memory import GVectorShells
            from visual_excitons.core.tasks import databaseAccess
            from yambopy import YamboLatticeDB
            try:
                with databaseAccess():
                    lattice = YamboLatticeDB.from_db(self.dataset.saveDir + '/ns.db1', Expand=False)
                    self.gShells = GVectorShells(self.dataset.saveDir, lattice)
            except (OSError, KeyError, ValueError):
                self.gShells = None
        box = self.wfCutoffRlSpinBox
        box.blockSignals(True)
        if self.gShells is not None:
            box.setRange(1, self.gShells.count)
            self.lastRl = self.gShells.rl(self.wfCutoffSpinBox.value())
            box.setValue(max(self.lastRl, 1))
            box.setSpecialValueText('')
        else:
            box.setRange(0, 0)
            box.setSpecialValueText('– RL')
        box.blockSignals(False)
        box.setEnabled(self.gShells is not None and not self.fullCutoffCheckBox.isChecked())

    @Slot(float)
    def cutoffRyChanged(self, cutoff):
        """The cutoff typed in Ry: its count of G-vectors in RL."""
        if self.gShells is None:
            return
        self.lastRl = self.gShells.rl(cutoff)
        self.wfCutoffRlSpinBox.blockSignals(True)
        self.wfCutoffRlSpinBox.setValue(max(self.lastRl, 1))
        self.wfCutoffRlSpinBox.blockSignals(False)

    @Slot(int)
    def cutoffRlChanged(self, rl):
        """A count of G-vectors: rounded to complete shells (down when it went down), and its cutoff in Ry."""
        if self.gShells is None:
            return
        complete, _ = self.gShells.shell(rl, down=rl < self.lastRl)
        self.lastRl = complete
        self.wfCutoffRlSpinBox.blockSignals(True)
        self.wfCutoffRlSpinBox.setValue(complete)
        self.wfCutoffRlSpinBox.blockSignals(False)
        self.wfCutoffSpinBox.setValue(self.gShells.cutoffRy(complete))

    @Slot()
    def updateWfStatesNote(self, *args):
        """The states of the wave function shown, and a warning when computed with the other setting."""
        calc = self.calculations
        if calc.waveFunction is None or not calc.wfExciton:
            self.wfStatesNote.hide()
            return
        qIndex, excIndex = calc.wfExciton
        states = calc.wfStates or [excIndex]
        # Older results (and sessions) say only whether the degenerate states were summed
        computedSum = calc.wfStateSum or (None if calc.wfDegenerate is None else
                                          {'degenerate': bool(calc.wfDegenerate), 'window': 0.0, 'weighting': 'equal'})
        summed = dict(computedSum or {}, states=states)
        text = f'Shown: exciton {excIndex} at Q{qIndex + 1}{describeStateSum(summed, [excIndex])}.'
        now = self.calculations.stateSum()
        if computedSum is not None and computedSum != now:
            if computedSum['window'] != now['window'] or computedSum['weighting'] != now['weighting']:
                other = 'another energy window'
            else:
                other = 'summing' if calc.wfDegenerate else 'without summing'
                other += ' the degenerate states'
            text += (f' <span style="color:#d9822b">Computed {other}: compute it again for the setting of '
                     'now.</span>')
        self.wfStatesNote.setText(text)
        self.wfStatesNote.show()

    @Slot(int)
    def updateParticlePositionWidgets(self, index: int):
        self.parameters.particle = 'h' if index == 0 else 'e'

        position = self.parameters.position()

        for lineEdit, value in zip((self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit),
                                   position):
            lineEdit.setText(f'{float(value) + 0.0:.4f}')   # as the row shown, and after snapping

        self.particlePositionChanged()

    @Slot()
    def particlePositionChanged(self):
        position = [float(self.xParticlePosLineEdit.text()), float(self.yParticlePosLineEdit.text()), float(self.zParticlePosLineEdit.text())]
        self.parameters.setPosition(position)
        self.fixedParticlePosChanged.emit()

    def particleShift(self):
        if not hasattr(self, 'originSpinBoxes'):        # the Structure section is built after this one
            return [0.0, 0.0, 0.0]
        shift = self.shiftProvider() if self.shiftProvider is not None else [0.0, 0.0, 0.0]
        return [float(value) for value in shift]

    @Slot()
    def updateShownPosition(self, *args):
        """The position as shown: its row only while there is a shift (the two would agree otherwise)."""
        if not hasattr(self, 'calculationForm'):
            return
        shift = self.particleShift()
        shifted = any(abs(value) > 1e-9 for value in shift)
        form = self.calculationForm
        form.setRowVisible(self.particleShownWidget, shifted)
        form.labelForField(self.particleComputedWidget).setText('Position as computed:' if shifted
                                                                else 'Position (a, b, c):')
        if not shifted:
            return
        computed = np.asarray(self.parameters.position(), dtype=float)
        shown = (computed + np.asarray(shift)) % 1.0
        shown[np.isclose(shown, 1.0, atol=1e-6)] = 0.0
        for lineEdit, value in zip(self.shownParticleLineEdits, shown):
            if not lineEdit.hasFocus():
                lineEdit.setText(f'{value + 0.0:.4f}')

    @Slot()
    def shownPositionEdited(self):
        """A position typed as shown: the position computed is that minus the shift."""
        try:
            shown = np.array([float(lineEdit.text()) for lineEdit in self.shownParticleLineEdits])
        except ValueError:
            self.updateShownPosition()
            return
        computed = (shown - np.asarray(self.particleShift())) % 1.0
        computed[np.isclose(computed, 1.0, atol=1e-6)] = 0.0
        for lineEdit, value in zip((self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit),
                                   computed):
            lineEdit.setText(f'{value + 0.0:.4f}')
        self.particlePositionChanged()

    @Slot()
    def onWfComputed(self):
        """Show the position and supercell actually used for the wave function."""
        calc = self.calculations

        # Supercell: odd sizes are enforced here, so this only guards against changes
        for spinBox, size in zip((self.xSupercellSpinBox, self.ySupercellSpinBox, self.zSupercellSpinBox), calc.wfSupercell):
            if spinBox.value() != size:
                spinBox.setValue(size)

        # Fixed particle position snapped to the real-space grid
        self.parameters.setPosition(calc.wfFixedPosition, calc.wfFixedParticle)
        if calc.wfFixedParticle == self.parameters.particle:
            for lineEdit, value in zip((self.xParticlePosLineEdit, self.yParticlePosLineEdit, self.zParticlePosLineEdit), calc.wfFixedPosition):
                lineEdit.setText(f'{value + 0.0:.4f}')   # + 0.0: no "-0.0000"

        particle = 'Hole' if calc.wfFixedParticle == 'h' else 'Electron'
        self.particleGridLabel.setText(f'{particle} position snapped to the nearest point of the wave-function grid '
                                       f'({calc.wfGrid[0]} × {calc.wfGrid[1]} × {calc.wfGrid[2]} points per cell).')
        self.particleGridLabel.show()
        self.fixedParticlePosChanged.emit()

    @Slot()
    def computeWf(self):
        """
        Compute the wave function; whether it started. With 'Fix the particle at
        its density maximum', for a density not computed yet (a new exciton,
        particle, cutoff or degenerate setting), the density first: the particle
        then goes to its maximum (onDensityForWaveFunction).
        """
        if (self.atMaximumCheckBox.isChecked() and self.currentDensity() is None and self.dataset.saveDir
                and self.dataset.diagoDir):
            self.pendingWaveFunction = True
            self.computeParticleDensity()
            return True
        q_index = self.qPointIndex()
        exc_index = self.excitonIndexSpinBox.value()
        fixed_particle = self.parameters.particle
        fixed_position = self.parameters.position()
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
        return self.parameters.display['wf'].smoothing

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
        particle = 'hole' if self.parameters.particle == 'h' else 'electron'
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

    @Slot(float)
    def setAtomScale(self, scale: float):
        self.parameters.atomScale = scale
        self.signalReplotLattice.emit()

    @Slot(float)
    def setBondTolerance(self, tolerance: float):
        self.parameters.bondTolerance = tolerance
        self.signalReplotLattice.emit()

    @Slot(float)
    def setBondRadius(self, radius: float):
        self.parameters.bondRadius = radius
        self.signalReplotLattice.emit()

    @Slot(int)
    def setBondColoring(self, mode: int):
        self.parameters.bondColoring = mode
        self.signalReplotLattice.emit()

    @Slot(int)
    def updatePlotTypeRows(self, plotType: int):
        for widget, plotTypes in self.plotTypeRows:
            self.plotFormLayout.setRowVisible(widget, plotType in plotTypes)

    def plotType(self, layer='wf'):
        return self.parameters.display[layer].plotType

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

        self.parameters.supercell = [self.xSupercellSpinBox.value(), self.ySupercellSpinBox.value(), self.zSupercellSpinBox.value()]
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
        for i, basis in enumerate(VIEW_BASES):
            if basis != 'Cartesian':
                model.item(i).setEnabled(enabled)
        if not enabled and self.viewBasis() != 'Cartesian':
            self.viewBasisComboBox.setCurrentText('Cartesian')

    @Slot(bool)
    def onDatabaseFound(self, found: bool):
        self.setLatticeBasesEnabled(found)
        self.setGVectorShells(found)
        # A new cell changes what lattice directions mean in Cartesian space
        if found and self.viewBasis() != 'Cartesian':
            self.applyView()

    def populateViewPresets(self):
        self.viewPresetComboBox.clear()
        self.viewPresetComboBox.addItems(list(VIEW_PRESETS[self.viewBasis()].keys()))

    @Slot(int)
    def onViewBasisChanged(self, index: int):
        presetIndex = self.viewPresetComboBox.currentIndex()
        self.populateViewPresets()
        self.viewPresetComboBox.setCurrentIndex(max(presetIndex, 0))
        self.onViewPresetActivated(self.viewPresetComboBox.currentIndex())

    @Slot(int)
    def onViewPresetActivated(self, index: int, apply: bool = True):
        presets = VIEW_PRESETS[self.viewBasis()]
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
            lookDir = viewVectorToCartesian(direction, self.viewBasis(), self.dataset.cell)
            upDir = None if up is None else viewVectorToCartesian(up, self.viewBasis(), self.dataset.cell)
        except ValueError as error:
            self.showViewStatus(str(error))
            return

        if self.reverseViewCheckBox.isChecked():
            lookDir = -lookDir

        self.showViewStatus('')
        self.viewDirChanged.emit(lookDir.tolist(), None if upDir is None else upDir.tolist())
