"""Size of wave-function calculations: real-space grid and memory."""

import sys

import numpy as np
import pytest

from visual_excitons.core.memory import (PlaneWaves, estimateMemory, chooseBlockSize, availableMemory, formatBytes,
                                         GIB, MIN_BLOCK_SIZE, MAX_BLOCK_SIZE)
from visual_excitons.core.analysis import upsampleDensity
from conftest import datasetPath


class FakePlaneWaves:
    nspin, nspinor, nkpoints, ngMax = 1, 2, 10, 1000

    def wavefunctionBytes(self, nbandsUsed):
        return self.nkpoints * self.nspin * nbandsUsed * self.nspinor * self.ngMax * 16


def test_estimate_parts():
    planeWaves = FakePlaneWaves()
    fftBox, supercell = (10, 10, 10), [3, 3, 1]
    estimate = estimateMemory(planeWaves, fftBox, supercell, nstates=2, nbandsUsed=5, nkBZ=512, blockSize=64)
    points = 9 * 1000
    pairs = 2 * 1 * 4
    assert estimate['points'] == points and estimate['pointsPerCell'] == 1000
    assert estimate['wavefunctions'] == 10 * 5 * 2 * 1000 * 16
    block = pairs * 64 * 1000 * 8
    assert estimate['realSpace'] == pairs * points * 8 + max(block + 2 * points * 8, pairs * points * 4 + points * 20)
    # Loading holds the wave functions about twice; once loaded, no more
    assert estimate['peak'] >= estimate['wavefunctions'] + estimate['realSpace']
    loaded = estimateMemory(planeWaves, fftBox, supercell, 2, 5, 512, wavefunctionsLoaded=True, blockSize=64)
    assert loaded['peak'] == loaded['wavefunctions'] + loaded['realSpace'] + loaded['display']
    assert loaded['kept'] == estimate['kept']
    # Display upsampling adds display memory only
    smooth = estimateMemory(planeWaves, fftBox, supercell, 2, 5, 512, displayFactor=3, blockSize=64)
    assert smooth['realSpace'] == estimate['realSpace'] and smooth['display'] > 20 * estimate['display'] / 3


def test_block_size_fits_the_memory():
    planeWaves = FakePlaneWaves()
    fftBox = (46, 46, 46)
    perKpoint = 10 * 1 * 4 * 46 ** 3 * 8
    # Plenty of memory: yambopy's default
    assert chooseBlockSize(planeWaves, fftBox, 1, 512, available=64 * GIB) == MAX_BLOCK_SIZE
    # Little: the buffer within a quarter of it, but never below the minimum
    block = chooseBlockSize(planeWaves, fftBox, 10, 512, available=8 * GIB)
    assert block * perKpoint <= 2 * GIB < (block + 1) * perKpoint
    assert chooseBlockSize(planeWaves, fftBox, 10, 512, available=0.1 * GIB) == MIN_BLOCK_SIZE
    # Never more than the k-points
    assert chooseBlockSize(planeWaves, (4, 4, 4), 1, 27, available=64 * GIB) == 27


def test_available_memory_is_optional(monkeypatch):
    memory = availableMemory()
    assert memory is None or (memory[0] >= memory[1] > 0)
    monkeypatch.setitem(sys.modules, 'psutil', None)   # as if not installed
    assert availableMemory() is None
    assert formatBytes(2.5 * GIB) == '2.5 GB' and formatBytes(300 * 2 ** 20) == '300 MB'


@pytest.mark.data
def test_grid_as_yambopy(lattice):
    """The FFT grids yambopy's ex_wf2Real used for BiI3 at these cutoffs, and its wave-function size."""
    lat = lattice('BiI3_Bulk_8x8x8')
    planeWaves = PlaneWaves(str(datasetPath('BiI3_Bulk_8x8x8') / 'save'), lat)
    assert (planeWaves.nkpoints, planeWaves.nspin, planeWaves.nspinor, planeWaves.ngMax) == (90, 1, 2, 27626)
    for cutoff, points in ((5, 13), (10, 18), (20, 24), (-1, 46)):
        assert planeWaves.fftBox(cutoff) == (points,) * 3
    # YamboWFDB holds 14 bands of BiI3 in 1062.3 MB (measured)
    assert planeWaves.wavefunctionBytes(14) / 2 ** 20 == pytest.approx(1062.3, abs=0.1)


def test_upsampling_keeps_the_grid_values():
    x = np.linspace(0, 1, 9)
    density = np.exp(-((x[:, None, None] - 0.4) ** 2 + (x[None, :, None] - 0.5) ** 2 + (x[None, None, :] - 0.6) ** 2) * 8)
    for factor in (2, 3):
        fine = upsampleDensity(density, factor)
        assert fine.shape == tuple((n - 1) * factor + 1 for n in density.shape)
        np.testing.assert_allclose(fine[::factor, ::factor, ::factor], density, atol=1e-6)
        assert fine.min() >= 0.0 and fine.max() <= 1.0
    assert upsampleDensity(density, 1) is not None and upsampleDensity(density, 1).shape == density.shape
