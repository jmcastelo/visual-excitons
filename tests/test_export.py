"""Export of the probability density (cube, XSF) and of the 3D view as an image."""

import numpy as np
import pytest

from visual_excitons.core.atomic_data import BOHR_TO_ANGSTROM
from visual_excitons.core.export import supercellAtoms, writeCube, writeXsf, writeDensity
from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations

LATTICE = np.array([[4.0, 0.0, 0.0], [1.0, 5.0, 0.0], [0.0, 0.5, 6.0]])   # Bohr, rows
POSITIONS = np.array([[0.0, 0.0, 0.0], [1.0, 1.5, 2.0]])
NUMBERS = [83, 53]


def indexedDensity(shape):
    """Values encoding their own grid indices: 10000 i + 100 j + k."""
    i, j, k = np.indices(shape)
    return (10000 * i + 100 * j + k).astype(float)


def test_supercell_atoms():
    numbers, positions = supercellAtoms(LATTICE, POSITIONS, NUMBERS, [3, 1, 2])
    assert len(numbers) == len(positions) == 2 * 6
    assert list(numbers[:4]) == [83, 53, 83, 53]
    # Cells 0..n-1 along each vector, as in the 3D view
    np.testing.assert_allclose(positions.min(axis=0), [0, 0, 0])
    np.testing.assert_allclose(positions[-1], POSITIONS[1] + 2 * LATTICE[0] + 1 * LATTICE[2])


def readCube(path):
    lines = open(path).read().splitlines()
    natoms = int(lines[2].split()[0])
    axes = [lines[3 + i].split() for i in range(3)]
    shape = tuple(int(axis[0]) for axis in axes)
    voxels = np.array([[float(x) for x in axis[1:]] for axis in axes])
    atoms = [lines[6 + n].split() for n in range(natoms)]
    values = np.array(' '.join(lines[6 + natoms:]).split(), dtype=float)
    return lines[:2], shape, voxels, atoms, values, lines[6 + natoms:]


def test_cube_file(tmp_path):
    density = indexedDensity((4, 3, 8))   # 8 values per line of the grid: rows of 6 + 2
    numbers, positions = supercellAtoms(LATTICE, POSITIONS, NUMBERS, [2, 1, 1])
    path = tmp_path / 'density.cube'
    writeCube(path, density, LATTICE, [2, 1, 1], numbers, positions, comment='Exciton 1')

    comments, shape, voxels, atoms, values, dataLines = readCube(path)
    assert comments[1] == 'Exciton 1' and shape == (4, 3, 8)
    # Voxel vectors: supercell vectors (Bohr) over the number of points
    np.testing.assert_allclose(voxels, LATTICE * np.array([[2], [1], [1]]) / np.array([[4], [3], [8]]), atol=1e-6)
    assert [int(a[0]) for a in atoms] == [83, 53, 83, 53]
    np.testing.assert_allclose([float(x) for x in atoms[-1][2:]], positions[-1], atol=1e-6)
    # Last index fastest, a new line for each line of the grid
    np.testing.assert_allclose(values, density.ravel(), rtol=1e-5)
    assert len(dataLines) == 4 * 3 * 2 and len(dataLines[0].split()) == 6 and len(dataLines[1].split()) == 2


def test_small_values_are_kept(tmp_path):
    """Scientific notation: the tails of the density do not round to zero."""
    density = np.full((2, 2, 2), 3.2e-9)
    writeCube(tmp_path / 'tiny.cube', density, LATTICE, [1, 1, 1], [83], [[0, 0, 0]])
    assert np.all(readCube(tmp_path / 'tiny.cube')[4] == pytest.approx(3.2e-9))


def readXsf(path):
    lines = [line for line in open(path).read().splitlines() if not line.startswith('#')]
    primvec = np.array([[float(x) for x in lines[2 + i].split()] for i in range(3)])
    natoms = int(lines[6].split()[0])
    atoms = [lines[7 + n].split() for n in range(natoms)]
    start = lines.index('BEGIN_DATAGRID_3D_density')
    shape = tuple(int(x) for x in lines[start + 1].split())
    origin = [float(x) for x in lines[start + 2].split()]
    span = np.array([[float(x) for x in lines[start + 3 + i].split()] for i in range(3)])
    end = lines.index('END_DATAGRID_3D')
    values = np.array(' '.join(lines[start + 6:end]).split(), dtype=float)
    return primvec, atoms, shape, origin, span, values


