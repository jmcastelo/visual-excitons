"""
Which part of the periodic crystal the 3D view shows: a shift of the origin
of the cell (fractions of the lattice vectors), applied to the atoms, the
cells, the wave function, the fixed particle and the analysis alike.

Monolayers are computed in cells with a wide vacuum along one axis, and the
layer often sits on a face of the cell (e.g. WSe2: W at c = 0, Se at c = ±0.07),
so the layer and its exciton are drawn in two halves, at the bottom and the top.
`detectLayer` finds the vacuum and the shift that puts it on the faces, the
layer in the middle.

The wave function is shifted by whole grid points (np.roll), the atoms by the
same amount, wrapped into the cell. Wrapping the wave function is exact along
axes where its box spans whole periods of the k-point grid (its Born-von
Karman period), such as the vacuum axis of a monolayer (one cell, one k-point);
along others, it is only right where the density has decayed at the faces
(`seamAxes` tells where it has not).
"""

import numpy as np

# A vacuum: a gap between the atoms of at least this much of the cell, and this
# thick; thinner (but not less than the second) along an axis with a single
# k-point, the sign of a 2D calculation (e.g. BN with 6.3 Å of vacuum)
LAYER_GAP_FRACTION = 0.4
LAYER_GAP_BOHR = 10.0 / 0.529177210903       # 10 Å
LAYER_GAP_2D_BOHR = 5.0 / 0.529177210903     # 5 Å

# Density at the faces (relative to the maximum) beyond which wrapping shows a seam
SEAM_THRESHOLD = 0.02

AXES = 'abc'


def kGrid(lattice):
    """The full k-point grid (n1, n2, n3) of a YamboLatticeDB, from its expanded k-points; None if unknown."""
    if getattr(lattice, 'red_kpoints', None) is None:
        return None
    reduced = np.asarray(lattice.red_kpoints, dtype=float) % 1.0
    grid = []
    for axis in range(3):
        values = np.unique(np.round(reduced[:, axis], 6) % 1.0)
        if len(values) < 2:
            grid.append(1)
            continue
        steps = np.diff(np.concatenate([values, [values[0] + 1.0]]))
        grid.append(int(round(1.0 / steps[steps > 1e-4].min())))
    return grid


def reducedPositions(cell, positions):
    """Cartesian positions (rows) in fractions of the lattice vectors (rows of `cell`)."""
    return np.linalg.solve(np.asarray(cell, dtype=float).T, np.asarray(positions, dtype=float).T).T


def detectLayer(cell, positions, grid=None):
    """
    The vacuum of a layered cell: (axis, shift) where shift (a fraction of
    that lattice vector) puts the middle of the vacuum on the faces of the
    cell, so the layer is in the middle; None if there is no such vacuum.
    `grid`, the k-point grid, if known, lowers the thickness needed along an
    axis with a single k-point.
    """
    cell = np.asarray(cell, dtype=float)
    fractions = reducedPositions(cell, positions) % 1.0
    reciprocal = np.linalg.inv(cell).T                        # rows: reciprocal vectors (no 2π)
    best = None
    for axis in range(3):
        values = np.sort(fractions[:, axis])
        gaps = np.diff(np.concatenate([values, [values[0] + 1.0]]))
        k = int(np.argmax(gaps))
        gap = gaps[k]
        thickness = gap / np.linalg.norm(reciprocal[axis])    # perpendicular to the layer
        needed = LAYER_GAP_2D_BOHR if grid is not None and int(grid[axis]) == 1 else LAYER_GAP_BOHR
        if gap >= LAYER_GAP_FRACTION and thickness >= needed and (best is None or thickness > best[2]):
            middle = (values[k] + gap / 2) % 1.0
            best = (axis, wrapShift(-middle), thickness)
    return None if best is None else (best[0], best[1])


def wrapShift(value):
    """A shift in (-0.5, 0.5]."""
    value = float(value) % 1.0
    return value - 1.0 if value > 0.5 else value


def snapShift(shift, gridPerCell):
    """The shift rounded to whole grid points of the wave function (`gridPerCell` along each axis)."""
    return [round(s * g) / g for s, g in zip(shift, gridPerCell)]


def rollDensity(density, shift, gridPerCell):
    """The density shifted by `shift` (fractions of a cell), by whole grid points, wrapped in its box."""
    steps = [int(round(s * g)) for s, g in zip(shift, gridPerCell)]
    return np.roll(density, steps, axis=(0, 1, 2)) if any(steps) else density


def shiftAtoms(cell, positions, shift):
    """Atomic positions (Cartesian, of one cell) shifted by `shift`, wrapped back into the cell."""
    cell = np.asarray(cell, dtype=float)
    fractions = (reducedPositions(cell, positions) + np.asarray(shift, dtype=float)) % 1.0
    fractions[np.isclose(fractions, 1.0, atol=1e-9)] = 0.0
    return fractions @ cell


def shiftCrystal(crystal, shift, supercell):
    """A position in crystal coordinates of the supercell, shifted and wrapped in it."""
    return (np.asarray(crystal, dtype=float) + np.asarray(shift, dtype=float)) % np.asarray(supercell, dtype=float)


def periodicAxes(supercell, grid):
    """Axes along which the wave function's box spans whole periods of the k-point grid (none if unknown)."""
    if grid is None:
        return [False, False, False]
    return [int(n) % int(g) == 0 for n, g in zip(supercell, grid)]


def seamAxes(density, shift, supercell, grid):
    """Axes shifted where wrapping is not exact and the density at the faces is significant."""
    density = np.asarray(density)
    top = float(density.max()) or 1.0
    seams = []
    for axis, periodic in enumerate(periodicAxes(supercell, grid)):
        if periodic or abs(shift[axis]) < 1e-9:
            continue
        faces = max(float(np.take(density, 0, axis=axis).max()), float(np.take(density, -1, axis=axis).max()))
        if faces / top > SEAM_THRESHOLD:
            seams.append(axis)
    return seams
