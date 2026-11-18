"""Tests of yambopy_ext.bse.exciton_particle_density (no Qt: meant to move to YamboPy with the module)."""

import itertools

import numpy as np
import pytest
from yambopy.dbs.wfdb import YamboWFDB
from yambopy.kpoints import build_ktree

from visual_excitons.yambopy_ext.bse.exciton_particle_density import (particle_nto, select_nto, wavefunction_grid,
                                                                       exciton_particle_density, density_maxima)

NV, NC = 2, 2


class FakeLatticeDB:
    """A 2 x 2 x 1 k-point grid of an orthorhombic cell, no symmetries (each k-point its own)."""
    lat = np.diag([4.0, 5.0, 6.0])
    kpoints_indexes = np.arange(4)
    symmetry_indexes = np.zeros(4, dtype=int)
    sym_car = np.eye(3)[None]
    time_rev = 0


class FakeWFDB:
    """
    What exciton_particle_density reads of a YamboWFDB: the bands (2 valence,
    2 conduction) at each k-point, with orthonormal coefficients on the
    plane waves G in [-1, 1]^3.
    """
    to_real_space = YamboWFDB.to_real_space

    def __init__(self, seed=0):
        self.ydb = FakeLatticeDB()
        self.kBZ = np.array([[0, 0, 0], [0.5, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0]], dtype=float)
        self.kpts_iBZ = self.kBZ
        self.ktree = build_ktree(self.kBZ)
        g = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
        self.gvecs = np.repeat(g[None], 4, axis=0)
        self.ngvecs = np.full(4, len(g))
        self.min_bnd, self.nbands, self.nspinor = 0, NV + NC, 1
        rng = np.random.default_rng(seed)
        self.wf = np.zeros((4, 1, self.nbands, 1, len(g)), dtype=complex)
        for k in range(4):
            q, _ = np.linalg.qr(rng.normal(size=(len(g), self.nbands)) + 1j * rng.normal(size=(len(g), self.nbands)))
            self.wf[k, 0, :, 0, :] = q.T                       # orthonormal bands

    def get_iBZ_wf(self, ik):
        return [self.wf[ik][..., :self.ngvecs[ik]], self.gvecs[ik, :self.ngvecs[ik], :]]

    def get_iBZ_kpt(self, ik):
        return self.kBZ[ik]


def coefficients(nstates=2, seed=1):
    """Normalised Akcv of `nstates` states, shape (nstates, 1, 1, nk, nc, nv)."""
    rng = np.random.default_rng(seed)
    A = rng.normal(size=(nstates, 1, 1, 4, NC, NV)) + 1j * rng.normal(size=(nstates, 1, 1, 4, NC, NV))
    return A / np.linalg.norm(A.reshape(nstates, -1), axis=1)[:, None, None, None, None, None]


def bloch(wfdb, k, band, points):
    """psi_band,k at `points` (crystal), the plane-wave sum (no volume factor)."""
    g = wfdb.gvecs[k]
    return np.exp(2j * np.pi * points @ (g + wfdb.kBZ[k]).T) @ wfdb.wf[k, 0, band, 0]


def byDefinition(wfdb, Akcv, Qpt, particle, box):
    """rho_h = sum_kc |sum_v A psi*_v,k-Q|^2, rho_e = sum_kv |sum_c A psi_ck|^2, summed over the states."""
    points = np.array(list(itertools.product(*(np.arange(n) / n for n in box))))
    rho = np.zeros(len(points))
    for A in Akcv[:, 0, 0]:                                     # (nk, nc, nv)
        for k in range(4):
            d = (wfdb.kBZ - (wfdb.kBZ[k] - Qpt)) % 1.0
            kh = int(np.argmin(np.linalg.norm(np.minimum(d, 1 - d), axis=1)))     # the hole's k-point: k - Q
            valence = np.array([bloch(wfdb, kh, v, points) for v in range(NV)])
            conduction = np.array([bloch(wfdb, k, NV + c, points) for c in range(NC)])
            if particle == 'h':
                rho += np.sum(np.abs(A[k] @ valence.conj()) ** 2, axis=0)
            else:
                rho += np.sum(np.abs(A[k].T @ conduction) ** 2, axis=0)
    return rho.reshape(tuple(box))