def test_xsf_file(tmp_path):
    density = indexedDensity((4, 3, 5))
    numbers, positions = supercellAtoms(LATTICE, POSITIONS, NUMBERS, [1, 2, 1])
    path = tmp_path / 'density.xsf'
    writeXsf(path, density, LATTICE, [1, 2, 1], numbers, positions, comment='Exciton 1\nhole at 0 0 0')
    text = open(path).read()
    assert text.startswith('# Exciton probability density') and '# hole at 0 0 0' in text
    assert text.rstrip().endswith('END_BLOCK_DATAGRID_3D')

    primvec, atoms, shape, origin, span, values = readXsf(path)
    supercellAngstrom = LATTICE * np.array([[1], [2], [1]]) * BOHR_TO_ANGSTROM
    np.testing.assert_allclose(primvec, supercellAngstrom, atol=1e-7)
    np.testing.assert_allclose(span, supercellAngstrom, atol=1e-7)
    assert origin == [0, 0, 0] and [a[0] for a in atoms] == ['Bi', 'I', 'Bi', 'I']
    np.testing.assert_allclose([float(x) for x in atoms[-1][1:]], positions[-1] * BOHR_TO_ANGSTROM, atol=1e-7)
    # Periodic grid: one more point per direction, repeating the first; first index fastest
    assert shape == (5, 4, 6)
    grid = values.reshape(shape[::-1]).transpose(2, 1, 0)
    np.testing.assert_allclose(grid[:4, :3, :5], density, rtol=1e-5)
    np.testing.assert_allclose(grid[4], grid[0]) and np.testing.assert_allclose(grid[:, :, 5], grid[:, :, 0])


def test_format_from_extension(tmp_path):
    density = np.ones((2, 2, 2))
    writeDensity(tmp_path / 'a.CUBE', density, LATTICE, [1, 1, 1], [83], [[0, 0, 0]])
    writeDensity(tmp_path / 'a.xsf', density, LATTICE, [1, 1, 1], [83], [[0, 0, 0]])
    assert (tmp_path / 'a.CUBE').stat().st_size > 0 and (tmp_path / 'a.xsf').stat().st_size > 0
    with pytest.raises(ValueError, match='Unknown density format'):
        writeDensity(tmp_path / 'a.vtk', density, LATTICE, [1, 1, 1], [83], [[0, 0, 0]])


# Through the calculations

class FakeLattice:
    lat = LATTICE
    atomic_numbers = NUMBERS
    car_atomic_positions = POSITIONS


def test_export_density_of_the_wave_function(qtbot, tmp_path):
    calculations = Calculations(Options(), synchronous=True)
    with qtbot.waitSignal(calculations.errorOccurred) as blocker:
        calculations.exportDensity(str(tmp_path / 'none.cube'))
    assert 'compute one first' in blocker.args[1]

    calculations.lattice = FakeLattice()
    calculations.waveFunction = indexedDensity((6, 3, 3)) / 1e5
    calculations.wfSupercell = [3, 1, 1]
    calculations.wfFixedParticle = 'h'
    calculations.wfFixedPosition = [0.5, 0.0, 0.0]
    calculations.wfExciton = (4, 2)

    path = str(tmp_path / 'wf.cube')
    with qtbot.waitSignal(calculations.densityExported) as blocker:
        calculations.exportDensity(path)
    assert blocker.args == [path]
    comments, shape, voxels, atoms, values, _ = readCube(path)
    assert shape == (6, 3, 3) and len(atoms) == 2 * 3
    # The fixed hole, in the central cell of the supercell (crystal 1.5, 0, 0)
    assert 'Exciton 2 at Q-point 5' in comments[1] and 'hole fixed at crystal coordinates 1.5000 0.0000 0.0000' in comments[1]


# The 3D view as an image. Rendering needs OpenGL, which Qt's offscreen
# platform lacks (showing an OpenGL widget there crashes), so these checks run
# in a separate process on the display, and are skipped without one.

def test_image_rendering_on_the_display():
    import os
    import subprocess
    import sys
    from pathlib import Path

    environment = dict(os.environ)
    if environment.get('WAYLAND_DISPLAY'):
        environment['QT_QPA_PLATFORM'] = 'wayland'
    elif environment.get('DISPLAY'):
        environment['QT_QPA_PLATFORM'] = 'xcb'
    else:
        pytest.skip('no display: OpenGL rendering cannot be tested')

    script = Path(__file__).with_name('render_checks.py')
    result = subprocess.run([sys.executable, str(script)], env=environment, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr[-3000:]
    assert 'all render checks passed' in result.stdout
