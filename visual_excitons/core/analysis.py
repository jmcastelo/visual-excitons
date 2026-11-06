"""
Analysis of the exciton probability density: plane cuts and the distribution
of distances from the fixed particle.

The density is given on its real-space grid over the supercell: grid point
(i, j, k) is at i v1 + j v2 + k v3, the v's being the voxel vectors (supercell
vectors divided by the number of points). Lengths are in Bohr in and out,
except where noted.
"""

import numpy as np
from scipy.ndimage import map_coordinates, zoom


def voxelVectors(lattice, supercell, shape):
    """Voxel vectors as rows, from the unit-cell vectors (rows), the supercell and the grid shape."""
    return np.asarray(lattice, dtype=float) * (np.asarray(supercell, dtype=float) / np.asarray(shape, dtype=float))[:, None]


def gridPositions(shape, voxels):
    """Cartesian positions of all grid points, shape (n1, n2, n3, 3)."""
    indices = np.stack(np.meshgrid(*(np.arange(n) for n in shape), indexing='ij'), axis=-1).astype(float)
    return indices @ np.asarray(voxels, dtype=float)


def upsampleDensity(density, factor):
    """
    The density on a grid `factor` times finer, by cubic spline interpolation,
    for display: grid point i of the original grid is point factor * i of the
    new one, so the voxel vectors are divided by `factor`. Clipped to [0, 1]
    (splines overshoot slightly near sharp features).
    """
    density = np.asarray(density, dtype=float)
    if factor == 1:
        return density
    target = [(n - 1) * factor + 1 for n in density.shape]
    upsampled = zoom(density, [m / n for m, n in zip(target, density.shape)], order=3, grid_mode=False)
    return np.clip(upsampled, 0.0, 1.0)


# Distribution of distances from the fixed particle

def radialDistribution(density, voxels, center, binWidth=None):
    """
    Distribution of the distance r between the free particle and the fixed
    one, at `center`: with the hole fixed, of the electron-hole distance.

    The density is normalized over the grid, so the result describes the part
    of the exciton inside the supercell (see 'boundary' for how much is cut).

    Returns a dict with (lengths in Bohr):
    - 'r': centers of the distance bins; 'probability': P(r), probability per
      unit length (integrates to 1); 'cumulative': probability within r.
    - 'mean', 'rms', 'median', 'r90': mean, root mean square, median distance
      and distance within which 90% of the probability lies.
    - 'boundary': largest density on the faces of the supercell relative to the
      maximum; when it is not small, the supercell cuts the exciton and the
      distances are underestimated.
    """
    density = np.clip(np.asarray(density, dtype=float), 0.0, None)
    voxels = np.asarray(voxels, dtype=float)
    total = density.sum()
    if total <= 0.0:
        raise ValueError('The density is zero everywhere')

    distances = np.linalg.norm(gridPositions(density.shape, voxels) - np.asarray(center, dtype=float), axis=-1).ravel()
    weights = density.ravel() / total

    if binWidth is None:
        binWidth = min(np.linalg.norm(voxels, axis=1))
    edges = np.arange(0.0, distances.max() + binWidth, binWidth)
    counts, edges = np.histogram(distances, bins=edges, weights=weights)
    cumulative = np.cumsum(counts)

    def quantile(q):
        return float(np.interp(q, np.concatenate([[0.0], cumulative]), edges))

    faces = [density[0], density[-1], density[:, 0], density[:, -1], density[:, :, 0], density[:, :, -1]]
    return {
        'r': 0.5 * (edges[:-1] + edges[1:]),
        'probability': counts / binWidth,
        'cumulative': cumulative,
        'mean': float(weights @ distances),
        'rms': float(np.sqrt(weights @ distances ** 2)),
        'median': quantile(0.5),
        'r90': quantile(0.9),
        'boundary': float(max(face.max() for face in faces) / density.max()),
    }


# Plane cuts

