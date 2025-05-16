# This Python file uses the following encoding: utf-8
from PySide6.QtCore import QObject, Signal
from pathlib import PurePath, Path
from qepy.lattice import Path as kPath
from glob import glob


class Options(QObject):
    # Dir signals
    saveDirChanged = Signal(str, str)
    diagoDirChanged = Signal(str, str)

    numQPointsChanged = Signal(int)

    def __init__(self):
        super().__init__()

        # Q-Path
        self.kList = [[[0.0, 0.0, 0.0], "Gamma"], [[0.0, 0.5, 0.0], "M"], [[0.3333333, 0.3333333, 0.0], "K"], [[0.0, 0.0, 0.0], "Gamma"]]
        self.intervals = [50, 10, 50]
        self.qPath = kPath(self.kList, self.intervals)

        # Dispersion
        self.nExcitons = 6

        # Absorption
        self.energyStep = 0.02
        self.energyMin = 4.0
        self.energyMax = 20.0

        # Excitons
        self.excMinIntensity = 0.1

    def setSaveDir(self, dir):
        file = Path(dir + '/ns.db1')
        if file.is_file():
            self.saveDir = dir
            self.saveDirChanged.emit(dir, "ns.db1 found")
        else:
            self.saveDirChanged.emit(dir, "ns.db1 not found!")

    def setDiagoDir(self, dir):
        files = glob(dir + '/ndb.BS_diago_Q*')
        self.nQpoints = len(files)

        if self.nQpoints > 0 :
            self.diagoDir = dir
            self.parentDir = Path(dir).parent.absolute()
            self.jobString = PurePath(self.diagoDir).name;
            self.diagoDirChanged.emit(dir, "ndb.BS_diago_Q* found - (" + str(self.nQpoints) + " Q-Points)")
            self.numQPointsChanged.emit(self.nQpoints)
        else:
            self.diagoDirChanged.emit(dir, "ndb.BS_diago_Q* not found!")

    def updateQPointValue(self, index, component, value):
        self.kList[index][0][component] = value
        self.qPath = kPath(self.kList, self.intervals)

    def updateQPointLabel(self, index, label):
        self.kList[index][1] = label
        self.qPath = kPath(self.kList, self.intervals)

    def updateInterval(self, index, value):
        if index < len(self.intervals):
            self.intervals[index] = value
            self.qPath = kPath(self.kList, self.intervals)

    def insertQPoint(self, index):
        qPoint = [[0.0, 0.0, 0.0], "Gamma"]
        self.kList.insert(index + 1, qPoint)
        self.intervals.append(10)
        self.qPath = kPath(self.kList, self.intervals)

    def removeQPoint(self, index):
        self.kList.pop(index)
        if index < len(self.intervals): self.intervals.pop(index)
        self.qPath = kPath(self.kList, self.intervals)

    def setNExcitons(self, n):
        if n < 1: n = 1
        self.nExcitons = n

    def setEnergyStep(self, step):
        if step <= 0.0: step = 0.001
        elif step > self.energyMax - self.energyMin: step = self.energyMax - self.energyMin
        self.energyStep = step

    def setEnergyMin(self, energy):
        if energy >= self.energyMax: energy = self.energyMax - self.energyStep
        if energy + self.energyStep > self.energyMax: self.energyStep = self.energyMax - self.energyMin
        self.energyMin = energy

    def setEnergyMax(self, energy):
        if energy <= self.energyMin: energy = self.energyMin + self.energyStep
        if self.energyMin + self.energyStep > energy: energy = self.energyMin + self.energyStep
        self.energyMax = energy

    def setExcMinIntensity(self, intensity):
        if intensity < 0.0: intensity = 0.0
        if intensity > 1.0: intensity = 1.0
        self.excMinIntensity = intensity
