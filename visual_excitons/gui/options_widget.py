from PySide6.QtCore import Slot, Qt
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QHBoxLayout, QVBoxLayout
from PySide6.QtWidgets import QComboBox, QGroupBox, QFormLayout, QGridLayout, QSizePolicy, QMessageBox, QSpinBox, QDoubleSpinBox
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QMenu, QHeaderView
from pathlib import Path


class OptionsWidget(QWidget):
    def __init__(self, options):
        QWidget.__init__(self)

        # All options are contained in this object

        self.options = options

        # Calculation type

        calcTypeComboBox = QComboBox()
        calcTypeComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        calcTypeComboBox.addItems(['DFT+BSE', 'DFT+GW+BSE'])
        calcTypeComboBox.setCurrentIndex(1)
        calcTypeComboBox.currentIndexChanged.connect(self.setGW)

        calcTypeLayout = QFormLayout()
        calcTypeLayout.addRow('Calculation type', calcTypeComboBox)

        # SAVE Dir widgets

        saveDirLabel = QLabel('SAVE Directory:')

        selectSaveDirButton = QPushButton('Select')
        selectSaveDirButton.clicked.connect(self.selectSaveDir)
        selectSaveDirButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.saveDirEdit = QLineEdit()
        self.saveDirEdit.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        self.saveDirEdit.editingFinished.connect(self.editSaveDir)

        saveLayout = QHBoxLayout()
        saveLayout.addWidget(saveDirLabel)
        saveLayout.addWidget(self.saveDirEdit)
        saveLayout.addWidget(selectSaveDirButton)

        self.saveLabel = QLabel('ns.db1 not found!')
        self.options.saveDirChanged.connect(self.setSaveLabel)

        self.options.databaseFound.connect(self.onDatabaseFound)

        # Diago Dir widgets

        diagoDirLabel = QLabel('Diago Directory:')

        selectDiagoDirButton = QPushButton('Select')
        selectDiagoDirButton.clicked.connect(self.selectDiagoDir)
        selectDiagoDirButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.diagoDirEdit = QLineEdit()
        self.diagoDirEdit.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        self.diagoDirEdit.editingFinished.connect(self.editDiagoDir)

        diagoLayout = QHBoxLayout()
        diagoLayout.addWidget(diagoDirLabel)
        diagoLayout.addWidget(self.diagoDirEdit)
        diagoLayout.addWidget(selectDiagoDirButton)

        self.diagoLabel = QLabel('ndb.BS_diago_Q* not found!')
        self.options.diagoDirChanged.connect(self.setDiagoLabel)

        # QP Dir widgets

        self.qpDirLabel = QLabel('QP Directory:')

        self.selectQPDirButton = QPushButton('Select')
        self.selectQPDirButton.clicked.connect(self.selectQPDir)
        self.selectQPDirButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.qpDirEdit = QLineEdit()
        self.qpDirEdit.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)
        self.qpDirEdit.editingFinished.connect(self.editQPDir)

        qpLayout = QHBoxLayout()
        qpLayout.addWidget(self.qpDirLabel)
        qpLayout.addWidget(self.qpDirEdit)
        qpLayout.addWidget(self.selectQPDirButton)

        self.qpLabel = QLabel('ndb.QP not found!')
        self.options.qpDirChanged.connect(self.setQPLabel)

        # Dir group

        dirLayout = QVBoxLayout()
        dirLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        dirLayout.addLayout(calcTypeLayout)
        dirLayout.addLayout(saveLayout)
        dirLayout.addWidget(self.saveLabel)
        dirLayout.addLayout(diagoLayout)
        dirLayout.addWidget(self.diagoLabel)
        dirLayout.addLayout(qpLayout)
        dirLayout.addWidget(self.qpLabel)

        dirGroupBox = QGroupBox('Directories')
        dirGroupBox.setLayout(dirLayout)

        # Bravais lattice widgets

        bravaisLayout = QFormLayout()

        # ibrav selector

        self.ibravComboBox = QComboBox()
        self.ibravComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.ibravComboBox.addItems([str(ibrav) for ibrav in self.options.availableIbrav])
        self.ibravComboBox.currentTextChanged.connect(self.getLatticeData)

        self.ibravComboBox.setEnabled(False)
        self.options.databaseFound.connect(self.setIbrav)

        bravaisLayout.addRow('ibrav', self.ibravComboBox)

        # Variant label

        self.variantLabel = QLabel()
        bravaisLayout.addRow('Variant', self.variantLabel)

        # Parameter labels

        self.parameterLabels = {
            'a': QLabel(),
            'b': QLabel(),
            'c': QLabel(),
            'alpha': QLabel(),
            'beta': QLabel(),
            'gamma': QLabel()
        }

        for param, label in self.parameterLabels.items():
            bravaisLayout.addRow(param, label)

        # Bravais lattice group

        bravaisGroup = QGroupBox('Bravais lattice')
        bravaisGroup.setLayout(bravaisLayout)

        # Q-Path widgets

        qPathLayout = QVBoxLayout()
        qPathLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Path line edit

        self.qPathLineEdit = QLineEdit()
        self.qPathLineEdit.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)

        formLayout = QFormLayout()
        formLayout.addRow('Path', self.qPathLineEdit)
        qPathLayout.addLayout(formLayout)

        # Interpolation widgets

        self.numPointsSpin = QSpinBox()
        self.numPointsSpin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.numPointsSpin.setMinimum(0)
        self.numPointsSpin.setMaximum(999999)
        self.numPointsSpin.setValue(100)

        self.densitySpin = QDoubleSpinBox()
        self.densitySpin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.densitySpin.setMinimum(0)
        self.densitySpin.setMaximum(9999)
        self.densitySpin.setSingleStep(0.1)
        self.densitySpin.setValue(10.0)
        self.densitySpin.setVisible(False)

        self.interpolationComboBox = QComboBox()
        self.interpolationComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.interpolationComboBox.addItems(['Number of points', 'Density'])

        self.interpolationLayout = QHBoxLayout()
        self.interpolationLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.interpolationLayout.addWidget(self.interpolationComboBox, 0, Qt.AlignmentFlag.AlignLeft)
        self.interpolationLayout.addWidget(self.numPointsSpin, 0, Qt.AlignmentFlag.AlignLeft)
        self.interpolationLayout.addWidget(self.densitySpin, 0, Qt.AlignmentFlag.AlignLeft)
        self.interpolationComboBox.currentIndexChanged.connect(self.updateInterpolationEdit)
        qPathLayout.addLayout(self.interpolationLayout)

        # Set path button

        self.setPathButton = QPushButton('Set Q-Path')
        self.setPathButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.setPathButton.clicked.connect(self.setBrillouinZone)
        qPathLayout.addWidget(self.setPathButton)

        # Q-Path group

        qPathGroupBox = QGroupBox('Q-Path')
        qPathGroupBox.setLayout(qPathLayout)

        # High symmetry points widgets

        hspLayout = QVBoxLayout()
        hspLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # High symmetry points table

        self.hspTable = QTableWidget()
        self.hspTable.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
        self.hspTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.hspTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.hspTable.setColumnCount(4)
        self.hspTable.setHorizontalHeaderLabels(['Label', 'Kx', 'Ky', 'Kz'])

        self.hspTable.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.hspTable.customContextMenuRequested.connect(self.showContextMenu)

        self.hspTable.cellChanged.connect(self.validateCell)

        hspLayout.addWidget(self.hspTable)

        # Special points group

        hspGroupBox = QGroupBox('High symmetry points')
        hspGroupBox.setLayout(hspLayout)

        # Main layout

        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(dirGroupBox, 0, 0, 1, 2)
        mainLayout.addWidget(bravaisGroup, 1, 0, 1, 1)
        mainLayout.addWidget(qPathGroupBox, 1, 1, 1, 1)
        mainLayout.addWidget(hspGroupBox, 0, 2, 3, 1)

        self.setLayout(mainLayout)

    @Slot(int)
    def setGW(self, index):
        gw = (index == 1)
        self.options.gw = gw
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
        directory = QFileDialog.getExistingDirectory(self, "Open Directory", self.options.diagoDir, QFileDialog.Option.ShowDirsOnly)
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
        self.saveLabel.setText(text)

    @Slot()
    def setDiagoLabel(self, dir, text):
        self.diagoDirEdit.setText(dir)
        self.diagoLabel.setText(text)

    @Slot()
    def setQPLabel(self, dir, text):
        self.qpDirEdit.setText(dir)
        self.qpLabel.setText(text)

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

            for paramName, label in self.parameterLabels.items():
                label.setText(f"{self.options.latticeParameters[paramName]:.5f}")

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