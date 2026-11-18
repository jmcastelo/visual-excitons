"""
What the System panel tells about the crystal: its Bravais lattice (as
detected, see dataset.Dataset.detectLatticeType), space group and point group (from
the atoms, with spglib), formula, volume, k-point grid and layer.
"""

import warnings
from math import gcd
from functools import reduce

import numpy as np

from .atomic_data import BOHR_TO_ANGSTROM, chemical_symbols
from .cellshift import reducedPositions, detectLayer

# Bravais lattices by Quantum ESPRESSO ibrav (both settings of those with two)
BRAVAIS_NAMES = {
    1: 'Cubic P (simple)', 2: 'Cubic F (face-centred)', 3: 'Cubic I (body-centred)',
    4: 'Hexagonal', 5: 'Rhombohedral', 6: 'Tetragonal P (simple)', 7: 'Tetragonal I (body-centred)',
    8: 'Orthorhombic P (simple)', 9: 'Orthorhombic C (base-centred)', 10: 'Orthorhombic F (face-centred)',
    11: 'Orthorhombic I (body-centred)',
}


def bravaisName(ibrav):
    return BRAVAIS_NAMES.get(abs(int(ibrav)), f'ibrav {ibrav}') if ibrav is not None else None


def formula(numbers):
    """Reduced chemical formula, elements in the order they first appear, e.g. WSe2, BiI3."""
    order, counts = [], {}
    for z in numbers:
        z = int(z)
        if z not in counts:
            order.append(z)
            counts[z] = 0
        counts[z] += 1
    if not counts:
        return ''
    divisor = reduce(gcd, counts.values())
    return ''.join(chemical_symbols[z] + (str(counts[z] // divisor) if counts[z] // divisor > 1 else '') for z in order)


def spaceGroup(cell, numbers, positions, symprec):
    """
    (international symbol, number, point group, number of operations) of the
    crystal, or None; `symprec` relative to the longest vector.
    """
    import spglib
    cell = np.asarray(cell, dtype=float)
    scale = float(np.max(np.linalg.norm(cell, axis=1)))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        dataset = spglib.get_symmetry_dataset((cell, reducedPositions(cell, positions) % 1.0,
                                               [int(z) for z in numbers]), symprec=symprec * scale)
    if dataset is None:
        return None
    get = (lambda name: getattr(dataset, name)) if hasattr(dataset, 'number') else (lambda name: dataset[name])
    return str(get('international')), int(get('number')), str(get('pointgroup')), len(get('rotations'))


def latticeSummary(cell, numbers, positions, grid, symprec):
    """
    The crystal's description: 'formula', 'atoms', 'volume' (Å³), 'spaceGroup'
    (symbol, number, point group, or None), 'grid' and 'layer' (the axis of the
    vacuum of a layered cell, or None). Lengths of `cell` and `positions` in Bohr.
    """
    cell = np.asarray(cell, dtype=float)
    positions = np.asarray(positions, dtype=float)[:len(numbers)]
    layer = detectLayer(cell, positions, grid)
    return {
        'formula': formula(numbers),
        'atoms': len(numbers),
        'volume': abs(float(np.linalg.det(cell))) * BOHR_TO_ANGSTROM ** 3,
        'spaceGroup': spaceGroup(cell, numbers, positions, symprec) if len(numbers) else None,
        'grid': list(grid) if grid is not None else None,
        'layer': None if layer is None else layer[0],
    }


# Identifying the lattice (see dataset.Dataset.detectLatticeType)

# Symmetry tolerances tried to identify the lattice (relative to the longest
# lattice vector), strictest first: the most symmetric lattice found is taken,
# so that a cell slightly off its symmetry (e.g. relaxed with numerical noise:
# hexagonal with a and b differing by 1e-5) is not taken for a lower one
SYMMETRY_TOLERANCES = (1e-5, 1e-4, 1e-3)

# Order of the point group of each lattice family (its holohedry), by variant family
LATTICE_SYMMETRY = {'CUB': 48, 'FCC': 48, 'BCC': 48, 'HEX': 24, 'TET': 16, 'BCT': 16, 'RHL': 12,
                    'ORC': 8, 'ORCC': 8, 'ORCF': 8, 'ORCI': 8}

# Lattice variants (Setyawan-Curtarolo) by family, and their ibrav (with the
# other orientation of the same lattice, if any)
VARIANT_IBRAV = {'CUB': [1], 'FCC': [2], 'BCC': [3, -3], 'HEX': [4], 'RHL': [5, -5], 'TET': [6], 'BCT': [7],
                 'ORC': [8], 'ORCC': [9, -9], 'ORCF': [10], 'ORCI': [11]}


def ibravCandidates(variant):
    """The ibrav values of a lattice variant (e.g. BCT2 -> [7], RHL1 -> [5, -5])."""
    return VARIANT_IBRAV.get(variant.rstrip('0123456789'), [])


def cellParameters(cell):
    """The lengths a, b, c (the units of `cell`) and angles alpha, beta, gamma (degrees) of a cell (rows: a, b, c)."""
    cell = np.asarray(cell, dtype=float)

    def angle(u, v):
        return np.round(np.degrees(np.arccos(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v)))), 4)
    a, b, c = cell
    return {'a': np.round(np.linalg.norm(a), 4), 'b': np.round(np.linalg.norm(b), 4),
            'c': np.round(np.linalg.norm(c), 4), 'alpha': angle(b, c), 'beta': angle(a, c), 'gamma': angle(a, b)}


def tickLabels(labels):
    """
    Path labels as shown on the plots: Γ, Σ₁, K′, merged sections as K|U
    (yambopy's Unicode rendering); a label it cannot read (e.g. from an older
    session file) is shown as it is.
    """
    from yambopy.bz.labels import format_label
    shown = []
    for label in labels:
        try:
            shown.append(format_label(str(label), 'unicode'))
        except ValueError:
            shown.append(str(label))
    return shown


# View directions (VESTA convention: the direction of projection, from the
# viewer into the screen), in the basis of each group; see viewVectorToCartesian

VIEW_BASES = ['Cartesian', 'Lattice [uvw]', 'Reciprocal (hkl)']
VIEW_PRESETS = {
    'Cartesian': {'x': [1, 0, 0], 'y': [0, 1, 0], 'z': [0, 0, 1], 'x + y': [1, 1, 0], 'x + z': [1, 0, 1],
                  'y + z': [0, 1, 1], 'x + y + z': [1, 1, 1]},
    'Lattice [uvw]': {'a  [1 0 0]': [1, 0, 0], 'b  [0 1 0]': [0, 1, 0], 'c  [0 0 1]': [0, 0, 1],
                      '[1 1 0]': [1, 1, 0], '[1 0 1]': [1, 0, 1], '[0 1 1]': [0, 1, 1], '[1 1 1]': [1, 1, 1]},
    'Reciprocal (hkl)': {'a*  normal to (1 0 0)': [1, 0, 0], 'b*  normal to (0 1 0)': [0, 1, 0],
                         'c*  normal to (0 0 1)': [0, 0, 1], 'normal to (1 1 0)': [1, 1, 0],
                         'normal to (1 0 1)': [1, 0, 1], 'normal to (0 1 1)': [0, 1, 1],
                         'normal to (1 1 1)': [1, 1, 1]},
}


def viewVectorToCartesian(vector, basis, cell):
    """
    Cartesian components of `vector` given in `basis` (one of VIEW_BASES):
    Cartesian, lattice [uvw] -> u a + v b + w c, or reciprocal (hkl) -> h a* + k b* + l c*,
    for the lattice `cell` (rows: a, b, c; None or empty if there is none).
    Only the direction matters, so the 2*pi factor of the reciprocal basis is dropped.
    """
    vector = np.asarray(vector, dtype=float)
    if basis == 'Cartesian':
        return vector
    if cell is None or not len(cell):
        raise ValueError('Lattice vectors are not available: no SAVE database loaded')
    cell = np.asarray(cell, dtype=float)
    if basis == 'Lattice [uvw]':
        return cell.T @ vector
    if basis == 'Reciprocal (hkl)':
        return np.linalg.inv(cell) @ vector          # h a* + k b* + l c* (rows of inv(cell).T)
    raise ValueError(f'Unknown view basis: {basis}')
