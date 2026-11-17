"""Tests of yambopy_ext.bse.exciton_kspace (no Qt: meant to move to YamboPy with the module)."""

import numpy as np
import pytest

from visual_excitons.yambopy_ext.bse.exciton_kspace import (state_weights, hole_kpoint_indices, kpoint_weights,
                                                            band_pair_weights, band_weights, exciton_kspace)


class FakeLattice:
    """A 2 x 2 x 1 grid of a square lattice (Bohr, reciprocal without 2π)."""
    lat = np.diag([4.0, 4.0, 20.0])
    rlat = np.linalg.inv(lat).T
    red_kpoints = np.array([[0, 0, 0], [0.5, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0]], dtype=float)


class FakeExcitonDB:
    """What exciton_kspace reads of a YamboExcitonDB: table (k, v, c), eigenvectors, energies, Q."""

    def __init__(self, red_qpoint=(0, 0, 0)):
        self.lattice = FakeLattice()
        # Transitions: k = 1..4, valence bands 3, 4, conduction band 5
        self.table = np.array([[k, v, 5, 1, 1] for k in range(1, 5) for v in (3, 4)])
        rng = np.random.default_rng(0)
        vectors = rng.normal(size=(3, 8)) + 1j * rng.normal(size=(3, 8))
        self.eigenvectors = vectors / np.linalg.norm(vectors, axis=1)[:, None]
        self.eigenvalues = np.array([1.0, 1.5, 1.5]) + 0j
        self.car_qpoint = np.asarray(red_qpoint, dtype=float) @ self.lattice.rlat

    def get_degenerate(self, index, eps=1e-4, rtol=1e-3):
        energy = self.eigenvalues[index - 1].real
        return (np.where(np.isclose(self.eigenvalues.real, energy, atol=eps, rtol=rtol))[0] + 1).tolist()


def test_weights_of_a_degenerate_group_add_up_to_one():
    db = FakeExcitonDB()
    assert state_weights(db.eigenvectors, [1]).sum() == pytest.approx(1.0)
    group = state_weights(db.eigenvectors, [2, 3])
    assert group.sum() == pytest.approx(1.0)
    # Independent of the basis of the group: a rotation of states 2 and 3
    a, b = db.eigenvectors[1], db.eigenvectors[2]
    rotated = np.array([db.eigenvectors[0], (a + b) / np.sqrt(2), (a - b) / np.sqrt(2)])
    assert np.allclose(state_weights(rotated, [2, 3]), group)
    with pytest.raises(ValueError):
        state_weights(db.eigenvectors, [0])


def test_hole_at_k_minus_q():
    red = FakeLattice.red_kpoints
    assert hole_kpoint_indices(red, [0, 0, 0]).tolist() == [0, 1, 2, 3]
    assert hole_kpoint_indices(red, [0.5, 0, 0]).tolist() == [1, 0, 3, 2]
    with pytest.raises(ValueError):
        hole_kpoint_indices(red, [0.25, 0, 0])                 # not a vector of the grid


def test_kpoint_and_band_weights():
    db = FakeExcitonDB()
    weights = state_weights(db.eigenvectors, [1])
    electron, hole = kpoint_weights(db.table, weights, 4)
    assert np.allclose(electron, hole) and electron.sum() == pytest.approx(1.0)
    assert np.allclose(electron, [weights[2 * k] + weights[2 * k + 1] for k in range(4)])
    pairs = band_pair_weights(db.table, weights)
    assert [p[:2] for p in pairs] in ([(3, 5), (4, 5)], [(4, 5), (3, 5)])
    assert pairs[0][2] >= pairs[1][2] and sum(p[2] for p in pairs) == pytest.approx(1.0)
    valence, conduction = band_weights(db.table, weights)
    assert conduction == {5: pytest.approx(1.0)} and sum(valence.values()) == pytest.approx(1.0)


def test_exciton_kspace_at_finite_q():
    db = FakeExcitonDB(red_qpoint=(0.5, 0, 0))
    result = exciton_kspace(db, 1)
    assert result['states'] == [1] and np.allclose(result['red_qpoint'], [0.5, 0, 0])
    # The hole at k - Q: the electron's weights moved by Q
    assert np.allclose(result['hole'], result['electron'][[1, 0, 3, 2]])
    # A degenerate state brings its partner
    assert exciton_kspace(db, 2)['states'] == [2, 3] and exciton_kspace(db, 2, degenerate=False)['states'] == [2]
    with pytest.raises(ValueError):
        exciton_kspace(db, 4)
