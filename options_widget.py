from PySide6.QtCore import Slot, Qt
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QHBoxLayout, QVBoxLayout
from PySide6.QtWidgets import QComboBox, QGroupBox, QFormLayout, QGridLayout, QSizePolicy, QMessageBox, QSpinBox, QDoubleSpinBox
from pathlib import Path


class OptionsWidget(QWidget):
    def __init__(self, options):
        QWidget.__init__(self)

        # All options are contained in this object
        self.options = options

        # SAVE Dir widgets
        saveDirLabel = QLabel('SAVE Directory:')

        selectSaveDirButton = QPushButton('Select')
        selectSaveDirButton.clicked.connect(self.selectSaveDir)
        selectSaveDirButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.saveDirEdit = QLineEdit()
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
        self.diagoDirEdit.editingFinished.connect(self.editDiagoDir)

        diagoLayout = QHBoxLayout()
        diagoLayout.addWidget(diagoDirLabel)
        diagoLayout.addWidget(self.diagoDirEdit)
        diagoLayout.addWidget(selectDiagoDirButton)

        self.diagoLabel = QLabel('ndb.BS_diago_Q* not found!')
        self.options.diagoDirChanged.connect(self.setDiagoLabel)

        # QP Dir widgets
        qpDirLabel = QLabel('QP Directory:')

        selectQPDirButton = QPushButton('Select')
        selectQPDirButton.clicked.connect(self.selectQPDir)
        selectQPDirButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.qpDirEdit = QLineEdit()
        self.qpDirEdit.editingFinished.connect(self.editQPDir)

        qpLayout = QHBoxLayout()
        qpLayout.addWidget(qpDirLabel)
        qpLayout.addWidget(self.qpDirEdit)
        qpLayout.addWidget(selectQPDirButton)

        self.qpLabel = QLabel('ndb.QP not found!')
        self.options.qpDirChanged.connect(self.setQPLabel)

        # Dir group
        dirLayout = QVBoxLayout()
        dirLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        dirLayout.addLayout(saveLayout)
        dirLayout.addWidget(self.saveLabel)
        dirLayout.addLayout(diagoLayout)
        dirLayout.addWidget(self.diagoLabel)
        dirLayout.addLayout(qpLayout)
        dirLayout.addWidget(self.qpLabel)

        dirGroupBox = QGroupBox("Directories")
        dirGroupBox.setLayout(dirLayout)

        # BZ widgets

        qPathLayout = QGridLayout()
        qPathLayout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignVCenter)

        # ibrav
        self.ibravComboBox = QComboBox()
        self.ibravComboBox.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.ibravComboBox.addItems([str(ibrav) for ibrav in self.options.availableIbrav])
        self.ibravComboBox.currentTextChanged.connect(self.getLatticeData)

        self.ibravComboBox.setEnabled(False)
        self.options.databaseFound.connect(self.setIbrav)

        bzFormLayout = QFormLayout()
        bzFormLayout.addRow('ibrav', self.ibravComboBox)
        qPathLayout.addLayout(bzFormLayout, 0, 0)

        self.parameterLabels = {
            'a': QLabel(),
            'b': QLabel(),
            'c': QLabel(),
            'alpha': QLabel(),
            'beta': QLabel(),
            'gamma': QLabel()
        }

        """
        self.qPathPoints = 0

        self.qPathTableWidget = QTableWidget(self)
        self.qPathTableWidget.setColumnCount(7)
        self.qPathTableWidget.setHorizontalHeaderLabels(["x", "y", "z", "Label", "Intervals", "Insert", "Remove"])
        self.qPathTableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.initQPathTableWidget()
        """

        col = 0
        for param, label in self.parameterLabels.items():
            formLayout = QFormLayout()
            formLayout.addRow(param, label)
            qPathLayout.addLayout(formLayout, 1, col)
            col += 1

        # Variant
        self.variantLabel = QLabel()
        formLayout = QFormLayout()
        formLayout.addRow('Variant', self.variantLabel)

        qPathLayout.addLayout(formLayout, 0, 1)

        # Path
        self.qPathLineEdit = QLineEdit()
        self.qPathLineEdit.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Maximum)

        formLayout = QFormLayout()
        formLayout.addRow('Path', self.qPathLineEdit)
        qPathLayout.addLayout(formLayout, 0, 2, 1, 3)

        # Interpolation
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
        self.interpolationLayout.addWidget(self.interpolationComboBox)
        self.interpolationLayout.addWidget(self.numPointsSpin)
        self.interpolationLayout.addWidget(self.densitySpin)
        self.interpolationComboBox.currentIndexChanged.connect(self.updateInterpolationEdit)
        qPathLayout.addLayout(self.interpolationLayout, 0, 5)

        # Set path
        self.setPathButton = QPushButton('Set Q-Path')
        self.setPathButton.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.setPathButton.clicked.connect(self.setBrillouinZone)
        qPathLayout.addWidget(self.setPathButton, 2, 0)

        qPathGroupBox = QGroupBox("Q-Path")
        qPathGroupBox.setLayout(qPathLayout)

        # Main layout
        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        mainLayout.addWidget(dirGroupBox, 0, 0)
        mainLayout.addWidget(qPathGroupBox, 1, 0)

        self.setLayout(mainLayout)

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
            if ibrav > 0:
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

    @Slot(bool)
    def onDatabaseFound(self, found):
        if found:
            self.variantLabel.setText(self.options.variant)
            self.qPathLineEdit.setText(self.options.defaultPath)

            for paramName, label in self.parameterLabels.items():
                label.setText(f"{self.options.latticeParameters[paramName]}")
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

    """
    @Slot()
    def setQPLabel(self, dir, text):
        self.qpDirEdit.setText(dir)
        self.qpLabel.setText(text)

    def initQPathTableWidget(self):
        self.qPathTableWidget.setRowCount(0)

        self.qPathPoints = 0

        qPath = self.options.qPath.as_dict()
        nQPoints = len(qPath['kpoints'])
        nIntervals = len(qPath['intervals'])

        for i in range(nQPoints):
            self.addQPointRow(qPath['kpoints'][i], qPath['klabels'][i], qPath['intervals'][i] if i < nIntervals else 0)

        # Disable remove buttons from last 2 rows
        if self.qPathPoints <= 2:
            self.qPathTableWidget.cellWidget(0, 5).setEnabled(False)
            self.qPathTableWidget.cellWidget(1, 5).setEnabled(False)

        lastIntervalLineEdit = self.qPathTableWidget.cellWidget(self.qPathPoints - 1, 4)
        lastIntervalLineEdit.setEnabled(False)

    def addQPointRow(self, qPoint, label, interval):
        xLineEdit = QLineEdit(f"{qPoint[0]}")
        yLineEdit = QLineEdit(f"{qPoint[1]}")
        zLineEdit = QLineEdit(f"{qPoint[2]}")
        labelLineEdit = QLineEdit(label)
        intervalLineEdit = QLineEdit(str(interval))

        insertPushButton = QPushButton("Insert")
        removePushButton = QPushButton("Remove")

        xLineEdit.setValidator(QDoubleValidator())
        yLineEdit.setValidator(QDoubleValidator())
        zLineEdit.setValidator(QDoubleValidator())

        intervalValidator = QIntValidator()
        intervalValidator.setBottom(0)
        intervalLineEdit.setValidator(intervalValidator)

        xLineEdit.editingFinished.connect(self.updateQPoint)
        yLineEdit.editingFinished.connect(self.updateQPoint)
        zLineEdit.editingFinished.connect(self.updateQPoint)
        labelLineEdit.editingFinished.connect(self.updateQPoint)
        intervalLineEdit.editingFinished.connect(self.updateQPoint)

        insertPushButton.clicked.connect(self.insertQPoint)
        removePushButton.clicked.connect(self.removeQPoint)

        self.qPathTableWidget.insertRow(self.qPathPoints)

        self.qPathTableWidget.setCellWidget(self.qPathPoints, 0, xLineEdit)
        self.qPathTableWidget.setCellWidget(self.qPathPoints, 1, yLineEdit)
        self.qPathTableWidget.setCellWidget(self.qPathPoints, 2, zLineEdit)
        self.qPathTableWidget.setCellWidget(self.qPathPoints, 3, labelLineEdit)
        self.qPathTableWidget.setCellWidget(self.qPathPoints, 4, intervalLineEdit)
        self.qPathTableWidget.setCellWidget(self.qPathPoints, 5, insertPushButton)
        self.qPathTableWidget.setCellWidget(self.qPathPoints, 6, removePushButton)

        self.qPathPoints += 1

    def insertQPoint(self):
        rowIndex = self.qPathTableWidget.currentRow()
        self.options.insertQPoint(rowIndex)
        self.initQPathTableWidget()

    def removeQPoint(self):
        rowIndex = self.qPathTableWidget.currentRow()
        self.options.removeQPoint(rowIndex)
        self.initQPathTableWidget()

    @Slot()
    def updateQPoint(self):
        rowIndex = self.qPathTableWidget.currentRow()
        colIndex = self.qPathTableWidget.currentColumn()

        currentLineEdit = self.qPathTableWidget.cellWidget(rowIndex, colIndex)

        if colIndex < 3:
            self.options.updateQPointValue(rowIndex, colIndex, float(currentLineEdit.text()))
        elif colIndex == 3:
            self.options.updateQPointLabel(rowIndex, currentLineEdit.text())
        elif colIndex == 4:
            self.options.updateInterval(rowIndex, int(currentLineEdit.text()))
    """