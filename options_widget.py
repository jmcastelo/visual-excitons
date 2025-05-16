# This Python file uses the following encoding: utf-8
from PySide6.QtCore import Slot, Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QFileDialog, QHBoxLayout, QVBoxLayout, QGroupBox, QTableWidget, QHeaderView, QTableWidgetItem, QGridLayout, QSizePolicy
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
        selectSaveDirButton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.saveDirEdit = QLineEdit()
        self.saveDirEdit.editingFinished.connect(self.editSaveDir)

        saveLayout = QHBoxLayout()
        saveLayout.addWidget(saveDirLabel)
        saveLayout.addWidget(self.saveDirEdit)
        saveLayout.addWidget(selectSaveDirButton)

        self.saveLabel = QLabel('ns.db1 not found!')
        self.options.saveDirChanged.connect(self.setSaveLabel)

        # Diago Dir widgets
        diagoDirLabel = QLabel('Diago Directory:')

        selectDiagoDirButton = QPushButton('Select')
        selectDiagoDirButton.clicked.connect(self.selectDiagoDir)
        selectDiagoDirButton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)

        self.diagoDirEdit = QLineEdit()
        self.diagoDirEdit.editingFinished.connect(self.editDiagoDir)

        diagoLayout = QHBoxLayout()
        diagoLayout.addWidget(diagoDirLabel)
        diagoLayout.addWidget(self.diagoDirEdit)
        diagoLayout.addWidget(selectDiagoDirButton)

        self.diagoLabel = QLabel('ndb.BS_diago_Q* not found!')
        self.options.diagoDirChanged.connect(self.setDiagoLabel)

        # Dir group
        dirLayout = QVBoxLayout()
        dirLayout.setAlignment(Qt.AlignTop)
        dirLayout.addLayout(saveLayout)
        dirLayout.addWidget(self.saveLabel)
        dirLayout.addLayout(diagoLayout)
        dirLayout.addWidget(self.diagoLabel)

        dirGroupBox = QGroupBox("Directories")
        dirGroupBox.setLayout(dirLayout)

        # Q-Path widgets
        self.qPathPoints = 0

        self.qPathTableWidget = QTableWidget(self)
        self.qPathTableWidget.setColumnCount(7)
        self.qPathTableWidget.setHorizontalHeaderLabels(["x", "y", "z", "Label", "Intervals", "Insert", "Remove"])
        self.qPathTableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.initQPathTableWidget()

        qPathLayout = QVBoxLayout()
        qPathLayout.setAlignment(Qt.AlignTop)
        qPathLayout.addWidget(self.qPathTableWidget)

        qPathGroupBox = QGroupBox("Q-Path")
        qPathGroupBox.setLayout(qPathLayout)

        # Main layout
        mainLayout = QGridLayout()
        mainLayout.setAlignment(Qt.AlignTop)
        mainLayout.addWidget(dirGroupBox, 0, 0)
        mainLayout.addWidget(qPathGroupBox, 1, 0)

        self.setLayout(mainLayout)

    @Slot()
    def selectSaveDir(self):
        dir = QFileDialog.getExistingDirectory(self, "Open Directory", self.options.saveDir, QFileDialog.ShowDirsOnly)
        if dir != "":
            self.options.setSaveDir(dir)
            self.saveDirEdit.setText(dir)

    @Slot()
    def selectDiagoDir(self):
        dir = QFileDialog.getExistingDirectory(self, "Open Directory", self.options.diagoDir, QFileDialog.ShowDirsOnly)
        if dir != "":
            self.options.setDiagoDir(dir)
            self.diagoDirEdit.setText(dir)

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
