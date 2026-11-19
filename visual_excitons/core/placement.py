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


def _nearestImage(position, atoms, cell):
    """The atom (reduced `atoms`) nearest `position` (reduced): index, the Cartesian vector from it, its length."""
    d = np.asarray(position, dtype=float)[None, :] - atoms
    d -= np.rint(d)
    vectors = (d[:, None, :] + _NEIGHBOURS[None, :, :]) @ cell                  # (atoms, images, 3)
    lengths = np.linalg.norm(vectors, axis=-1)
    i, image = np.unravel_index(np.argmin(lengths), lengths.shape)
    return int(i), vectors[i, image], float(lengths[i, image])


def _bonds(i, atoms, cell, margin=1.15):
    """The bonds of atom i: (neighbour index, Cartesian vector) to the atoms within `margin` x the nearest distance."""
    d = atoms - atoms[i][None, :]
    d -= np.rint(d)
    vectors = ((d[:, None, :] + _NEIGHBOURS[None, :, :]) @ cell).reshape(-1, 3)
    owners = np.repeat(np.arange(len(atoms)), len(_NEIGHBOURS))
    lengths = np.linalg.norm(vectors, axis=-1)
    others = lengths > 1e-6
    if not others.any():
        return []
    nearest = lengths[others].min()
    keep = others & (lengths <= margin * nearest)
    return list(zip(owners[keep].tolist(), vectors[keep]))


def _angle(u, v):
    cosine = np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def distinctMaxima(density, maxima, cell, atomPositions, numbers, layerAxis=None, limit=12):
    """
    The local maxima of a particle density (grid indices, the largest first, as
    yambopy_ext.bse.exciton_particle_density.density_maxima gives them), grouped:
    equivalent maxima (by symmetry) have the same value, the same nearest atom
    species at the same distance and the same angles to its bonds and to the
    layer, so they count once. For each group (at most `limit`, the largest
    first), a dict:

    - 'share': its value, relative to the largest;
    - 'members': grid indices of its maxima;
    - 'atom', 'element': the atom nearest its first member (index in the cell),
      and its element number; 'distance': from that atom (Å);
    - 'bondAngle', 'partner': the angle (degrees) between the direction from the
      atom and its nearest bond, and the element at the other end (None for a
      maximum on the atom or an atom without neighbours);
    - 'elevation': for a layer (`layerAxis`, the vacuum's lattice vector), the
      angle of that direction out of the plane of the layer (0: in it); else None.
    """
    density = np.asarray(density)
    if not len(maxima):
        return []
    shape = np.asarray(density.shape)
    cell = np.asarray(cell, dtype=float)
    atoms = np.asarray(atomPositions, dtype=float) @ np.linalg.inv(cell)
    numbers = [int(z) for z in numbers]
    top = float(density.max())
    normal = None
    if layerAxis is not None:
        a, b = [cell[i] for i in range(3) if i != layerAxis]
        normal = np.cross(a, b)
    groups = []
    for index in maxima:
        index = tuple(int(i) for i in index)
        share = float(density[index]) / top
        i, vector, length = _nearestImage(np.asarray(index) / shape, atoms, cell)
        distance = length * BOHR_TO_ANGSTROM
        bondAngle = partner = elevation = None
        if distance > 0.05:
            bonds = _bonds(i, atoms, cell)
            if bonds:
                angles = [(_angle(vector, b), j) for j, b in bonds]
                bondAngle, j = min(angles)
                partner = numbers[j]
            if normal is not None:
                elevation = abs(90.0 - _angle(vector, normal))
        found = None
        for g in groups:
            if (g['element'] == numbers[i] and abs(g['share'] - share) < 0.005 and abs(g['distance'] - distance) < 0.02
                    and (g['bondAngle'] is None) == (bondAngle is None)
                    and (bondAngle is None or abs(g['bondAngle'] - bondAngle) < 3.0)
                    and (elevation is None or abs(g['elevation'] - elevation) < 3.0)):
                found = g
                break
        if found is not None:
            found['members'].append(index)
            continue
        if len(groups) == limit:
            continue
        groups.append({'share': share, 'members': [index], 'atom': i, 'element': numbers[i], 'distance': distance,
                       'bondAngle': bondAngle, 'partner': partner, 'elevation': elevation})
    return groups


def groupOf(groups, index):
    """The position (in `groups`) of the group with the grid point `index` among its members, or None."""
    index = tuple(int(i) for i in index)
    for n, g in enumerate(groups):
        if index in g['members']:
            return n
    return None


def directionText(group, symbols):
    """The direction of a maximum from its atom, in words: e.g. '12° from the I–Bi bond, in the plane'."""
    if group['bondAngle'] is None and group['elevation'] is None:
        return 'on the atom' if group['distance'] <= 0.05 else ''
    parts = []
    if group['bondAngle'] is not None:
        parts.append(f'{group["bondAngle"]:.0f}° from the {symbols[group["element"]]}–{symbols[group["partner"]]} bond')
    if group['elevation'] is not None:
        e = group['elevation']
        parts.append('in the plane' if e < 10 else 'out of the plane' if e > 80 else f'{e:.0f}° out of the plane')
    return ', '.join(parts)


def nearestMember(group, position, shape, cell):
    """The member of `group` nearest `position` (reduced): its grid index (to move the particle the least)."""
    cell = np.asarray(cell, dtype=float)
    best, chosen = None, group['members'][0]
    for index in group['members']:
        d = np.asarray(index) / np.asarray(shape) - np.asarray(position, dtype=float)
        d -= np.rint(d)
        length = np.linalg.norm(d @ cell)
        if best is None or length < best:
            best, chosen = length, index
    return chosen
