"""Tests of yambopy_ext.bz.wigner_seitz (no Qt, no data: meant to move to YamboPy with the module)."""

import numpy as np
import pytest

from visual_excitons.yambopy_ext.bz.wigner_seitz import (wigner_seitz_cell, wigner_seitz_polygon, plane_section,
                                                         inside_cell, fill_wigner_seitz)


def reciprocal(lat):
    return np.linalg.inv(np.asarray(lat, dtype=float)).T


def volume(cell):
    """Volume of a convex cell from its faces (divergence theorem)."""
    total = 0.0
    for face in cell['faces']:
        p = cell['vertices'][face]
        for i in range(1, len(p) - 1):
            total += np.dot(p[0], np.cross(p[i], p[i + 1])) / 6
    return abs(total)


HEX = [[1, 0, 0], [-0.5, np.sqrt(3) / 2, 0], [0, 0, 1.6]]


@pytest.mark.parametrize('lat, faces, vertices, edges', [
    (np.eye(3), 6, 8, 12),                                                     # cube
    (HEX, 8, 12, 18),                                                          # hexagonal prism
    (0.5 * np.array([[-1, 0, 1], [0, 1, 1], [-1, 1, 0]]), 14, 24, 36),         # FCC: truncated octahedron
    (0.5 * np.array([[1, 1, 1], [-1, 1, 1], [-1, -1, 1]]), 12, 14, 24),        # BCC: rhombic dodecahedron
    ([[1, 0, 0], [0.3, 1.1, 0], [0.2, 0.1, 1.4]], 14, 24, 36),                 # triclinic
])
def test_cell_of_known_zones(lat, faces, vertices, edges):
    rlat = reciprocal(lat)
    cell = wigner_seitz_cell(rlat)
    assert (len(cell['faces']), len(cell['vertices']), len(cell['edges'])) == (faces, vertices, edges)
    # It is a primitive cell of the lattice
    assert volume(cell) == pytest.approx(abs(np.linalg.det(rlat)))
    # Every vertex is as far from the origin as from the lattice vector of its faces
    for face, g in zip(cell['faces'], cell['face_vectors']):
        for v in cell['vertices'][face]:
            assert np.linalg.norm(v) == pytest.approx(np.linalg.norm(v - g))


def test_hexagon():
    polygon = wigner_seitz_polygon(reciprocal(HEX)[:2, :2])
    assert len(polygon) == 6
    radii = np.linalg.norm(polygon, axis=1)
    assert np.allclose(radii, radii[0])                         # regular: the K points
    angles = np.arctan2(polygon[:, 1], polygon[:, 0])
    assert np.all(np.diff(angles) > 0)                          # counterclockwise


def test_section():
    cell = wigner_seitz_cell(reciprocal(np.eye(3)))
    square = plane_section(cell, [0, 0, 0], [0, 0, 1])
    assert len(square) == 4 and np.allclose(np.abs(square[:, :2]), 0.5)
    assert len(plane_section(cell, [0, 0, 2.0], [0, 0, 1])) == 0           # misses the cell
    # Through the hexagonal prism, perpendicular to c: the hexagon
    hexagon = plane_section(wigner_seitz_cell(reciprocal(HEX)), [0, 0, 0.1], [0, 0, 1])
    assert len(hexagon) == 6


def test_inside_and_fill():
    rlat = reciprocal(HEX)
    cell = wigner_seitz_cell(rlat)
    assert inside_cell([[0, 0, 0]], cell)[0] and not inside_cell([rlat[0]], cell)[0]
    red = np.array([[i / 6, j / 6, 0] for i in range(6) for j in range(6)])
    kpoints, indices = fill_wigner_seitz(red, rlat, cell)
    assert set(indices) == set(range(36))                      # every point of the grid is there
    assert np.all(inside_cell(kpoints, cell))
    # The corners (K) are shared by three zones, the middles of the edges (M) by two
    counts = np.bincount(indices, minlength=36)
    assert sorted(set(counts)) == [1, 2, 3]
