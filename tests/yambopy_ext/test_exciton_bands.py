"""Tests of yambopy_ext.bse.exciton_bands and yambopy_ext.dbs.qp_energies (no Qt: meant to move to YamboPy)."""

import numpy as np
import pytest
from netCDF4 import Dataset

from visual_excitons.yambopy_ext.bse.exciton_bands import band_kpoint_weights, interpolate_on_grid, band_energies_ibz
from visual_excitons.yambopy_ext.dbs.qp_energies import qp_energies

RED = np.array([[0, 0, 0], [0.5, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0]], dtype=float)    # a 2 x 2 x 1 grid


def test_weights_on_the_bands_of_their_particle():
    # Transitions from valence band 3 to conduction band 4, the electron at k = 1..4
    table = np.array([[k, 3, 4] for k in range(1, 5)])
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    at_gamma = band_kpoint_weights(table, weights, 4, 3, 4)
    assert np.allclose(at_gamma[:, 0], weights) and np.allclose(at_gamma[:, 1], weights)
    # Q = (1/2, 0, 0): the hole at k - Q, on the valence band
    holes = np.array([1, 0, 3, 2])
    finite = band_kpoint_weights(table, weights, 4, 3, 4, holes)
    assert np.allclose(finite[:, 1], weights)                     # the electron's, at k
    assert np.allclose(finite[:, 0], weights[[1, 0, 3, 2]])       # the hole's, moved by Q
    assert finite.sum() == pytest.approx(2 * weights.sum())


def test_periodic_linear_interpolation():
    values = np.array([[1.0], [3.0], [5.0], [7.0]])
    # Exact at the grid points, whatever their copy
    assert np.allclose(interpolate_on_grid(RED, values, RED + 1, order=1), values)
    # Half-way: the mean of the neighbours, across the zone boundary too
    points = np.array([[0.25, 0, 0], [0.75, 0, 0], [0.25, 0.25, 0]])
    assert np.allclose(interpolate_on_grid(RED, values, points, order=1)[:, 0], [2.0, 2.0, 4.0])
    # Never outside the range of the values
    random = np.random.default_rng(1).random((50, 3))
    result = interpolate_on_grid(RED, values, random, order=1)
    assert result.min() >= 1.0 and result.max() <= 7.0
    with pytest.raises(ValueError):
        interpolate_on_grid(RED[:3], values[:3], points)          # not a full grid


def test_periodic_cubic_interpolation():
    """Exact at the grid points, periodic, and smooth: no kinks at the grid points, unlike the linear one."""
    n = 12
    red = np.array([[i / n, j / n, 0] for i in range(n) for j in range(n)])
    values = np.cos(2 * np.pi * red[:, 0])[:, None] + 0.5 * np.sin(2 * np.pi * red[:, 1])[:, None]
    assert np.allclose(interpolate_on_grid(red, values, red), values)
    assert np.allclose(interpolate_on_grid(red, values, red + [1, -2, 0]), values)
    line = np.column_stack([np.linspace(0, 1, 241), np.zeros(241), np.zeros(241)])
    exact = np.cos(2 * np.pi * line[:, 0])
    cubic = interpolate_on_grid(red, values, line)[:, 0]
    linear = interpolate_on_grid(red, values, line, order=1)[:, 0]
    assert np.abs(cubic - exact).max() < 0.2 * np.abs(linear - exact).max()
    assert np.abs(np.diff(cubic, 2)).max() < 0.5 * np.abs(np.diff(linear, 2)).max()     # no kinks


def write_qp(path, bands, offset=0.0):
    """A QP database on 2 k-points: DFT energies band - offset (eV), QP corrections 0.1 * band."""
    from yambopy.units import ha2ev
    rows = [(b, b, k) for k in (1, 2) for b in range(bands[0], bands[1] + 1)]
    table = np.array(rows, dtype=float).T
    dft = np.array([b - offset for b, _, _ in rows]) / ha2ev
    qp = np.array([b - offset + 0.1 * b for b, _, _ in rows]) / ha2ev
    with Dataset(path, 'w') as database:
        database.createDimension('n', len(rows))
        database.createDimension('three', 3)
        database.createDimension('two', 2)
        database.createDimension('k', 2)
        database.createVariable('QP_table', 'f8', ('three', 'n'))[:] = table
        energies = database.createVariable('QP_E', 'f8', ('n', 'two'))
        energies[:] = np.column_stack([qp, np.zeros_like(qp)])
        database.createVariable('QP_Eo', 'f8', ('n',))[:] = dft
        database.createVariable('QP_kpts', 'f8', ('three', 'k'))[:] = 0.0


def test_qp_energies_whatever_the_name(tmp_path):
    path = tmp_path / 'ndb.QP_4_6'
    write_qp(path, (4, 6))
    qp = qp_energies(str(path))
    assert (qp['min_band'], qp['max_band'], qp['nkpoints']) == (4, 6, 2)
    assert np.allclose(qp['qp'][0], [4.4, 5.5, 6.6]) and np.allclose(qp['dft'][1], [4, 5, 6])


def test_band_energies_with_qp_outside_its_range(tmp_path):
    path = tmp_path / 'ndb.QP'
    write_qp(path, (4, 6), offset=2.0)                 # the QP database's zero is 2 eV below the SAVE's
    qp = qp_energies(str(path))
    dft_ibz = np.tile(np.arange(1, 9, dtype=float), (2, 1))         # band b at b eV, bands 1-8
    energies, estimated = band_energies_ibz(dft_ibz, 3, 7, qp)
    assert estimated == [3, 7]
    # Bands of the database: its QP energies, in its zero
    assert np.allclose(energies[:, 1:4], [4.4 - 2, 5.5 - 2, 6.6 - 2])
    # Outside: DFT in that zero, corrected as the nearest band of the database
    assert np.allclose(energies[:, 0], 3 - 2 + 0.4) and np.allclose(energies[:, 4], 7 - 2 + 0.6)
    # Without QP: DFT
    dft, none = band_energies_ibz(dft_ibz, 3, 7)
    assert none == [] and np.allclose(dft[0], [3, 4, 5, 6, 7])
