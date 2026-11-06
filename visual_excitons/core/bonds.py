"""
Bonds between atoms of a periodic crystal.

Two atoms are bonded when their distance is at most `tolerance` times the sum
of their covalent radii, the criterion of ASE, Jmol and VESTA's default search.
All lengths are in Bohr.
"""

import numpy as np

from .atomic_data import covalent_radii, ANGSTROM_TO_BOHR


DEFAULT_BOND_TOLERANCE = 1.15

# Closer atoms are taken as duplicates of each other, not as bonded
MIN_BOND_LENGTH = 0.1


def findBonds(lattice, positions, atomicNumbers, tolerance=DEFAULT_BOND_TOLERANCE):
    """
    Bonds of the unit cell, including those to atoms of neighbouring cells.

    `lattice` holds the lattice vectors as rows and `positions` the Cartesian
    atomic positions, both in Bohr. Returns `(i, j, shifts)`: atom i of a cell is
    bonded to atom j of the cell displaced by `shifts` (integer lattice
    coordinates). Each bond is listed once per direction, i -> j and j -> i,
    so every atom finds all its bonds among the entries with its index as i.
    """
    lattice = np.asarray(lattice, dtype=float)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    numbers = np.asarray(atomicNumbers, dtype=int)[:len(positions)]
    empty = (np.empty(0, dtype=int), np.empty(0, dtype=int), np.empty((0, 3), dtype=int))
    if len(positions) == 0:
        return empty

    radii = covalent_radii[numbers] * ANGSTROM_TO_BOHR
    maxBond = tolerance * 2.0 * radii.max()

    # Search with the atoms wrapped into the cell, then convert the shifts back
    # to the given positions, which yambopy may leave outside the cell
    fractional = np.linalg.solve(lattice.T, positions.T).T
    cellIndex = np.floor(fractional + 1e-9)
    wrapped = (fractional - cellIndex) @ lattice

    # Neighbouring cells within reach: wrapped atoms are less than one cell
    # apart, plus as many cells as the longest bond spans across each family
    # of lattice planes (spacing 1 / |b_k|, with b_k the reciprocal vectors
    # without the 2 pi factor)
    reciprocal = np.linalg.inv(lattice).T
    reach = np.ceil(maxBond * np.linalg.norm(reciprocal, axis=1)).astype(int) + 1
    shifts = np.stack(np.meshgrid(*(np.arange(-n, n + 1) for n in reach), indexing='ij'), axis=-1).reshape(-1, 3)

    # Distances from every atom i to every image of every atom j: (i, j, shift)
    images = wrapped[None, :, :] + (shifts @ lattice)[:, None, :]       # (shift, j, 3)
    vectors = images[None, :, :, :] - wrapped[:, None, None, :]         # (i, shift, j, 3)
    distances = np.linalg.norm(vectors, axis=-1)
    limits = tolerance * (radii[:, None] + radii[None, :])               # (i, j)

    bonded = (distances <= limits[:, None, :]) & (distances > MIN_BOND_LENGTH)
    i, s, j = np.nonzero(bonded)
    if len(i) == 0:
        return empty

    bondShifts = shifts[s] + (cellIndex[i] - cellIndex[j]).astype(int)
    return i, j, bondShifts


def halfBonds(lattice, positions, bonds, supercell):
    """
    Half-bond segments of a supercell of `supercell` cells (cell offsets 0 to
    n - 1 along each lattice vector, as the atoms are drawn).

    Each atom of the supercell gets the half of each of its bonds that is on
    its side: from its center to the bond midpoint. A bond between two atoms
    of the supercell is thus drawn whole, in two halves, while a bond to an
    atom outside it is drawn up to the midpoint only, which shows the
    coordination of the atoms at the boundary without adding atoms.

    Returns `(starts, ends, atomIndices)`: segment end points (Bohr) and the
    index, in the unit cell, of the atom each half belongs to.
    """
    lattice = np.asarray(lattice, dtype=float)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    i, j, shifts = bonds
    if len(i) == 0:
        return np.empty((0, 3)), np.empty((0, 3)), np.empty(0, dtype=int)

    # Half-bond vector from atom i to the midpoint, the same in every cell
    halfVectors = 0.5 * (positions[j] + shifts @ lattice - positions[i])

    cells = np.stack(np.meshgrid(*(np.arange(n) for n in supercell), indexing='ij'), axis=-1).reshape(-1, 3)
    offsets = cells @ lattice                                            # (cell, 3)

    starts = (offsets[:, None, :] + positions[i][None, :, :]).reshape(-1, 3)
    ends = starts + np.tile(halfVectors, (len(cells), 1))
    atomIndices = np.tile(i, len(cells))
    return starts, ends, atomIndices