def planeAxes(normal, inPlane=None, latticeVectors=None):
    """
    Orthonormal axes (u, v, n) of a plane with normal `normal`, right-handed:
    seen from the side the normal points to, u points right and v up.

    v is `inPlane` projected onto the plane if given (e.g. the screen's up
    direction); otherwise u is the lattice vector (or Cartesian axis) most
    nearly in the plane, projected onto it.
    """
    n = np.asarray(normal, dtype=float)
    if np.linalg.norm(n) == 0.0:
        raise ValueError('The normal of the plane must be a non-zero vector')
    n = n / np.linalg.norm(n)

    if inPlane is not None:
        v = np.asarray(inPlane, dtype=float)
        v = v - (v @ n) * n
        if np.linalg.norm(v) > 1e-8:
            v /= np.linalg.norm(v)
            return np.cross(v, n), v, n

    candidates = list(np.asarray(latticeVectors, dtype=float)) if latticeVectors is not None else []
    candidates += list(np.eye(3))
    # The candidate most nearly in the plane (smallest angle with it)
    candidate = min(candidates, key=lambda a: abs(a @ n) / np.linalg.norm(a))
    u = candidate - (candidate @ n) * n
    u /= np.linalg.norm(u)
    return u, np.cross(n, u), n


def planeCut(density, voxels, point, normal, inPlane=None, latticeVectors=None, spacing=None):
    """
    The density on the plane through `point` with normal `normal`, sampled on
    a square grid (trilinear interpolation) covering the part of the plane
    inside the supercell; NaN outside it.

    Returns a dict with 'values' (len(t), len(s)), the in-plane coordinates
    's' (along u) and 't' (along v) of the samples, measured from `point`, and
    the axes 'u', 'v', 'n' (see planeAxes).
    """
    density = np.asarray(density, dtype=float)
    voxels = np.asarray(voxels, dtype=float)
    point = np.asarray(point, dtype=float)
    u, v, n = planeAxes(normal, inPlane, latticeVectors)

    # Extent: the supercell's corners projected onto the plane
    shape = np.array(density.shape)
    corners = np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)]) * (shape - 1) @ voxels
    relative = corners - point
    sRange = (relative @ u).min(), (relative @ u).max()
    tRange = (relative @ v).min(), (relative @ v).max()

    if spacing is None:
        spacing = 0.5 * min(np.linalg.norm(voxels, axis=1))
    s = np.arange(sRange[0], sRange[1] + spacing, spacing)
    t = np.arange(tRange[0], tRange[1] + spacing, spacing)
    S, T = np.meshgrid(s, t)
    positions = point + S[..., None] * u + T[..., None] * v

    # Fractional grid indices of the samples; outside the grid: NaN
    indices = np.linalg.solve(voxels.T, positions.reshape(-1, 3).T)
    values = map_coordinates(density, indices, order=1, mode='constant', cval=np.nan)
    inside = np.all((indices >= -1e-9) & (indices <= (shape - 1)[:, None] + 1e-9), axis=0)
    values[~inside] = np.nan

    return {'values': values.reshape(S.shape), 's': s, 't': t, 'u': u, 'v': v, 'n': n}


def planeSupercellPolygon(supercellVectors, point, normal):
    """
    Vertices (in order around it) of the intersection of the plane through
    `point` with normal `normal` and the supercell spanned by
    `supercellVectors` (rows) from the origin; empty if they do not meet.
    """
    vectors = np.asarray(supercellVectors, dtype=float)
    n = np.asarray(normal, dtype=float) / np.linalg.norm(normal)
    corners = {(i, j, k): np.array([i, j, k]) @ vectors for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    side = {key: (corner - point) @ n for key, corner in corners.items()}

    vertices = []
    for p in corners:
        for q in corners:
            # The 12 edges: corners differing in one index
            if p < q and sum(a != b for a, b in zip(p, q)) == 1:
                dp, dq = side[p], side[q]
                if dp == 0.0:
                    vertices.append(corners[p])
                elif dp * dq < 0.0:
                    vertices.append(corners[p] + dp / (dp - dq) * (corners[q] - corners[p]))
    if len(vertices) < 3:
        return np.empty((0, 3))

    vertices = np.unique(np.round(np.array(vertices), 10), axis=0)
    centroid = vertices.mean(axis=0)
    u, v, _ = planeAxes(n)
    angles = np.arctan2((vertices - centroid) @ v, (vertices - centroid) @ u)
    return vertices[np.argsort(angles)]


def atomsNearPlane(positions, numbers, point, axes, tolerance):
    """
    The atoms within `tolerance` of the plane through `point` with axes
    (u, v, n): their numbers, in-plane coordinates (s, t) and distances to the plane.
    """
    u, v, n = axes
    relative = np.asarray(positions, dtype=float).reshape(-1, 3) - np.asarray(point, dtype=float)
    distance = relative @ n
    near = np.abs(distance) <= tolerance
    return np.asarray(numbers)[near], np.column_stack([relative[near] @ u, relative[near] @ v]), distance[near]
