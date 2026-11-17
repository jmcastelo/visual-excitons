"""
wigner_seitz.py
===============
The first Brillouin zone as a geometric object, for any lattice: the
Wigner-Seitz cell of the reciprocal lattice, its sections by planes, and
the points of a k-point grid that fill it.

* :func:`wigner_seitz_cell` — vertices, edges and faces of the cell (3D),
  from the Voronoi construction (scipy), so that every Bravais lattice is
  supported, oblique and centred ones included;
* :func:`wigner_seitz_polygon` — the 2D zone of an in-plane lattice (e.g. a
  layer), as an ordered polygon;
* :func:`plane_section` — the polygon where a plane cuts a convex cell;
* :func:`fill_wigner_seitz` — the copies of the points of a grid (e.g.
  ``YamboLatticeDB.red_kpoints``) inside the cell, with the index of the
  point each copy comes from.

Meant for ``yambopy.bz``: it replaces, in a general way, the hexagonal and
rectangular zones of ``yambopy.plot.plotting.BZ_Wigner_Seitz`` (which has
no oblique or 3D zones). Lengths in any unit, as the vectors given (for
YamboPy, ``lattice.rlat``: Bohr⁻¹ without 2π).
"""

import itertools

import numpy as np
from scipy.spatial import Voronoi

__all__ = ['wigner_seitz_cell', 'wigner_seitz_polygon', 'plane_section', 'inside_cell', 'fill_wigner_seitz']


def _lattice_points(vectors, n=2):
    """Points of the lattice spanned by the rows of *vectors*, with indices from -n to n; the origin first."""
    vectors = np.asarray(vectors, dtype=float)
    dim = len(vectors)
    indices = [i for i in itertools.product(range(-n, n + 1), repeat=dim) if any(i)]
    return np.vstack([np.zeros(dim), np.array(indices, dtype=float) @ vectors])


def _merge_vertices(vertices, tol):
    """Unique vertices (within *tol*) and, for each vertex given, the index of its unique copy."""
    unique, mapping = [], []
    for vertex in vertices:
        for i, other in enumerate(unique):
            if np.linalg.norm(vertex - other) < tol:
                mapping.append(i)
                break
        else:
            unique.append(vertex)
            mapping.append(len(unique) - 1)
    return np.array(unique), mapping


def _order_around(points, centre, normal):
    """Indices that order *points* (on a plane through *centre* with *normal*) counterclockwise around it."""
    normal = normal / np.linalg.norm(normal)
    e1 = points[0] - centre
    e1 = e1 - (e1 @ normal) * normal
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(normal, e1)
    relative = points - centre
    return np.argsort(np.arctan2(relative @ e2, relative @ e1))


def wigner_seitz_cell(rlat, tol=1e-8):
    """
    The Wigner-Seitz cell of the lattice spanned by the rows of *rlat* (for
    the first Brillouin zone, the reciprocal lattice vectors).

    Returns
    -------
    dict with
        ``vertices`` : ndarray (nv, 3)
        ``faces`` : list of lists of vertex indices, each ordered around its face
        ``face_vectors`` : ndarray (nf, 3), the lattice vector G of each face
            (the face is the plane bisecting 0 and G)
        ``edges`` : ndarray (ne, 2), pairs of vertex indices
    """
    rlat = np.asarray(rlat, dtype=float)
    scale = float(np.max(np.linalg.norm(rlat, axis=1)))
    points = _lattice_points(rlat)
    voronoi = Voronoi(points)
    region = voronoi.regions[voronoi.point_region[0]]
    if -1 in region or not region:
        raise ValueError('The Wigner-Seitz cell is not bounded: check the lattice vectors.')

    # Faces: the ridges between the origin and its neighbours
    raw_faces, face_vectors = [], []
    for (p, q), ridge in zip(voronoi.ridge_points, voronoi.ridge_vertices):
        if 0 not in (p, q) or -1 in ridge:
            continue
        raw_faces.append(ridge)
        face_vectors.append(points[q if p == 0 else p])

    used = sorted({v for face in raw_faces for v in face})
    vertices, mapping = _merge_vertices(voronoi.vertices[used], tol * scale * 1e4)
    index = {v: mapping[i] for i, v in enumerate(used)}

    faces, vectors = [], []
    for ridge, g in zip(raw_faces, face_vectors):
        face = list(dict.fromkeys(index[v] for v in ridge))       # unique, in order
        if len(face) < 3:
            continue                                             # degenerate (a point or an edge)
        centre = vertices[face].mean(axis=0)
        order = _order_around(vertices[face], centre, np.asarray(g))
        faces.append([face[i] for i in order])
        vectors.append(g)

    edges = sorted({tuple(sorted((face[i], face[(i + 1) % len(face)]))) for face in faces for i in range(len(face))})
    return {'vertices': vertices, 'faces': faces, 'face_vectors': np.array(vectors), 'edges': np.array(edges, dtype=int)}


