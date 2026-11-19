"""Placing the fixed particle: the distinct maxima of a particle density, and their directions (no Qt)."""

import numpy as np
import pytest

from visual_excitons.core.atomic_data import chemical_symbols
from visual_excitons.core.placement import (distinctMaxima, directionText, groupOf, nearestMember, gridIndex,
                                            densityShare)

ANGSTROM = 1 / 0.529177210903       # Bohr


def peaks(shape, points):
    """A density with peaks (value) at grid points, and the maxima as density_maxima lists them."""
    density = np.full(shape, 1e-3)
    for index, value in points:
        density[index] = value
    order = sorted(points, key=lambda p: -p[1])
    return density, [list(i) for i, _ in order]


def test_equivalent_maxima_count_once():
    # Simple cubic, one atom at the origin: its bonds along +-x, +-y, +-z
    cell = np.eye(3) * 4 * ANGSTROM
    shape = (20, 20, 20)
    axes = [((1, 0, 0), 1.0), ((19, 0, 0), 1.0), ((0, 1, 0), 1.0), ((0, 19, 0), 1.0), ((0, 0, 1), 1.0),
            ((0, 0, 19), 1.0)]                           # 0.2 Å from the atom, along its bonds
    diagonal = [((2, 2, 2), 0.5), ((18, 18, 18), 0.5)]    # weaker, along the body diagonal
    density, maxima = peaks(shape, axes + diagonal)
    groups = distinctMaxima(density, maxima, cell, [[0.0, 0.0, 0.0]], [53])
    assert [len(g['members']) for g in groups] == [6, 2]
    first, second = groups
    assert first['share'] == pytest.approx(1.0) and first['element'] == 53
    assert first['distance'] == pytest.approx(0.2) and first['bondAngle'] == pytest.approx(0.0, abs=1e-6)
    assert directionText(first, chemical_symbols) == '0° from the I–I bond'
    assert second['bondAngle'] == pytest.approx(np.degrees(np.arccos(1 / np.sqrt(3))))
    assert groupOf(groups, (18, 18, 18)) == 1 and groupOf(groups, (5, 5, 5)) is None
    # The copy nearest a position: across the faces of the cell too
    assert nearestMember(first, [0.0, 0.0, 0.97], shape, cell) == (0, 0, 19)


def test_directions_in_a_layer():
    # A layer in the a-b plane (vacuum along c): maxima above and below the atom, and beside it
    cell = np.diag([3.0, 3.0, 20.0]) * ANGSTROM
    shape = (30, 30, 200)
    density, maxima = peaks(shape, [((0, 0, 5), 1.0), ((0, 0, 195), 1.0), ((5, 0, 0), 0.4)])
    groups = distinctMaxima(density, maxima, cell, [[0.0, 0.0, 0.0]], [74], layerAxis=2)
    assert [len(g['members']) for g in groups] == [2, 1]
    assert groups[0]['elevation'] == pytest.approx(90.0) and 'out of the plane' in directionText(groups[0], chemical_symbols)
    assert groups[1]['elevation'] == pytest.approx(0.0) and 'in the plane' in directionText(groups[1], chemical_symbols)


def test_unequal_values_are_not_merged():
    cell = np.eye(3) * 4 * ANGSTROM
    density, maxima = peaks((20, 20, 20), [((1, 0, 0), 1.0), ((19, 0, 0), 0.9)])
    groups = distinctMaxima(density, maxima, cell, [[0.0, 0.0, 0.0]], [53])
    assert [len(g['members']) for g in groups] == [1, 1]


def test_share_at_a_position():
    density, _ = peaks((10, 10, 10), [((3, 4, 5), 2.0), ((0, 0, 0), 1.0)])
    assert gridIndex([0.31, 0.39, 0.52], density.shape) == (3, 4, 5)
    assert densityShare(density, [0.31, 0.39, 0.52]) == 1.0 and densityShare(density, [1.0, 0.0, -0.01]) == 0.5
