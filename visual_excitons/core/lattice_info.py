"""
What the System panel tells about the crystal: its Bravais lattice (as
detected, see Options.detectLatticeType), space group and point group (from
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