def wigner_seitz_polygon(vectors):
    """
    The 2D Wigner-Seitz cell of the lattice spanned by the two rows of
    *vectors* (2D coordinates), as its vertices ordered counterclockwise.
    """
    vectors = np.asarray(vectors, dtype=float)
    if vectors.shape != (2, 2):
        raise ValueError('Two 2D vectors are needed.')
    points = _lattice_points(vectors)
    voronoi = Voronoi(points)
    region = voronoi.regions[voronoi.point_region[0]]
    if -1 in region or not region:
        raise ValueError('The Wigner-Seitz cell is not bounded: check the lattice vectors.')
    polygon = voronoi.vertices[region]
    order = np.argsort(np.arctan2(polygon[:, 1], polygon[:, 0]))
    return polygon[order]


def plane_section(cell, point, normal, tol=1e-9):
    """
    The polygon where the plane through *point* with *normal* cuts *cell*
    (from :func:`wigner_seitz_cell`): its vertices (n, 3), ordered around it;
    empty (0, 3) if the plane misses the cell.
    """
    vertices = cell['vertices']
    normal = np.asarray(normal, dtype=float)
    normal = normal / np.linalg.norm(normal)
    side = (vertices - np.asarray(point, dtype=float)) @ normal
    scale = float(np.max(np.linalg.norm(vertices, axis=1)))
    found = []
    for a, b in cell['edges']:
        da, db = side[a], side[b]
        if abs(da) <= tol * scale:
            found.append(vertices[a])
        if abs(db) <= tol * scale:
            found.append(vertices[b])
        if da * db < 0 and abs(da) > tol * scale and abs(db) > tol * scale:
            found.append(vertices[a] + da / (da - db) * (vertices[b] - vertices[a]))
    if len(found) < 3:
        return np.empty((0, 3))
    polygon, _ = _merge_vertices(np.array(found), 1e-6 * scale)
    if len(polygon) < 3:
        return np.empty((0, 3))
    order = _order_around(polygon, polygon.mean(axis=0), normal)
    return polygon[order]


def inside_cell(kpoints, cell, tol=1e-6):
    """
    Whether each of *kpoints* (Cartesian, rows) is inside *cell* or on its
    boundary (within *tol*, relative to the size of the cell): closer to the
    origin than to the lattice vector of any face.
    """
    kpoints = np.atleast_2d(np.asarray(kpoints, dtype=float))
    g = cell['face_vectors']
    scale = float(np.max(np.linalg.norm(g, axis=1))) ** 2
    return np.all(kpoints @ g.T <= 0.5 * np.sum(g * g, axis=1) + tol * scale, axis=1)


def fill_wigner_seitz(red_kpoints, rlat, cell=None, tol=1e-6):
    """
    The points of a grid that fall in the first Brillouin zone: copies of
    *red_kpoints* (reduced coordinates of *rlat*), shifted by lattice
    vectors, inside the Wigner-Seitz cell or on its boundary (so a point on
    a face appears on both opposite faces).

    Returns
    -------
    kpoints : ndarray (m, 3), Cartesian
    indices : ndarray (m,), the index in *red_kpoints* of each copy
    """
    rlat = np.asarray(rlat, dtype=float)
    cell = wigner_seitz_cell(rlat) if cell is None else cell
    red = np.asarray(red_kpoints, dtype=float) % 1.0
    red[np.isclose(red, 1.0)] = 0.0
    # Shifts along each axis; none along those where the grid has a single plane (e.g. a layer)
    ranges = [[0] if np.allclose(red[:, axis], red[0, axis]) else [-2, -1, 0, 1] for axis in range(3)]
    kpoints, indices = [], []
    for shift in itertools.product(*ranges):
        car = (red + np.array(shift, dtype=float)) @ rlat
        inside = inside_cell(car, cell, tol)
        kpoints.append(car[inside])
        indices.append(np.nonzero(inside)[0])
    return np.vstack(kpoints), np.concatenate(indices)
