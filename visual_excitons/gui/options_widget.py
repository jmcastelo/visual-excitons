from PySide6.QtCore import Slot, Qt
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QHBoxLayout, QVBoxLayout
from PySide6.QtWidgets import QComboBox, QGroupBox, QFormLayout, QGridLayout, QSizePolicy, QMessageBox, QSpinBox, QDoubleSpinBox
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QMenu, QHeaderView
from pathlib import Path

from visual_excitons.core.atomic_data import BOHR_TO_ANGSTROM
from .inspector import NoteLabel


class OptionsWidget(QWidget):
    """System page: data directories, crystal lattice and Brillouin-zone path."""

    def __init__(self, options):
        QWidget.__init__(self)

        # All options are contained in this object

        self.options = options

        # Calculation type

        self.calcTypeComboBox = QComboBox()
        self.calcTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.calcTypeComboBox.addItems(['DFT+BSE', 'DFT+GW+BSE'])
        self.calcTypeComboBox.setCurrentIndex(1 if self.options.gw else 0)
        self.calcTypeComboBox.currentIndexChanged.connect(self.setGW)
        self.options.gwChanged.connect(lambda gw: self.calcTypeComboBox.setCurrentIndex(1 if gw else 0))

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
            2, 'GW:', 'Directory with the ndb.QP database of the GW calculation', self.selectQPDir, self.editQPDir)

        self.setStatus(self.saveLabel, 'ns.db1 not found!')
        self.setStatus(self.diagoLabel, 'ndb.BS_diago_Q* not found!')
        self.setStatus(self.qpLabel, 'ndb.QP not found!')

        self.options.saveDirChanged.connect(self.setSaveLabel)
        self.options.diagoDirChanged.connect(self.setDiagoLabel)
        self.options.qpDirChanged.connect(self.setQPLabel)
        self.options.databaseFound.connect(self.onDatabaseFound)

        dirGroupBox = QGroupBox('Data')
        dirGroupBox.setLayout(dirLayout)

        # Bravais lattice

        self.ibravComboBox = QComboBox()
        self.ibravComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.ibravComboBox.addItems([str(ibrav) for ibrav in self.options.availableIbrav])
        self.ibravComboBox.setToolTip('Bravais lattice type (Quantum ESPRESSO ibrav), detected from ns.db1')
        self.ibravComboBox.currentTextChanged.connect(self.getLatticeData)
        self.ibravComboBox.setEnabled(False)
        self.options.databaseFound.connect(self.setIbrav)

        self.variantLabel = QLabel()

        self.parameterLabels = {name: QLabel() for name in ('a', 'b', 'c', 'alpha', 'beta', 'gamma')}
        for label in self.parameterLabels.values():
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        bravaisLayout = QGridLayout()
        bravaisLayout.setColumnStretch(4, 1)
        bravaisLayout.setHorizontalSpacing(12)
        bravaisLayout.addWidget(QLabel('ibrav:'), 0, 0)
        bravaisLayout.addWidget(self.ibravComboBox, 0, 1)
        bravaisLayout.addWidget(QLabel('Variant:'), 0, 2)
        bravaisLayout.addWidget(self.variantLabel, 0, 3)
        for row, (length, angle, angleSymbol) in enumerate((('a', 'alpha', 'α'), ('b', 'beta', 'β'), ('c', 'gamma', 'γ')), start=1):
            bravaisLayout.addWidget(QLabel(f'{length}:'), row, 0)
            bravaisLayout.addWidget(self.parameterLabels[length], row, 1)
            bravaisLayout.addWidget(QLabel(f'{angleSymbol}:'), row, 2)
            bravaisLayout.addWidget(self.parameterLabels[angle], row, 3)

        bravaisGroup = QGroupBox('Crystal lattice')
        bravaisGroup.setLayout(bravaisLayout)

        # Q-path

        self.qPathLineEdit = QLineEdit()
        self.qPathLineEdit.setToolTip('Labels of the high-symmetry points along the path;\n'
                                      'commas separate disconnected sections')

        self.numPointsSpin = QSpinBox(minimum=0, maximum=999999)
        self.numPointsSpin.setValue(100)

        self.densitySpin = QDoubleSpinBox(minimum=0, maximum=9999, singleStep=0.1)
        self.densitySpin.setValue(10.0)
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

        self.hspTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.hspTable.customContextMenuRequested.connect(self.showContextMenu)

        self.hspTable.cellChanged.connect(self.validateCell)

        hspLayout = QVBoxLayout()
        hspLayout.addWidget(self.hspTable)
        hspLayout.addWidget(NoteLabel('Coordinates are fractions of the reciprocal lattice vectors. '
                                      'Right-click the table to add or delete extra points.'))

        hspGroupBox = QGroupBox('High-symmetry points')
        hspGroupBox.setLayout(hspLayout)

        # Main layout: setup on the left, points on the right

        leftLayout = QVBoxLayout()
        leftLayout.addWidget(dirGroupBox)
        leftLayout.addWidget(bravaisGroup)
        leftLayout.addWidget(qPathGroupBox)
        leftLayout.addStretch(1)

        mainLayout = QHBoxLayout()
        mainLayout.setContentsMargins(16, 12, 16, 12)
        mainLayout.setSpacing(16)
        mainLayout.addLayout(leftLayout, 3)
        mainLayout.addWidget(hspGroupBox, 2)

        self.setLayout(mainLayout)

    @staticmethod
    def setStatus(label, text):
        """Status of a directory, with a green tick or a red cross."""
        ok = 'not found' not in text
        symbol, color = ('✓', '#2e9e4f') if ok else ('✗', '#d9453b')
        label.setText(f'<span style="color:{color}; font-weight:bold">{symbol}</span>&nbsp;{text}')

    @Slot(int)
    def setGW(self, index):
        gw = (index == 1)
        self.options.setGW(gw)
        self.qpDirLabel.setVisible(gw)
        self.qpDirEdit.setVisible(gw)
        self.selectQPDirButton.setVisible(gw)
        self.qpLabel.setVisible(gw)

    @Slot()
    def selectSaveDir(self):
        directory = QFileDialog.getExistingDirectory(self, "Open Directory", self.options.saveDir, QFileDialog.Option.ShowDirsOnly)
        if directory != '':
            self.options.setSaveDir(directory)
            self.saveDirEdit.setText(directory)

    @Slot()
    def selectDiagoDir(self):
        directory = QFileDialog.getExistingDirectory(self, "Open Directory", self.options.diagoDir, QFileDialog.Option.ShowDirsOnly)
        if directory != '':
            self.options.setDiagoDir(directory)
            self.diagoDirEdit.setText(directory)

    @Slot()
    def selectQPDir(self):
        directory = QFileDialog.getExistingDirectory(self, "Open Directory", self.options.qpDir or self.options.diagoDir, QFileDialog.Option.ShowDirsOnly)
        if directory != '':
            self.options.setQPDir(directory)
            self.qpDirEdit.setText(directory)

    @Slot()
    def editSaveDir(self):
        if Path(self.saveDirEdit.text()).is_dir():
            self.options.setSaveDir(self.saveDirEdit.text())
        else:
            self.saveDirEdit.setText(self.options.saveDir)

    @Slot()
    def editDiagoDir(self):
        if Path(self.diagoDirEdit.text()).is_dir():
            self.options.setDiagoDir(self.diagoDirEdit.text())
        else:
            self.diagoDirEdit.setText(self.options.diagoDir)

    @Slot()
    def editQPDir(self):
        if Path(self.qpDirEdit.text()).is_dir():
            self.options.setQPDir(self.qpDirEdit.text())
        else:
            self.qpDirEdit.setText(self.options.qpDir)

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
    def setIbrav(self, found):
        if found:
            ibrav = self.options.detectLatticeType()
            if ibrav:
                self.ibravComboBox.setCurrentText(str(ibrav))
            else:
                msgBox = QMessageBox()
                msgBox.setText('Warning')
                msgBox.setInformativeText('Unable to detect Bravais lattice type')
                msgBox.exec()

                self.ibravComboBox.setCurrentIndex(0)

            self.ibravComboBox.setEnabled(True)
        else:
            self.ibravComboBox.setEnabled(False)

    @Slot(int)
    def getLatticeData(self, ibrav):
        try:
            self.options.setLatticeData(int(ibrav))
        except ValueError as error:
            self.qPathLineEdit.clear()
            self.variantLabel.clear()
            self.options.setIbrav(-1)
            self.setPathButton.setEnabled(False)

            msgBox = QMessageBox()
            msgBox.setText('Error')
            msgBox.setInformativeText(str(error))
            msgBox.exec()
        else:
            self.qPathLineEdit.setText(self.options.defaultPath)
            self.variantLabel.setText(self.options.variant)
            self.options.setIbrav(int(ibrav))
            self.setPathButton.setEnabled(True)
            self.populateHSPTable(self.options.highSymmetryPoints)

    @Slot(bool)
    def onDatabaseFound(self, found):
        if found:
            self.variantLabel.setText(self.options.variant)
            self.qPathLineEdit.setText(self.options.defaultPath)

            # Lengths are in Bohr in the database
            for paramName, label in self.parameterLabels.items():
                value = self.options.latticeParameters[paramName]
                if paramName in ('a', 'b', 'c'):
                    label.setText(f'{value * BOHR_TO_ANGSTROM:.5f} Å')
                    label.setToolTip(f'{value:.5f} Bohr')
                else:
                    label.setText(f'{value:.4f}°')

        else:
            self.variantLabel.clear()
            self.qPathLineEdit.clear()

            for param, label in self.parameterLabels.items():
                label.clear()

    @Slot(int)
    def updateInterpolationEdit(self, index):
        if index == 0:
            self.numPointsSpin.setVisible(True)
            self.densitySpin.setVisible(False)
        elif index == 1:
            self.numPointsSpin.setVisible(False)
            self.densitySpin.setVisible(True)

    @Slot()
    def setBrillouinZone(self):
        try:
            if self.interpolationComboBox.currentIndex() == 0:
                self.options.setBrillouinZone(path=self.qPathLineEdit.text(), npoints=self.numPointsSpin.value())
            elif self.interpolationComboBox.currentIndex() == 1:
                self.options.setBrillouinZone(path=self.qPathLineEdit.text(), density=self.densitySpin.value())
        except ValueError as error:
            msgBox = QMessageBox()
            msgBox.setText('Error')
            msgBox.setInformativeText(str(error))
            msgBox.exec()
        else:
            self.qPathLineEdit.setText(self.options.getPathString())

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

        deleteAction.setEnabled(self.hspTable.rowCount() > len(self.options.highSymmetryPoints))

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
        self.options.extraHighSymmetryPoints = {}

        for row in range(len(self.options.highSymmetryPoints), self.hspTable.rowCount()):
            validExtraHSP = True
            for col in range(4):
                validExtraHSP  &= (self.hspTable.item(row, col) is not None and self.hspTable.item(row, col).text() != '')
            if validExtraHSP:
                label = self.hspTable.item(row, 0).text()
                kx = self.hspTable.item(row, 1).text()
                ky = self.hspTable.item(row, 2).text()
                kz = self.hspTable.item(row, 3).text()
                self.options.extraHighSymmetryPoints[label]=  [float(kx), float(ky), float(kz)]