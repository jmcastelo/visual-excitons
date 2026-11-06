from collections import Counter

import numpy as np
import pytest

from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR, BOHR_TO_ANGSTROM, chemical_symbols
from visual_excitons.core.bonds import findBonds, halfBonds

SI_A = 5.431 * ANGSTROM_TO_BOHR  # silicon lattice constant
SI_BOND = np.sqrt(3) / 4 * 5.431  # nearest-neighbour distance, angstrom


def silicon(shift=(0, 0, 0)):
    """Diamond silicon, primitive fcc cell; `shift` moves the second atom by lattice vectors."""
    lattice = 0.5 * SI_A * np.array([[0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=float)
    positions = np.array([[0, 0, 0], [0.25, 0.25, 0.25]]) * SI_A
    positions[1] += np.asarray(shift) @ lattice
    return lattice, positions, [14, 14]


def bondLengths(lattice, positions, bonds):
    i, j, shifts = bonds
    return np.linalg.norm(positions[j] + shifts @ lattice - positions[i], axis=1) * BOHR_TO_ANGSTROM


@pytest.mark.parametrize('shift', [(0, 0, 0), (2, 0, -1), (-3, 1, 1)])
def test_silicon_is_tetrahedral(shift):
    """Four bonds of 2.352 A per atom, wherever yambopy leaves the atoms."""
    lattice, positions, numbers = silicon(shift)
    bonds = findBonds(lattice, positions, numbers)
    assert Counter(bonds[0].tolist()) == {0: 4, 1: 4}
    np.testing.assert_allclose(bondLengths(lattice, positions, bonds), SI_BOND, atol=1e-4)


def test_bonds_are_listed_in_both_directions():
    lattice, positions, numbers = silicon()
    i, j, shifts = findBonds(lattice, positions, numbers)
    directed = {(a, b, tuple(s)) for a, b, s in zip(i.tolist(), j.tolist(), shifts.tolist())}
    assert all((b, a, tuple(-np.array(s))) in directed for a, b, s in directed)


def test_tolerance_controls_bonding():
    lattice, positions, numbers = silicon()
    # Si covalent radius 1.11 A: 2 * 1.11 * 1.05 = 2.33 A < 2.352 A
    assert len(findBonds(lattice, positions, numbers, tolerance=1.05)[0]) == 0
    assert len(findBonds(lattice, positions, numbers, tolerance=1.10)[0]) == 8


def test_no_atoms():
    i, j, shifts = findBonds(np.eye(3) * 10, np.empty((0, 3)), [])
    assert len(i) == len(j) == len(shifts) == 0


def test_bonds_reach_beyond_neighbouring_cells():
    """
    A thin, skewed cell with one carbon atom: a chain along x with 0.8 A
    spacing. The bond cutoff, 1.15 * 2 * 0.76 A = 1.748 A, reaches the images
    two cells away, which a search of the neighbouring cells only would miss.
    """
    a = 0.8 * ANGSTROM_TO_BOHR
    lattice = np.array([[a, 0, 0], [12 * a, 25 * a, 0], [0, 0, 25 * a]])
    positions = np.zeros((1, 3))
    i, j, shifts = findBonds(lattice, positions, [6])
    assert sorted(shifts[:, 0].tolist()) == [-2, -1, 1, 2]
    assert not shifts[:, 1:].any()
    np.testing.assert_allclose(sorted(bondLengths(lattice, positions, (i, j, shifts))), [0.8, 0.8, 1.6, 1.6], atol=1e-9)


def test_half_bonds_pair_inside_the_supercell():
    """Whole bonds inside the supercell are two halves meeting at the midpoint; boundary ones are single halves."""
    lattice, positions, numbers = silicon()
    bonds = findBonds(lattice, positions, numbers)
    starts, ends, atoms = halfBonds(lattice, positions, bonds, [3, 3, 3])
    assert len(starts) == 27 * 8

    # Count of whole bonds in the 54-atom block, computed directly
    cells = np.array([n @ lattice for n in np.ndindex(3, 3, 3)])
    distances = np.linalg.norm(cells[:, None] - (cells + positions[1])[None], axis=-1) * BOHR_TO_ANGSTROM
    wholeBonds = int((np.abs(distances - SI_BOND) < 1e-3).sum())

    midpoints = Counter(map(tuple, np.round(ends, 5)))
    assert sum(count == 2 for count in midpoints.values()) == wholeBonds == 81
    assert sum(count == 1 for count in midpoints.values()) == 216 - 2 * 81
    # Each half has half the bond length and belongs to its starting atom
    np.testing.assert_allclose(np.linalg.norm(ends - starts, axis=1) * BOHR_TO_ANGSTROM, SI_BOND / 2, atol=1e-4)
    # Halves start at their own atom, in every cell
    np.testing.assert_allclose(np.unique(np.round(starts[atoms == 1], 6), axis=0),
                               np.unique(np.round(cells + positions[1], 6), axis=0))


def test_half_bonds_without_bonds():
    starts, ends, atoms = halfBonds(np.eye(3), np.zeros((1, 3)), (np.empty(0, int), np.empty(0, int), np.empty((0, 3), int)), [1, 1, 1])
    assert starts.shape == ends.shape == (0, 3) and len(atoms) == 0


@pytest.mark.data
@pytest.mark.parametrize('name, expected', [
    # Octahedral Bi, each I bonded to two Bi
    ('BiI3_Bulk_8x8x8', {'Bi': 6, 'I': 2}),
    ('BN', {'B': 3, 'N': 3}),
])
def test_coordination_of_real_crystals(lattice, name, expected):
    lat = lattice(name)
    numbers = np.asarray(lat.atomic_numbers)
    positions = np.asarray(lat.car_atomic_positions)[:len(numbers)]
    i, j, shifts = findBonds(lat.lat, positions, numbers)
    for z in set(numbers.tolist()):
        symbol = chemical_symbols[z]
        atomsOfSpecies = np.flatnonzero(numbers == z)
        coordination = Counter(i.tolist())
        assert all(coordination[a] == expected[symbol] for a in atomsOfSpecies), symbol
