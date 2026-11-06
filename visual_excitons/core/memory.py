"""
Size of a wave-function calculation before running it: its real-space grid
and the memory it needs, compared with the memory available.

The grid is computed exactly as yambopy's ex_wf2Real does: the smallest FFT
box holding the plane waves of the wave functions with |k + G|^2 below the
cutoff (Ry), plus a margin of 3 points, in each direction. The plane waves are
read from the SAVE database (ns.db1), without loading the wave functions.

The memory is the sum of the largest arrays, from their shapes:

- The wave functions of the bands of the excitons (complex128): kept between
  calculations (see computeWaveFunction's cache), and held about twice while
  loading.
- In ex_wf2Real (complex64): the result, one value per state, spinor pair and
  grid point of the supercell; a buffer of up to 256 k-points over the grid of
  one cell; and the products of one state.
- The probability density: |result|^2 (float32), and the normalized density
  kept for the plots (float64), with its display copies.

It is an estimate of the peak, within some tens of percent: Python and the
libraries add their own memory, and the operating system counts it its way.
"""

import numpy as np

GIB = 2.0 ** 30

# Loading the wave functions holds them about twice (list of arrays, then one array)
WAVEFUNCTION_LOAD_FACTOR = 2.15
# k-points per block in ex_wf2Real: at most yambopy's default, at least enough
# to keep it efficient; the block buffer gets at most this fraction of the
# available memory (or this much when unknown)
MAX_BLOCK_SIZE = 256
MIN_BLOCK_SIZE = 16
BLOCK_MEMORY_FRACTION = 0.25
BLOCK_MEMORY_UNKNOWN = GIB


def availableMemory():
    """(total, available) memory in bytes, or None if psutil is not installed."""
    try:
        import psutil
    except ImportError:
        return None
    memory = psutil.virtual_memory()
    return memory.total, memory.available


def formatBytes(size):
    if size >= GIB:
        return f'{size / GIB:.1f} GB'
    return f'{size / 2.0 ** 20:.0f} MB'


class PlaneWaves:
    """Plane waves of the wave functions of a SAVE database: their grids and size."""

    def __init__(self, saveDir, lattice):
        """`lattice`: the YamboLatticeDB of the database."""
        from netCDF4 import Dataset

        with Dataset(f'{saveDir}/ns.db1', 'r') as database:
            dimensions = np.asarray(database.variables['DIMENSIONS'][:], dtype=float)
            gVectors = np.asarray(database.variables['G-VECTORS'][:]).T
            wfcGrid = np.rint(np.asarray(database.variables['WFC_GRID'][:])).astype(int)
            wfcNg = np.rint(np.asarray(database.variables['WFC_NG'][:])).astype(int)

        self.nspinor = int(round(dimensions[11]))
        self.nspin = int(round(dimensions[12]))
        self.nbands = int(round(dimensions[5]))
        self.ngMax = int(wfcNg.max())

        # As yambopy's YamboWFDB: G-vectors and k-points in crystal coordinates
        latticeVectors = np.asarray(lattice.lat, dtype=float).T
        alat = np.asarray(lattice.alat, dtype=float)
        miller = np.rint((gVectors / alat[None, :]) @ latticeVectors).astype(int)
        kpoints = (np.asarray(lattice.ibz_kpoints, dtype=float) / alat[None, :]) @ latticeVectors
        self.nkpoints = len(kpoints)

        self._miller = [miller[wfcGrid[ik, :wfcNg[ik]] - 1] for ik in range(len(kpoints))]
        self._kpoints = kpoints
        self._reciprocal = np.linalg.inv(latticeVectors)
        self._boxes = {}

    def fftBox(self, cutoffRy):
        """Points per unit cell along each lattice vector at `cutoffRy` (<= 0: all the plane waves)."""
        key = float(cutoffRy) if cutoffRy > 0 else -1.0
        if key not in self._boxes:
            box = np.zeros(3, dtype=int)
            for miller, kpoint in zip(self._miller, self._kpoints):
                if key > 0:
                    norms = 2 * np.pi * np.linalg.norm((miller + kpoint[None, :]) @ self._reciprocal, axis=1)
                    miller = miller[norms < np.sqrt(key)]
                if len(miller):
                    box = np.maximum(box, miller.max(axis=0) - miller.min(axis=0) + 3)
            self._boxes[key] = tuple(int(n) for n in box)
        return self._boxes[key]

    def wavefunctionBytes(self, nbandsUsed):
        """Memory of the wave functions of `nbandsUsed` bands, as loaded by YamboWFDB (complex128)."""
        return self.nkpoints * self.nspin * nbandsUsed * self.nspinor * self.ngMax * 16


def chooseBlockSize(planeWaves, fftBox, nstates, nkBZ, available=None):
    """
    k-points per block of ex_wf2Real: its buffer holds the wave function of
    every state and spinor pair for a block of k-points over one cell, which
    for many degenerate states and fine grids can take gigabytes. The block
    only changes how the sum over k-points is split, not the result, so it is
    reduced to fit a share of the available memory.
    """
    perKpoint = nstates * planeWaves.nspin * planeWaves.nspinor ** 2 * int(np.prod(fftBox)) * 8
    budget = BLOCK_MEMORY_FRACTION * available if available else BLOCK_MEMORY_UNKNOWN
    block = int(budget // max(perKpoint, 1))
    return int(min(nkBZ, MAX_BLOCK_SIZE, max(MIN_BLOCK_SIZE, block)))


def estimateMemory(planeWaves, fftBox, supercell, nstates, nbandsUsed, nkBZ, wavefunctionsLoaded=False,
                   displayFactor=1, blockSize=MAX_BLOCK_SIZE):
    """
    Memory of a wave-function calculation, in bytes: a dict with the 'peak'
    during the calculation, what stays in use afterwards ('kept'), and the
    parts: 'wavefunctions', 'realSpace', 'display'.

    `nstates`: states computed together (the exciton and those degenerate with
    it); `nbandsUsed`: bands of the excitons; `nkBZ`: k-points of the BSE;
    `wavefunctionsLoaded`: already in memory (cached); `displayFactor`: display
    upsampling along each direction; `blockSize`: k-points per block.
    """
    pointsPerCell = int(np.prod(fftBox))
    points = int(np.prod(supercell)) * pointsPerCell
    spinorPairs = nstates * planeWaves.nspin * planeWaves.nspinor ** 2

    wavefunctions = planeWaves.wavefunctionBytes(nbandsUsed)
    loading = 0 if wavefunctionsLoaded else (WAVEFUNCTION_LOAD_FACTOR - 1) * wavefunctions

    result = spinorPairs * points * 8                                    # complex64
    block = spinorPairs * min(nkBZ, blockSize) * pointsPerCell * 8       # complex64
    products = 2 * points * 8                                            # one state, and its reordered copy
    density = spinorPairs * points * 4 + points * (4 + 8 + 8)            # |result|^2, sum, normalized, clipped
    realSpace = result + max(block + products, density)

    # Kept for the plots: the density, and its display copy, volume colors (float32
    # RGBA) and isosurfaces at the display resolution
    displayPoints = points * displayFactor ** 3
    display = points * 8 + displayPoints * (8 + 16 + 8)

    return {
        'peak': wavefunctions + max(loading, realSpace) + display,
        'kept': wavefunctions + display,
        'wavefunctions': wavefunctions,
        'realSpace': realSpace,
        'display': display,
        'points': points,
        'pointsPerCell': pointsPerCell,
    }
