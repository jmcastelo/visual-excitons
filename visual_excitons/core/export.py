"""
Export of the exciton probability density, on its real-space grid, with the
atoms of the supercell, as read by VESTA, VMD, XCrySDen, Ovito, ParaView...

- Gaussian cube (.cube): lengths in Bohr; values listed with the last grid
  index fastest, in rows of at most six, a new row for each line of the grid.
- XCrySDen XSF (.xsf): lengths in angstrom; a periodic "general grid", which
  repeats the first point of each direction at its end, listed with the
  first index fastest.

The grid starts at the origin of the supercell, with grid point (i, j, k) at
i a1 / n1 + j a2 / n2 + k a3 / n3, the a's being the supercell vectors; the
atoms are those of the unit cell repeated over the supercell, as drawn in the
3D view. The fixed particle is not an atom: its position goes in the comments.
"""

import numpy as np

from .atomic_data import BOHR_TO_ANGSTROM, chemical_symbols


def supercellAtoms(lattice, positions, atomicNumbers, supercell):
    """Atomic numbers and Cartesian positions of the atoms of the supercell (cells 0 to n - 1)."""
    lattice = np.asarray(lattice, dtype=float)
    positions = np.asarray(positions, dtype=float).reshape(-1, 3)
    numbers = np.asarray(atomicNumbers, dtype=int)[:len(positions)]
    cells = np.stack(np.meshgrid(*(np.arange(n) for n in supercell), indexing='ij'), axis=-1).reshape(-1, 3)
    allPositions = (cells @ lattice)[:, None, :] + positions[None, :, :]
    return np.tile(numbers, len(cells)), allPositions.reshape(-1, 3)


def _rows(values, perLine, fmt):
    """Text of `values` (2D: one block per row) in lines of at most `perLine` values."""
    nRows, nValues = values.shape
    full, rest = divmod(nValues, perLine)
    rowFormat = (fmt * perLine + '\n') * full + ((fmt * rest + '\n') if rest else '')
    return (rowFormat * nRows) % tuple(values.ravel())


def writeCube(filename, density, lattice, supercell, atomicNumbers, atomPositions, comment=''):
    """
    Gaussian cube file of `density` (n1, n2, n3) on the supercell of `lattice`
    (unit-cell vectors as rows, Bohr); atoms in Cartesian Bohr.
    """
    density = np.asarray(density, dtype=float)
    supercellLattice = np.asarray(lattice, dtype=float) * np.asarray(supercell)[:, None]
    voxels = supercellLattice / np.array(density.shape)[:, None]
    numbers = np.asarray(atomicNumbers, dtype=int)
    positions = np.asarray(atomPositions, dtype=float).reshape(-1, 3)

    lines = ['Exciton probability density, written by Visual Excitons',
             ' '.join(comment.split()) or 'Values relative to the maximum',
             f'{len(numbers):5d} {0.0:12.6f} {0.0:12.6f} {0.0:12.6f}']
    # Positive numbers of points: lengths in Bohr
    lines += [f'{n:5d} {v[0]:12.6f} {v[1]:12.6f} {v[2]:12.6f}' for n, v in zip(density.shape, voxels)]
    lines += [f'{z:5d} {float(z):12.6f} {p[0]:12.6f} {p[1]:12.6f} {p[2]:12.6f}' for z, p in zip(numbers, positions)]

    with open(filename, 'w') as file:
        file.write('\n'.join(lines) + '\n')
        file.write(_rows(density.reshape(-1, density.shape[2]), 6, ' %12.5E'))


def writeXsf(filename, density, lattice, supercell, atomicNumbers, atomPositions, comment=''):
    """
    XSF file of `density` (n1, n2, n3) on the supercell of `lattice` (unit-cell
    vectors as rows, Bohr); atoms in Cartesian Bohr. Written in angstrom.
    """
    density = np.asarray(density, dtype=float)
    supercellLattice = np.asarray(lattice, dtype=float) * np.asarray(supercell)[:, None] * BOHR_TO_ANGSTROM
    numbers = np.asarray(atomicNumbers, dtype=int)
    positions = np.asarray(atomPositions, dtype=float).reshape(-1, 3) * BOHR_TO_ANGSTROM

    lines = ['# Exciton probability density, written by Visual Excitons']
    lines += [f'# {line}' for line in comment.splitlines() if line.strip()]
    lines += ['CRYSTAL', 'PRIMVEC']
    lines += [f'{v[0]:14.8f} {v[1]:14.8f} {v[2]:14.8f}' for v in supercellLattice]
    lines += ['PRIMCOORD', f'{len(numbers)} 1']
    lines += [f'{chemical_symbols[z]:<3s} {p[0]:14.8f} {p[1]:14.8f} {p[2]:14.8f}' for z, p in zip(numbers, positions)]

    # General periodic grid: the first point of each direction repeated at its end
    periodic = np.pad(density, ((0, 1), (0, 1), (0, 1)), mode='wrap')
    lines += ['BEGIN_BLOCK_DATAGRID_3D', 'exciton_probability_density', 'BEGIN_DATAGRID_3D_density',
              '{} {} {}'.format(*periodic.shape), f'{0.0:14.8f} {0.0:14.8f} {0.0:14.8f}']
    lines += [f'{v[0]:14.8f} {v[1]:14.8f} {v[2]:14.8f}' for v in supercellLattice]

    with open(filename, 'w') as file:
        file.write('\n'.join(lines) + '\n')
        # First index fastest
        values = periodic.ravel(order='F')
        file.write(_rows(values.reshape(1, -1), 6, ' %12.5E'))
        file.write('END_DATAGRID_3D\nEND_BLOCK_DATAGRID_3D\n')


DENSITY_FORMATS = {'.cube': writeCube, '.xsf': writeXsf}


def writeDensity(filename, *args, **kwargs):
    """Write a density file, in the format given by the extension of `filename`."""
    suffix = '.' + str(filename).rsplit('.', 1)[-1].lower() if '.' in str(filename) else ''
    if suffix not in DENSITY_FORMATS:
        raise ValueError(f'Unknown density format "{suffix}": use one of {", ".join(DENSITY_FORMATS)}')
    DENSITY_FORMATS[suffix](filename, *args, **kwargs)
