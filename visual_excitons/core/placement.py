"""
Placing the fixed particle of the wave function: the own density of that
particle (see yambopy_ext.bse.exciton_particle_density and
Calculations.computeParticleDensity) at a position, its largest values, and
the atoms near them. Positions in crystal coordinates of the unit cell, the
cell in Bohr (rows: a, b, c).
"""

import itertools

import numpy as np

from .atomic_data import BOHR_TO_ANGSTROM

_NEIGHBOURS = np.array(list(itertools.product((-1, 0, 1), repeat=3)), dtype=float)


def gridIndex(position, shape):
    """The point of a unit-cell grid of `shape` nearest `position` (as ex_wf2Real snaps the fixed particle)."""
    shape = np.asarray(shape)
    return tuple(int(i) for i in np.rint(np.asarray(position, dtype=float) % 1.0 * shape).astype(int) % shape)


def gridPosition(index, shape):
    """The crystal coordinates of a point of a unit-cell grid."""
    return [float(i) / int(n) for i, n in zip(index, shape)]


def densityShare(density, position):
    """The density at the grid point nearest `position`, as a share of its largest value."""
    density = np.asarray(density)
    top = float(density.max())
    return float(density[gridIndex(position, density.shape)]) / top if top > 0 else 0.0


def nearestAtom(position, cell, atomPositions):
    """
    The atom nearest `position` (any periodic image): its index and the
    distance in Å. `atomPositions`: Cartesian, Bohr, as the cell.
    """
    cell = np.asarray(cell, dtype=float)
    atoms = np.asarray(atomPositions, dtype=float) @ np.linalg.inv(cell)
    d = np.asarray(position, dtype=float)[None, :] - atoms
    d -= np.rint(d)
    distances = np.linalg.norm((d[:, None, :] + _NEIGHBOURS[None, :, :]) @ cell, axis=-1).min(axis=1)
    i = int(np.argmin(distances))
    return i, float(distances[i] * BOHR_TO_ANGSTROM)
