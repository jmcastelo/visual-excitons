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


def planeMap(red_kpoints, values, lat, rlat, grid, axis, plane=None, replicas=0):
    """
    A map of `values` (one per k-point) on a plane perpendicular to lattice
    vector `axis`: the plane k_axis = plane/N, or, if `plane` is None, the
    sum over the planes (for a layer, with one plane, the same).

    Returns a dict with 'points' (m, 2) and 'values' (m,) of the tiles'
    centres, 'tile' (t, 2) (the shape of each tile, around its centre),
    'outline' (o, 2) (the zone, or its section) and 'red' (m, 3) (the reduced
    coordinates of each point), lengths in Å⁻¹, in the plane basis (e1, e2),
    for the zone; and 'zones': the zone and `replicas` rings of its periodic
    replicas around it (the zone first, then the nearest), each a dict with
    the same keys and its 'shift' (2,), the zones of the plane tiling it.
    """
    lat, rlat = np.asarray(lat, dtype=float), np.asarray(rlat, dtype=float)
    red = np.asarray(red_kpoints, dtype=float)
    values = np.asarray(values, dtype=float)
    grid = [int(n) for n in grid]
    normal, e1, e2 = planeBasis(lat, axis)
    others = [i for i in range(3) if i != axis]

    def project(points):
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        return np.column_stack([points @ e1, points @ e2]) * TO_INVERSE_ANGSTROM

    # The tile of each point: the 2D Voronoi cell of the grid in the plane
    tile = wigner_seitz_polygon(project([rlat[i] / grid[i] for i in others]))

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
        central = {'points': project(kpoints), 'values': summed[indices], 'red': red2[indices],
                   'outline': project(plane_section(cell, np.zeros(3), normal))}
        # The replicas tile the plane: copies shifted by the in-plane reciprocal vectors
        zones = [dict(central, points=central['points'] + shift, outline=central['outline'] + shift, shift=shift)
                 for shift in zoneShifts(project([rlat[i] for i in others]), replicas)]
    else:
        cell = wigner_seitz_cell(rlat)
        # Points up to a tile outside the zone too: their tiles fill the edges of the section
        # (drawn clipped to it)
        step = max(np.linalg.norm(rlat[i] / grid[i]) for i in range(3))
        margin = 1.5 * step / np.min(np.linalg.norm(cell['face_vectors'], axis=1))
        kpoints, indices = fill_wigner_seitz(red, rlat, cell, tol=margin)
        copies = kpoints @ np.linalg.inv(rlat)

        def section(level):
            """The points of the zone on the plane k_axis = level (reduced), and its outline there."""
            on = np.isclose(copies[:, axis], level, atol=1e-6)
            point = level * lat[axis] / (lat[axis] @ lat[axis])
            return {'points': project(kpoints[on]), 'values': values[indices[on]], 'red': copies[on],
                    'outline': project(plane_section(cell, point, normal))}
        level = plane / grid[axis]
        central = section(level)
        # The replicas: the zones displaced by G = i b1 + j b2 + l b3 (in the reduced basis of
        # the other axes and `axis`) that this plane crosses. Their points are those of the
        # central zone on the plane k_axis = level - l, displaced by G; with l != 0 they fill
        # the gaps that in-plane copies of the central section would leave.
        zones = [dict(central, shift=np.zeros(2))]
        if replicas > 0:
            inPlane = project([rlat[i] for i in others])
            radius = replicas * np.sqrt(2) * np.min(np.linalg.norm(inPlane, axis=1)) * (1 + 1e-6)
            span = 4 * replicas + 2
            sections = {}
            for i in range(-span, span + 1):
                for j in range(-span, span + 1):
                    for l in range(-2, 3):
                        if i == j == l == 0:
                            continue
                        g = np.zeros(3)
                        g[others[0]], g[others[1]], g[axis] = i, j, l
                        g = g @ rlat
                        shift = project(g)[0]
                        if np.linalg.norm(shift) > radius:
                            continue
                        if l not in sections:
                            sections[l] = section(level - l)
                        zone = sections[l]
                        if len(zone['outline']) < 3:
                            continue                        # the plane misses this zone
                        zones.append(dict(zone, points=zone['points'] + shift, outline=zone['outline'] + shift,
                                          shift=shift))
            # Nearest first (as zoneShifts)
            zones[1:] = sorted(zones[1:], key=lambda z: (round(float(np.linalg.norm(z['shift'])), 9),
                                                         float(np.arctan2(z['shift'][1], z['shift'][0]))))
    return dict(central, tile=tile, zones=zones)


def zoneShifts(vectors, rings):
    """
    The displacements of the zone and of `rings` rings of its periodic replicas,
    combinations of the two in-plane reciprocal vectors `vectors` (2D), the zone
    itself first. Ring n: the zones whose centres are within n·√2 of the
    shortest vector, so that the first ring is the 6 neighbours of a hexagonal
    zone and the 8 of a square one.
    """
    vectors = np.asarray(vectors, dtype=float)
    if rings <= 0:
        return np.zeros((1, 2))
    radius = rings * np.sqrt(2) * np.min(np.linalg.norm(vectors, axis=1)) * (1 + 1e-6)
    span = 4 * rings + 2
    combos = np.array([(i, j) for i in range(-span, span + 1) for j in range(-span, span + 1)], dtype=float)
    shifts = combos @ vectors
    shifts = shifts[np.linalg.norm(shifts, axis=1) <= radius]
    order = np.lexsort((np.arctan2(shifts[:, 1], shifts[:, 0]), np.round(np.linalg.norm(shifts, axis=1), 9)))
    return shifts[order]


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