@pytest.mark.parametrize('particle', ['h', 'e'])
@pytest.mark.parametrize('Qpt', [(0, 0, 0), (0.5, 0, 0)])
def test_density_is_the_integral_over_the_other_particle(particle, Qpt):
    wfdb, Akcv = FakeWFDB(), coefficients()
    rho, info = exciton_particle_density(Akcv, np.array(Qpt, float), wfdb, [1, NV + NC], particle, fraction=1.0)
    assert tuple(info['fft_box']) == rho.shape == (5, 5, 5)
    np.testing.assert_allclose(rho, byDefinition(wfdb, Akcv, np.array(Qpt, float), particle, rho.shape),
                               rtol=1e-9, atol=1e-12)
    # Orthonormal bands: the average over the cell is the number of states
    assert rho.mean() == pytest.approx(2.0) and info['weight'] == pytest.approx(2.0)


def test_ntos_of_a_group_are_those_of_its_states_summed():
    Akcv = coefficients(3)
    for particle in ('h', 'e'):
        weights, vectors = particle_nto(Akcv, particle)
        assert weights.shape == (1, 4, NV if particle == 'h' else NC) and weights.sum() == pytest.approx(3.0)
        wfdb = FakeWFDB()
        group = exciton_particle_density(Akcv, np.zeros(3), wfdb, [1, 4], particle, fraction=1.0)[0]
        each = sum(exciton_particle_density(Akcv[[n]], np.zeros(3), wfdb, [1, 4], particle, fraction=1.0)[0]
                   for n in range(3))
        np.testing.assert_allclose(group, each, rtol=1e-10)


def test_truncation_drops_exactly_the_weight_left_out():
    wfdb, Akcv = FakeWFDB(), coefficients(1)
    full = exciton_particle_density(Akcv, np.zeros(3), wfdb, [1, 4], 'h', fraction=1.0)[0]
    part, info = exciton_particle_density(Akcv, np.zeros(3), wfdb, [1, 4], 'h', fraction=0.8)
    assert 0.8 <= info['weight_kept'] < 1.0 and info['nto'] < 8
    assert part.mean() == pytest.approx(info['weight_kept'])               # orthonormal: the weight itself
    assert np.all(part <= full + 1e-12)                                    # a positive part dropped
    weights = np.array([0.5, 0.3, 0.15, 0.05])
    assert select_nto(weights, 0.8).tolist() == [True, True, False, False]
    assert select_nto(weights, 1.0).all()


def test_maxima_across_the_faces_of_the_cell():
    density = np.zeros((6, 6, 6))
    density[0, 0, 0], density[5, 0, 0] = 1.0, 0.9      # neighbours through the face: only the first is a maximum
    density[3, 3, 3] = 0.5
    density[2, 4, 1] = 0.05                             # below the threshold
    indices, values = density_maxima(density, threshold=0.1)
    assert indices.tolist() == [[0, 0, 0], [3, 3, 3]] and values.tolist() == [1.0, 0.5]


def test_cutoff_selects_the_plane_waves_of_ex_wf2Real():
    wfdb = FakeWFDB()
    idx, box = wavefunction_grid(wfdb, -1)
    assert all(len(i) == 27 for i in idx) and box.tolist() == [5, 5, 5]
    # |k + G| (2 pi / a) < sqrt(cutoff): at Gamma, G = 0 and the six shortest along x, y, z need different cutoffs
    lengths = 2 * np.pi * np.linalg.norm((wfdb.gvecs[0]) @ np.linalg.inv(wfdb.ydb.lat.T), axis=-1)
    cutoff = (np.sort(lengths)[1] + 1e-9) ** 2
    idx, box = wavefunction_grid(wfdb, cutoff)
    assert len(idx[0]) == 3                              # G = 0 and +-1 along the longest axis (c = 6)


def test_only_tamm_dancoff():
    with pytest.raises(ValueError, match='Tamm-Dancoff'):
        particle_nto(np.zeros((1, 2, 1, 4, NC, NV)))
