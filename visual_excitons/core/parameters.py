"""
The parameters of the calculations and of how their results are shown, set in
the Spectra controls and in the Wave function controls: plain values (the
controls enforce their ranges; sessions keep them through the controls, see
gui/persistence.py). The dataset they apply to is core.dataset.Dataset.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SpectraParameters:
    """The dispersion and the absorption spectra (energies in eV)."""

    nExcitons: int = 6                  # excitons of the dispersion
    energyStep: float = 0.02            # sampling of the absorption spectra
    energyMin: float = 4.0
    energyMax: float = 20.0
    # Automatic range: the excitons of each spectrum, plus a margin (see calculations)
    absorptionAutoRange: bool = True
    excMinIntensity: float = 0.1        # bright excitons: intensity relative to the largest

    # The range keeps min < max with room for one step

    def setEnergyStep(self, step):
        if step <= 0.0:
            step = 0.001
        elif step > self.energyMax - self.energyMin:
            step = self.energyMax - self.energyMin
        self.energyStep = step

    def setEnergyMin(self, energy):
        if energy >= self.energyMax:
            energy = self.energyMax - self.energyStep
        if energy + self.energyStep > self.energyMax:
            self.energyStep = self.energyMax - self.energyMin
        self.energyMin = energy

    def setEnergyMax(self, energy):
        if energy <= self.energyMin:
            energy = self.energyMin + self.energyStep
        if self.energyMin + self.energyStep > energy:
            energy = self.energyMin + self.energyStep
        self.energyMax = energy


@dataclass
class WavefunctionParameters:
    """The wave function of the selected exciton, and how it is drawn."""

    particle: str = 'h'                 # the fixed particle: 'h' (hole) or 'e' (electron)
    holePosition: list = field(default_factory=lambda: [0.0, 0.0, 0.0])        # reduced, in the cell
    electronPosition: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    cutoff: float = 10.0                # plane-wave cutoff (Ry)
    supercell: list = field(default_factory=lambda: [1, 1, 1])
    # Isosurfaces (levels relative to the maximum) and volume
    isoLevel: float = 0.5
    numIsoLevels: int = 10
    isoOpacity: float = 0.3
    isoSetOpacity: float = 0.1
    sliceDensity: int = 5
    volumeOpacity: float = 0.8
    volumeContrast: float = 1.0
    # Atoms and bonds (ball-and-stick): atoms are drawn with their covalent
    # radius times atomScale; bonds join atoms closer than bondTolerance times
    # the sum of their covalent radii
    atomScale: float = 0.5
    bondTolerance: float = 1.15
    bondRadius: float = 0.12            # Å
    bondColoring: int = 0               # 0: half bonds in the colors of their atoms, 1: uniform grey

    def position(self, particle=None):
        """The position of `particle` ('h' or 'e'; the fixed one by default)."""
        return self.holePosition if (particle or self.particle) == 'h' else self.electronPosition

    def setPosition(self, position, particle=None):
        """Set the position of `particle` ('h' or 'e'; the fixed one by default)."""
        if (particle or self.particle) == 'h':
            self.holePosition = position
        else:
            self.electronPosition = position

    def positionCartesian(self, cell):
        """
        The fixed particle in Cartesian coordinates (the units of `cell`): the
        wave function is computed with it in the central cell of the (odd)
        supercell, so that is where it is shown.
        """
        return np.asarray(cell, dtype=float).T @ (np.asarray(self.position(), dtype=float)
                                                  + np.asarray(self.supercell) // 2)
