"""
What the Composition panel draws of an exciton in reciprocal space, from the
weights of yambopy_ext.bse.exciton_kspace: maps on planes of the k-point grid
(each k-point drawn as its own tile, the Voronoi cell of the grid in the
plane), the points of the Brillouin zone in 3D, and the special point near a
k-point. Lengths in Å⁻¹ (with 2π) for display; the lattices as YamboPy gives
them (lat in Bohr, rlat in Bohr⁻¹ without 2π).
"""

import itertools

import numpy as np

from .atomic_data import BOHR_TO_ANGSTROM
from visual_excitons.yambopy_ext.bz.wigner_seitz import (wigner_seitz_cell, wigner_seitz_polygon, plane_section,
                                                         fill_wigner_seitz)

# Bohr⁻¹ without 2π to Å⁻¹ with 2π
TO_INVERSE_ANGSTROM = 2 * np.pi / BOHR_TO_ANGSTROM


def planeBasis(lat, axis):
    """
    Orthonormal (normal, e1, e2) of the planes of k-points perpendicular to
    lattice vector `axis` (they hold the other two reciprocal vectors): e1
    along Cartesian x if it is not along the normal, else y.
    """
    normal = np.asarray(lat, dtype=float)[axis]
    normal = normal / np.linalg.norm(normal)
    reference = np.eye(3)[0] if abs(normal[0]) < 0.9 else np.eye(3)[1]
    e1 = reference - (reference @ normal) * normal
    e1 /= np.linalg.norm(e1)
    return normal, e1, np.cross(normal, e1)


