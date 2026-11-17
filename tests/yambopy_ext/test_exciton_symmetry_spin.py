"""Tests of yambopy_ext.bse.exciton_symmetry and exciton_spin (no Qt, synthetic data: meant to move to YamboPy)."""

import numpy as np
import pytest

from visual_excitons.yambopy_ext.bse.exciton_symmetry import little_group, degenerate_groups
from visual_excitons.yambopy_ext.bse.exciton_spin import spin_operator, spin_matrix_elements


def test_spin_operator():
    for direction in ((0, 0, 1), (1, 0, 0), (1, 1, 1)):
        s = spin_operator(direction)
        assert np.allclose(s, s.conj().T)
        assert np.allclose(np.linalg.eigvalsh(s), [-0.5, 0.5])
    assert np.allclose(spin_operator((0, 0, 2)), [[0.5, 0], [0, -0.5]])


def test_little_group():
    lat = np.eye(3) * 5.0
    rotations = np.array([np.eye(3), -np.eye(3), np.diag([1, -1, 1]), np.diag([-1, 1, 1])], dtype=float)
    assert little_group(rotations, lat, np.zeros(3)) == [0, 1, 2, 3]              # Γ: all
    assert little_group(rotations, lat, [0.25, 0, 0]) == [0, 2]                   # along x: those keeping x
    assert little_group(rotations, lat, [0.5, 0, 0]) == [0, 1, 2, 3]              # zone boundary: -q = q + G


def test_degenerate_groups():
    energies = [2.0, 2.1, 2.1004, 1.9, 2.3]
    assert degenerate_groups(energies, atol=1e-3, rtol=0) == [[4], [1], [2, 3], [5]]


class FakeLattice:
    """Two irreducible k-points; four on the full grid, from the identity and an inversion (no time reversal)."""
    sym_car = np.array([np.eye(3), -np.eye(3)])
    time_rev = 0
    symmetry_indexes = np.array([0, 0, 1, 1])
    kpoints_indexes = np.array([0, 1, 0, 1])


class FakeWFDB:
    def __init__(self):
        rng = np.random.default_rng(3)
        psi = rng.normal(size=(2, 1, 3, 2, 7)) + 1j * rng.normal(size=(2, 1, 3, 2, 7))   # (k, spin, band, spinor, G)
        self.wf = psi
        self.nspin, self.nspinor = 1, 2
        self.ydb = FakeLattice()


def test_spin_matrix_elements_as_a_direct_sum():
    """Same as summing over the plane waves at each k-point of the full grid, with the rotated operator."""
    from yambopy.dbs.wfdb import su2_mat
    wfdb = FakeWFDB()
    operator = spin_operator((0.3, -0.2, 0.9))
    result = spin_matrix_elements(wfdb, operator)
    assert result.shape == (4, 3, 3)
    for k in range(4):
        su2 = su2_mat(FakeLattice.sym_car[FakeLattice.symmetry_indexes[k]], False)
        rotated = su2.conj().T @ operator @ su2
        psi = wfdb.wf[FakeLattice.kpoints_indexes[k], 0]                       # (band, spinor, G)
        direct = np.einsum('mag,ab,nbg->mn', psi.conj(), rotated, psi)
        assert np.allclose(result[k], direct)
    with pytest.raises(ValueError):
        wfdb.nspinor = 1
        spin_matrix_elements(wfdb, operator)
