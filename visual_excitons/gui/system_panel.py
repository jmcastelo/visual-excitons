from PySide6.QtCore import Slot, Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QHBoxLayout, QVBoxLayout
from PySide6.QtWidgets import QComboBox, QGroupBox, QFormLayout, QGridLayout, QSizePolicy, QMessageBox, QSpinBox, QDoubleSpinBox
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QMenu, QHeaderView
from pathlib import Path

from visual_excitons.core.atomic_data import BOHR_TO_ANGSTROM
from visual_excitons.core.lattice_info import bravaisName
from visual_excitons.core.lattice_info import SYMMETRY_TOLERANCES
from visual_excitons.core.consistency import checkDataset, summary, Busy, OK, INFO, WARNING, ERROR
from .inspector import NoteLabel

# Default density of points along the Q-path, per Bohr⁻¹ (see densitySpin)
DEFAULT_PATH_DENSITY = 300


class SystemPanel(QWidget):
    """System panel: data directories, crystal lattice and Brillouin-zone path."""

    # Read every BSE file (run in the background by the main window, see setFullBSEChecks)
    checkAllBSERequested = Signal()
    # A directory chosen by the user: 'save', 'diago' or 'qp', and the path (the
    # main window applies it: a new SAVE directory is another dataset)
    directoryChosen = Signal(str, str)

    # A Q-path was set successfully: its state (see qPathState), to be saved
    qPathApplied = Signal(dict)

    def __init__(self, dataset):
        """The System panel of `dataset` (a core.dataset.Dataset)."""
        QWidget.__init__(self)

        self.dataset = dataset

        # Calculation type

        self.calcTypeComboBox = QComboBox()
        self.calcTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.calcTypeComboBox.addItems(['DFT+BSE', 'DFT+GW+BSE'])
        self.calcTypeComboBox.setCurrentIndex(1 if self.dataset.gw else 0)
        self.calcTypeComboBox.currentIndexChanged.connect(self.setGW)
        self.dataset.gwChanged.connect(lambda gw: self.calcTypeComboBox.setCurrentIndex(1 if gw else 0))

        # Directory rows: label, path, browse button, and a status line below

        dirLayout = QGridLayout()
        dirLayout.setColumnStretch(1, 1)
        dirLayout.setVerticalSpacing(4)
        dirLayout.addWidget(QLabel('Calculation:'), 0, 0)
        dirLayout.addWidget(self.calcTypeComboBox, 0, 1)

        def directoryRow(row, text, toolTip, browse, edit):
            label = QLabel(text)
            label.setToolTip(toolTip)
            lineEdit = QLineEdit()
            lineEdit.setToolTip(toolTip)
            lineEdit.editingFinished.connect(edit)
            button = QPushButton('Browse…')
            button.clicked.connect(browse)
            status = QLabel()
            status.setTextFormat(Qt.TextFormat.RichText)
            # Messages can be long (e.g. the Q-points or QP databases found): wrapped
            status.setWordWrap(True)
            dirLayout.addWidget(label, 2 * row + 1, 0)
            dirLayout.addWidget(lineEdit, 2 * row + 1, 1)
            dirLayout.addWidget(button, 2 * row + 1, 2)
            dirLayout.addWidget(status, 2 * row + 2, 1, 1, 2)
            return label, lineEdit, button, status

        _, self.saveDirEdit, _, self.saveLabel = directoryRow(
            0, 'SAVE:', 'Directory with the ns.db1 database of the DFT calculation', self.selectSaveDir, self.editSaveDir)
        _, self.diagoDirEdit, _, self.diagoLabel = directoryRow(
            1, 'BSE:', 'Directory with the ndb.BS_diago_Q* databases, one per Q-point', self.selectDiagoDir, self.editDiagoDir)
        self.qpDirLabel, self.qpDirEdit, self.selectQPDirButton, self.qpLabel = directoryRow(
            2, 'GW:', 'Directory with the QP databases of the GW calculation (ndb.QP, or others recognised by their '
                      'content, e.g. ndb.QP_140_146)', self.selectQPDir, self.editQPDir)

        # The QP database used, when the directory has several (e.g. merged and partial ones)
        self.qpFileLabel = QLabel('QP database:')
        self.qpFileComboBox = QComboBox()
        self.qpFileComboBox.setToolTip('The QP database used: ndb.QP by default, otherwise the widest band range')
        self.qpFileComboBox.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Narrower than its longest entry when the panel is: the entries are elided
        self.qpFileComboBox.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.qpFileComboBox.setMinimumContentsLength(12)
        self.qpFileComboBox.activated.connect(lambda index: self.dataset.setQPFile(self.qpFileComboBox.itemData(index)))
        dirLayout.addWidget(self.qpFileLabel, 7, 0)
        dirLayout.addWidget(self.qpFileComboBox, 7, 1)
        self.dataset.qpDatabasesChanged.connect(self.setQPDatabases)
        self.setQPDatabases([], '')

        # Whether the databases belong together (see core/consistency.py)
        self.checksLabel = QLabel()
        self.checksLabel.setTextFormat(Qt.TextFormat.RichText)
        self.checksLabel.setWordWrap(True)
        self.checksDetailsButton = QPushButton('Details…')
        self.checksDetailsButton.setToolTip('The checks of the databases, one by one')
        self.checksDetailsButton.clicked.connect(self.showChecks)
        self.checksDetailsButton.setEnabled(False)
        # Every BSE file read (in the background): catches files renamed with
        # standard names that are not what their name says
        self.checkAllBSEButton = QPushButton('Check all BSE')
        self.checkAllBSEButton.setToolTip('Read every BSE database, not only a sample: each must be one, of the\n'
                                          'Q-point its name gives (in background; a few seconds for hundreds)')
        self.checkAllBSEButton.clicked.connect(self.checkAllBSERequested)
        self.checkAllBSEButton.setEnabled(False)
        checkButtons = QVBoxLayout()
        checkButtons.setContentsMargins(0, 0, 0, 0)
        checkButtons.addWidget(self.checksDetailsButton)
        checkButtons.addWidget(self.checkAllBSEButton)
        dirLayout.addWidget(QLabel('Checks:'), 9, 0)
        dirLayout.addWidget(self.checksLabel, 9, 1)
        dirLayout.addLayout(checkButtons, 9, 2)
        self.findings = []
        self.fullBSECheck = None    # (BSE files checked, findings) of the last check of all of them
        self.checkTimer = QTimer(self)
        self.checkTimer.setSingleShot(True)
        self.checkTimer.setInterval(300)
        self.checkTimer.timeout.connect(self.runChecks)
        for signal in (self.dataset.databaseFound, self.dataset.diagoDirChanged, self.dataset.qpDirChanged,
                       self.dataset.gwChanged):
            signal.connect(lambda *args: self.checkTimer.start())

        self.setStatus(self.saveLabel, 'ns.db1 not found!')
        self.setStatus(self.diagoLabel, 'No BSE databases (ndb.BS_diago_Q*) found!')
        self.setStatus(self.qpLabel, 'No QP database (ndb.QP) found!')

        self.dataset.saveDirChanged.connect(self.setSaveLabel)
        self.dataset.diagoDirChanged.connect(self.setDiagoLabel)
        self.dataset.qpDirChanged.connect(self.setQPLabel)

        dirGroupBox = QGroupBox('Data')
        dirGroupBox.setLayout(dirLayout)

        # Bravais lattice

        # What the crystal is: detected, not chosen (a lattice chosen by hand would
        # take its special points in a standard orientation, maybe not the cell's)
        def infoLabel(toolTip=''):
            label = QLabel()
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setToolTip(toolTip)
            return label
        self.latticeLabel = infoLabel('The Bravais lattice, identified from the symmetry of the cell (spglib): '
                                      'Quantum ESPRESSO ibrav and Setyawan-Curtarolo variant, which give the '
                                      'special points')
        self.spaceGroupLabel = infoLabel('Space group of the crystal, with its atoms (spglib), and its point group')
        self.atomsLabel = infoLabel('Formula and atoms in the unit cell')
        self.volumeLabel = infoLabel('Volume of the unit cell')
        self.kGridLabel = infoLabel('k-point grid of the DFT calculation, and its irreducible points '
                                    '(the Q-points of the BSE databases)')
        self.vacuumLabel = infoLabel('A layer: the axis along which the cell has vacuum')
        self.latticeNote = NoteLabel()
        self.latticeNote.hide()

        self.parameterLabels = {name: QLabel() for name in ('a', 'b', 'c', 'alpha', 'beta', 'gamma')}
        for label in self.parameterLabels.values():
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        bravaisLayout = QGridLayout()
        bravaisLayout.setColumnStretch(3, 1)
        bravaisLayout.setHorizontalSpacing(12)
        row = 0
        for text, label in (('Lattice:', self.latticeLabel), ('Space group:', self.spaceGroupLabel),
                            ('Atoms:', self.atomsLabel)):
            bravaisLayout.addWidget(QLabel(text), row, 0)
            bravaisLayout.addWidget(label, row, 1, 1, 3)
            row += 1
        for length, angle, angleSymbol in (('a', 'alpha', 'α'), ('b', 'beta', 'β'), ('c', 'gamma', 'γ')):
            bravaisLayout.addWidget(QLabel(f'{length}:'), row, 0)
            bravaisLayout.addWidget(self.parameterLabels[length], row, 1)
            bravaisLayout.addWidget(QLabel(f'{angleSymbol}:'), row, 2)
            bravaisLayout.addWidget(self.parameterLabels[angle], row, 3)
            row += 1
        for text, label in (('Volume:', self.volumeLabel), ('k-points:', self.kGridLabel),
                            ('Vacuum:', self.vacuumLabel)):
            bravaisLayout.addWidget(QLabel(text), row, 0)
            bravaisLayout.addWidget(label, row, 1, 1, 3)
            row += 1
        bravaisLayout.addWidget(self.latticeNote, row, 0, 1, 4)
        self.dataset.databaseFound.connect(self.onDatabaseFound)

        bravaisGroup = QGroupBox('Crystal')
        bravaisGroup.setLayout(bravaisLayout)

        # Q-path

        self.qPathLineEdit = QLineEdit()
        self.qPathLineEdit.setToolTip('Labels of the high-symmetry points along the path;\n'
                                      'commas separate disconnected sections')

        self.numPointsSpin = QSpinBox(minimum=0, maximum=999999)
        self.numPointsSpin.setValue(100)

        # Points per unit of reciprocal length of the cell (without 2π), as
        # yambopy's BrillouinZone takes it: the cell is in Bohr. 300 gives about
        # 100-250 points along the default paths of common crystals
        self.densitySpin = QDoubleSpinBox(minimum=0, maximum=99999, singleStep=10, decimals=1)
        self.densitySpin.setValue(DEFAULT_PATH_DENSITY)
        self.densitySpin.setSuffix(' per Bohr⁻¹')
        self.densitySpin.setToolTip('Points per unit of length along the path in reciprocal space, '
                                    'in Bohr⁻¹ (without 2π)')
        self.densitySpin.setVisible(False)

        self.interpolationComboBox = QComboBox()
        self.interpolationComboBox.addItems(['Number of points', 'Density'])
        self.interpolationComboBox.currentIndexChanged.connect(self.updateInterpolationEdit)

        self.interpolationLayout = QHBoxLayout()
        self.interpolationLayout.addWidget(self.interpolationComboBox)
        self.interpolationLayout.addWidget(self.numPointsSpin)
        self.interpolationLayout.addWidget(self.densitySpin)
        self.interpolationLayout.addStretch(1)

        self.setPathButton = QPushButton('Set Q-path')
        self.setPathButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setPathButton.clicked.connect(self.setBrillouinZone)

        qPathLayout = QFormLayout()
        qPathLayout.addRow('Path:', self.qPathLineEdit)
        qPathLayout.addRow('Sampling:', self.interpolationLayout)
        qPathLayout.addRow('', self.setPathButton)

        qPathGroupBox = QGroupBox('Q-path')
        qPathGroupBox.setLayout(qPathLayout)

        # High-symmetry points

        self.hspTable = QTableWidget()
        self.hspTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.hspTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.hspTable.setColumnCount(4)
        self.hspTable.setHorizontalHeaderLabels(['Label', 'k₁', 'k₂', 'k₃'])
        for column in range(1, 4):
            self.hspTable.horizontalHeaderItem(column).setToolTip(f'Fractional coordinate along the reciprocal vector b{column}')
        self.hspTable.setAlternatingRowColors(True)
        # Below the Q-path, in a panel that scrolls: room for several points at least
        self.hspTable.setMinimumHeight(8 * self.hspTable.verticalHeader().defaultSectionSize())

        self.hspTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.hspTable.customContextMenuRequested.connect(self.showContextMenu)

        self.hspTable.cellChanged.connect(self.validateCell)

        hspLayout = QVBoxLayout()
        hspLayout.addWidget(self.hspTable)
        hspLayout.addWidget(NoteLabel('Coordinates are fractions of the reciprocal lattice vectors. '
                                      'Right-click the table to add or delete extra points.'))

        hspGroupBox = QGroupBox('High-symmetry points')
        hspGroupBox.setLayout(hspLayout)

        # Main layout: one column (it may be docked in a narrow panel), the
        # high-symmetry points below the Q-path they are used in

        mainLayout = QVBoxLayout()
        mainLayout.setContentsMargins(16, 12, 16, 12)
        mainLayout.setSpacing(12)
        mainLayout.addWidget(dirGroupBox)
        mainLayout.addWidget(bravaisGroup)
        mainLayout.addWidget(qPathGroupBox)
        mainLayout.addWidget(hspGroupBox, 1)

        self.setLayout(mainLayout)

    @staticmethod
    def setStatus(label, text):
        """Status of a directory, with a green tick or a red cross."""
        ok = 'not found' not in text and not text.startswith('No ')
        symbol, color = ('✓', '#2e9e4f') if ok else ('✗', '#d9453b')
        label.setText(f'<span style="color:{color}; font-weight:bold">{symbol}</span>&nbsp;{text}')

    @Slot(list, str)
    def setQPDatabases(self, databases, current):
        """The QP databases to choose from (shown with GW, when there is one at least)."""
        self.qpFileComboBox.clear()
        for info in databases:
            self.qpFileComboBox.addItem(f'{info["name"]}: bands {info["bands"][0]}–{info["bands"][1]}, '
                                        f'{info["kpoints"]} k-points', info['name'])
        if current:
            self.qpFileComboBox.setCurrentIndex(max(0, self.qpFileComboBox.findData(current)))
        shown = self.dataset.gw and bool(databases)
        self.qpFileLabel.setVisible(shown)
        self.qpFileComboBox.setVisible(shown)
        self.qpFileComboBox.setEnabled(len(databases) > 1)

    @Slot()
    def runChecks(self):
        """Check that the databases belong together, and show the result."""
        o = self.dataset
        if not o.saveDir:
            self.findings = []
            self.checksLabel.setText('')
            self.checksDetailsButton.setEnabled(False)
            self.checkAllBSEButton.setEnabled(False)
            return
        qpPath = f'{o.qpDir}/{o.qpFile}' if o.gw and o.qpDir and o.qpFile else None
        try:
            self.findings = checkDataset(o.saveDir, qpPath, o.diagoDir or None, o.bseFiles, o.bseProblems)
        except Busy:
            self.checkTimer.start(1000)     # a calculation is reading them: later
            return
        # The check of every BSE file, if done on these files, rather than the sample
        if self.fullBSECheck is not None and self.fullBSECheck[0] == self.bseKey():
            self.findings = [f for f in self.findings if f['area'] != 'BSE'] + self.fullBSECheck[1]
        self.checkAllBSEButton.setEnabled(bool(o.bseFiles))
        level = summary(self.findings)
        problems = [f for f in self.findings if f['level'] in (ERROR, WARNING)]
        if level == OK:
            text = '<span style="color:#2e9e4f; font-weight:bold">✓</span>&nbsp;The databases belong together.'
        else:
            symbol, color = ('✗', '#d9453b') if level == ERROR else ('⚠', '#d9822b')
            first = problems[0]['text']
            more = f' (and {len(problems) - 1} more)' if len(problems) > 1 else ''
            text = f'<span style="color:{color}; font-weight:bold">{symbol}</span>&nbsp;{first}{more}'
        self.checksLabel.setText(text)
        self.checksDetailsButton.setEnabled(True)

    def bseKey(self):
        """What a check of every BSE file was done on."""
        return self.dataset.diagoDir, tuple(sorted(self.dataset.bseFiles.items()))

    def setFullBSEChecks(self, key, findings):
        """The BSE findings of a check of every BSE file (of `key`, see bseKey), shown from now on."""
        self.fullBSECheck = (key, [f for f in findings if f['area'] == 'BSE'])
        self.runChecks()

    @Slot()
    def showChecks(self):
        symbols = {OK: '✓', INFO: 'ℹ', WARNING: '⚠', ERROR: '✗'}
        lines = [f'{symbols[f["level"]]} {f["area"]}: {f["text"]}' for f in self.findings]
        QMessageBox.information(self, 'Dataset check', '\n\n'.join(lines) or 'Nothing to check.')

    @Slot(int)
    def setGW(self, index):
        gw = (index == 1)
        self.dataset.setGW(gw)
        self.qpDirLabel.setVisible(gw)
        self.qpDirEdit.setVisible(gw)
        self.selectQPDirButton.setVisible(gw)
        self.setQPDatabases(self.dataset.qpDatabases, self.dataset.qpFile)
        self.qpLabel.setVisible(gw)

    @Slot()
    def selectSaveDir(self):
        directory = QFileDialog.getExistingDirectory(self, 'SAVE directory', self.dataset.saveDir, QFileDialog.Option.ShowDirsOnly)
        if directory:
            self.directoryChosen.emit('save', directory)

    @Slot()
    def selectDiagoDir(self):
        directory = QFileDialog.getExistingDirectory(self, 'BSE directory', self.dataset.diagoDir, QFileDialog.Option.ShowDirsOnly)
        if directory:
            self.directoryChosen.emit('diago', directory)

    @Slot()
    def selectQPDir(self):
        directory = QFileDialog.getExistingDirectory(self, 'GW directory', self.dataset.qpDir or self.dataset.diagoDir,
                                                     QFileDialog.Option.ShowDirsOnly)
        if directory:
            self.directoryChosen.emit('qp', directory)

    def directoryEdited(self, kind, edit, current):
        """A directory typed in `edit`: chosen if it is one and not the one in use (`current`), else put back."""
        text = edit.text().strip()
        if text and Path(text).is_dir() and Path(text).resolve() != (Path(current).resolve() if current else None):
            self.directoryChosen.emit(kind, text)
        else:
            edit.setText(current)

    @Slot()
    def editSaveDir(self):
        self.directoryEdited('save', self.saveDirEdit, self.dataset.saveDir)

    @Slot()
    def editDiagoDir(self):
        self.directoryEdited('diago', self.diagoDirEdit, self.dataset.diagoDir)

    @Slot()
    def editQPDir(self):
        self.directoryEdited('qp', self.qpDirEdit, self.dataset.qpDir)

    def showDirectories(self):
        """The directories in use in the fields (after a choice that was not applied)."""
        self.saveDirEdit.setText(self.dataset.saveDir)
        self.diagoDirEdit.setText(self.dataset.diagoDir)
        self.qpDirEdit.setText(self.dataset.qpDir)

    @Slot()
    def setSaveLabel(self, dir, text):
        self.saveDirEdit.setText(dir)
        self.setStatus(self.saveLabel, text)

    @Slot()
    def setDiagoLabel(self, dir, text):
        self.diagoDirEdit.setText(dir)
        self.setStatus(self.diagoLabel, text)

    @Slot()
    def setQPLabel(self, dir, text):
        self.qpDirEdit.setText(dir)
        self.setStatus(self.qpLabel, text)

    @Slot(bool)
    def onDatabaseFound(self, found):
        """The crystal of the dataset found (or none): its description, special points and default path."""
        o = self.dataset
        ibrav = o.identifyLattice() if found else None
        self.qPathLineEdit.setText(o.defaultPath if ibrav is not None else '')
        self.setPathButton.setEnabled(ibrav is not None)
        self.populateHSPTable(o.highSymmetryPoints if ibrav is not None else {})
        self.showLattice(found)

    def showLattice(self, found):
        """The description of the crystal (see lattice_info.latticeSummary)."""
        o = self.dataset
        labels = (self.latticeLabel, self.spaceGroupLabel, self.atomsLabel, self.volumeLabel, self.kGridLabel,
                  self.vacuumLabel, *self.parameterLabels.values())
        for label in labels:
            label.clear()
        self.latticeNote.hide()
        info = o.latticeSummary() if found else None
        if info is None:
            return
        if o.ibrav != -1:
            self.latticeLabel.setText(f'{bravaisName(o.ibrav)} · ibrav {o.ibrav} · {o.variant}')
        else:
            self.latticeLabel.setText('Not identified')
        group = info['spaceGroup']
        self.spaceGroupLabel.setText(f'{group[0]} (No. {group[1]}), point group {group[2]}' if group else 'Not found')
        self.atomsLabel.setText(f'{info["formula"]} · {info["atoms"]} atom{"s" if info["atoms"] != 1 else ""} per cell')
        self.volumeLabel.setText(f'{info["volume"]:.3f} Å³')
        if info['grid']:
            self.kGridLabel.setText(' × '.join(str(n) for n in info['grid']) + f' ({o.nIbzQpoints} irreducible)')
        self.vacuumLabel.setText(f'along {"abc"[info["layer"]]}: a layer (2D)' if info['layer'] is not None
                                 else 'none (bulk)')
        # Lengths are in Bohr in the database
        for paramName, label in self.parameterLabels.items():
            value = o.latticeParameters[paramName]
            if paramName in ('a', 'b', 'c'):
                label.setText(f'{value * BOHR_TO_ANGSTROM:.5f} Å')
                label.setToolTip(f'{value:.5f} Bohr')
            else:
                label.setText(f'{value:.4f}°')
        if o.ibrav == -1:
            self.latticeNote.setText(f'The lattice could not be identified ({o.latticeProblem}), so no Q-path can '
                                     'be set: only cubic, hexagonal, rhombohedral, tetragonal and orthorhombic '
                                     'lattices have special points here.')
            self.latticeNote.show()
        elif o.symmetryTolerance and o.symmetryTolerance > SYMMETRY_TOLERANCES[0]:
            strict = f' (at the strictest, {o.strictVariant})' if o.strictVariant else ''
            self.latticeNote.setText(f'Identified with a symmetry tolerance of {o.symmetryTolerance:g}, relative to '
                                     f'the longest lattice vector{strict}: the cell is slightly off this symmetry.')
            self.latticeNote.show()

    @Slot(int)
    def updateInterpolationEdit(self, index):
        if index == 0:
            self.numPointsSpin.setVisible(True)
            self.densitySpin.setVisible(False)
        elif index == 1:
            self.numPointsSpin.setVisible(False)
            self.densitySpin.setVisible(True)

    @Slot()
    def setBrillouinZone(self, quiet: bool = False):
        """Set the Q-path of the widgets; errors are shown in a dialog unless `quiet`. True if it was set."""
        try:
            if self.interpolationComboBox.currentIndex() == 0:
                self.dataset.setBrillouinZone(path=self.qPathLineEdit.text(), npoints=self.numPointsSpin.value())
            elif self.interpolationComboBox.currentIndex() == 1:
                self.dataset.setBrillouinZone(path=self.qPathLineEdit.text(), density=self.densitySpin.value())
        except ValueError as error:
            if not quiet:
                msgBox = QMessageBox()
                msgBox.setText('Error')
                msgBox.setInformativeText(str(error))
                msgBox.exec()
            return False
        self.qPathLineEdit.setText(self.dataset.pathString())
        self.qPathApplied.emit(self.qPathState())
        return True

    def qPathState(self) -> dict:
        """The Q-path as set, with what it depends on: lattice type and extra points."""
        return {
            'ibrav': self.dataset.ibrav,
            'path': self.dataset.pathString(),
            'sampling': 'density' if self.interpolationComboBox.currentIndex() == 1 else 'points',
            'points': self.numPointsSpin.value(),
            'density': self.densitySpin.value(),
            'extraPoints': {label: list(coords) for label, coords in self.dataset.extraHighSymmetryPoints.items()},
        }

    def restoreQPath(self, state: dict) -> bool:
        """Set a Q-path saved with qPathState. False (and the default path left) if it cannot be set."""
        try:
            # Saved for another lattice (e.g. chosen by hand in earlier versions): not valid
            if int(state['ibrav']) != self.dataset.ibrav or self.dataset.ibrav == -1:
                return False
            self.dataset.setLatticeData()             # the points and path of the lattice, afresh
            self.populateHSPTable(self.dataset.highSymmetryPoints)

            # Extra points, as rows below those of the lattice
            self.hspTable.blockSignals(True)
            for label, coords in state.get('extraPoints', {}).items():
                row = self.hspTable.rowCount()
                self.hspTable.insertRow(row)
                for column, text in enumerate([label] + [f'{float(c):.5f}' for c in coords]):
                    self.hspTable.setItem(row, column, QTableWidgetItem(text))
            self.hspTable.blockSignals(False)
            self.setExtraHSP()

            self.numPointsSpin.setValue(int(state.get('points', self.numPointsSpin.value())))
            self.densitySpin.setValue(float(state.get('density', self.densitySpin.value())))
            self.interpolationComboBox.setCurrentIndex(1 if state.get('sampling') == 'density' else 0)
            defaultPath = self.qPathLineEdit.text()
            self.qPathLineEdit.setText(state['path'])
        except (KeyError, TypeError, ValueError):
            return False

        if not self.setBrillouinZone(quiet=True):
            self.qPathLineEdit.setText(defaultPath)
            return False
        return True

    def populateHSPTable(self, hsp: dict):
        self.hspTable.clearContents()
        self.hspTable.setRowCount(len(hsp))

        row = 0
        for label, coords in hsp.items():
            # Label
            labelItem = QTableWidgetItem(label)
            labelItem.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.hspTable.setItem(row, 0, labelItem)
            # Coordinates
            for i in range(3):
                coordItem = QTableWidgetItem(f'{coords[i]:.5f}')
                coordItem.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.hspTable.setItem(row, i+1, coordItem)
            row += 1

    def showContextMenu(self, position):
        menu = QMenu()
        addAction = menu.addAction("Add Row")
        deleteAction = menu.addAction("Delete Row")

        deleteAction.setEnabled(self.hspTable.rowCount() > len(self.dataset.highSymmetryPoints))

        action = menu.exec(self.hspTable.mapToGlobal(position))

        if action == deleteAction:
            selectedRows = set()
            for index in self.hspTable.selectedIndexes():
                selectedRows.add(index.row())

            # Remove rows in reverse order to avoid index shifting problems
            for row in sorted(selectedRows, reverse=True):
                self.hspTable.removeRow(row)
                self.setExtraHSP()

        elif action == addAction:
            row = self.hspTable.rowCount()
            self.hspTable.insertRow(row)

    @Slot(int, int)
    def validateCell(self, row, col):
        item = self.hspTable.item(row, col)
        text = item.text()

        if col == 0:
            if len(text) > 2:
                item.setText(text[:2])
            if len(text) > 1:
                if not text[1].isdigit():
                    item.setText(text[0])
            if len(text) > 0:
                if not text[0].isalpha():
                    item.setText('')

        elif col > 0:
            try:
                float(text)
            except ValueError:
                item.setText('')

        self.setExtraHSP()

    def setExtraHSP(self):
        self.dataset.extraHighSymmetryPoints = {}

        for row in range(len(self.dataset.highSymmetryPoints), self.hspTable.rowCount()):
            validExtraHSP = True
            for col in range(4):
                validExtraHSP  &= (self.hspTable.item(row, col) is not None and self.hspTable.item(row, col).text() != '')
            if validExtraHSP:
                label = self.hspTable.item(row, 0).text()
                kx = self.hspTable.item(row, 1).text()
                ky = self.hspTable.item(row, 2).text()
                kz = self.hspTable.item(row, 3).text()
                self.dataset.extraHighSymmetryPoints[label]=  [float(kx), float(ky), float(kz)]