def planeIndices(grid, axis):
    """The planes of the grid along `axis` through the zone: n of k_axis = n/N, from -(N-1)//2 to N//2."""
    n = int(grid[axis])
    return list(range(-((n - 1) // 2), n // 2 + 1))


def planeMap(red_kpoints, values, lat, rlat, grid, axis, plane=None):
    """
    A map of `values` (one per k-point) on a plane perpendicular to lattice
    vector `axis`: the plane k_axis = plane/N, or, if `plane` is None, the
    sum over the planes (for a layer, with one plane, the same).

    Returns a dict with 'points' (m, 2) and 'values' (m,) of the tiles'
    centres, 'tile' (t, 2) (the shape of each tile, around its centre),
    'outline' (o, 2) (the zone, or its section) and 'red' (m, 3) (the reduced
    coordinates of each point), lengths in Å⁻¹, in the plane basis (e1, e2).
    """
    lat, rlat = np.asarray(lat, dtype=float), np.asarray(rlat, dtype=float)
    red = np.asarray(red_kpoints, dtype=float)
    values = np.asarray(values, dtype=float)
    grid = [int(n) for n in grid]
    normal, e1, e2 = planeBasis(lat, axis)
    others = [i for i in range(3) if i != axis]

    if plane is None or grid[axis] == 1:
        # The planes summed: a 2D grid of the other two reciprocal vectors (in the plane),
        # whose zone is a prism with the 2D zone as its section
        keys = np.round(red[:, others] % 1.0 * np.array(grid)[others]).astype(int) % np.array(grid)[others]
        unique, inverse = np.unique(keys, axis=0, return_inverse=True)
        summed = np.bincount(inverse.ravel(), weights=values)
        red2 = np.zeros((len(unique), 3))
        red2[:, others] = unique / np.array(grid)[others]
        prism = rlat.copy()
        prism[axis] = normal * 10 * np.max(np.linalg.norm(rlat, axis=1))
        cell = wigner_seitz_cell(prism)
        kpoints, indices = fill_wigner_seitz(red2, prism, cell)
        outline = plane_section(cell, np.zeros(3), normal)
        pointValues = summed[indices]
        pointRed = red2[indices]
    else:
        cell = wigner_seitz_cell(rlat)
        # Points up to a tile outside the zone too: their tiles fill the edges of the section
        # (drawn clipped to it)
        step = max(np.linalg.norm(rlat[i] / grid[i]) for i in range(3))
        margin = 1.5 * step / np.min(np.linalg.norm(cell['face_vectors'], axis=1))
        kpoints, indices = fill_wigner_seitz(red, rlat, cell, tol=margin)
        copies = kpoints @ np.linalg.inv(rlat)
        on = np.isclose(copies[:, axis], plane / grid[axis], atol=1e-6)
        kpoints, indices = kpoints[on], indices[on]
        point = plane / grid[axis] * lat[axis] / (lat[axis] @ lat[axis])
        outline = plane_section(cell, point, normal)
        pointValues = values[indices]
        pointRed = copies[on]

    def project(points):
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        return np.column_stack([points @ e1, points @ e2]) * TO_INVERSE_ANGSTROM

    # The tile of each point: the 2D Voronoi cell of the grid in the plane
    steps = project([rlat[i] / grid[i] for i in others])
    return {'points': project(kpoints), 'values': pointValues, 'red': pointRed,
            'tile': wigner_seitz_polygon(steps), 'outline': project(outline)}


def zonePoints(red_kpoints, values, rlat):
    """The k-points in the Brillouin zone (copies on its boundary included) in Å⁻¹, their values, and the zone."""
    rlat = np.asarray(rlat, dtype=float)
    cell = wigner_seitz_cell(rlat)
    kpoints, indices = fill_wigner_seitz(red_kpoints, rlat, cell)
    zone = dict(cell, vertices=cell['vertices'] * TO_INVERSE_ANGSTROM)
    return kpoints * TO_INVERSE_ANGSTROM, np.asarray(values, dtype=float)[indices], zone


def nearestSpecialPoint(red_kpoint, special_points, rlat, tolerance=0.08):
    """
    The label of the special point equivalent to, or near, `red_kpoint`
    (within `tolerance` of the shortest reciprocal vector), or ''. A point
    near -s, when -s is not equivalent to s, gets the label of s with a prime
    (K' of the hexagonal zone, whose list has K only; in YamboPy's label
    grammar, shown K′ by options.tickLabels).
    """
    rlat = np.asarray(rlat, dtype=float)
    limit = tolerance * np.min(np.linalg.norm(rlat, axis=1))
    shifts = np.array(list(itertools.product((-1, 0, 1), repeat=3)), dtype=float)
    k = np.asarray(red_kpoint, dtype=float)

    def distance(a, b):
        return float(np.min(np.linalg.norm((a - b + shifts) @ rlat, axis=1)))
    best, label = None, ''
    for name, point in special_points.items():
        point = np.asarray(point, dtype=float)
        candidates = [(distance(k, point), name)]
        if distance(point, -point) > limit and not name.endswith(("'", '′')):
            candidates.append((distance(k, -point), name + "'"))
        for d, text in candidates:
            if d <= limit and (best is None or d < best - 1e-12):
                best, label = d, text
    return label


def compositionCSV(composition, lattice, datasetName=''):
    """
    The composition of an exciton (see Calculations.computeComposition) as CSV
    text: a header with what it is, then the weight of the electron (at k)
    and of the hole (at k-Q) at every k-point, then the band pairs and bands.
    """
    c = composition
    red = np.asarray(lattice.red_kpoints, dtype=float)
    car = red @ np.asarray(lattice.rlat, dtype=float) * TO_INVERSE_ANGSTROM
    q = ' '.join(f'{x:.6f}' for x in c['red_qpoint'])
    lines = [f'# Visual Excitons: composition of exciton {c["excIndex"]} at Q{c["qIndex"] + 1} ({q}, reduced)'
             + (f' of {datasetName}' if datasetName else ''),
             f'# Energy {c["energy"]:.6f} eV; states summed: {" ".join(map(str, c["states"]))}',
             '# The electron at k, the hole at k-Q; weights add up to 1',
             'k1,k2,k3,kx (1/A),ky (1/A),kz (1/A),electron,hole']
    for r, k, e, h in zip(red, car, c['electron'], c['hole']):
        lines.append(','.join(f'{x:.6f}' for x in (*r, *k)) + f',{e:.8f},{h:.8f}')
    lines += ['', 'valence band,conduction band,weight']
    lines += [f'{v},{cb},{w:.8f}' for v, cb, w in c['pairs']]
    lines += ['', 'band,of,weight']
    lines += [f'{b},hole (valence),{w:.8f}' for b, w in sorted(c['valence'].items())]
    lines += [f'{b},electron (conduction),{w:.8f}' for b, w in sorted(c['conduction'].items())]
    return '\n'.join(lines) + '\n'
