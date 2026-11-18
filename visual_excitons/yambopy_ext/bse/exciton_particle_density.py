"""
exciton_particle_density.py
===========================
The own density of the hole or of the electron of an exciton: where that
particle is, wherever the other one is. It tells where to fix a particle
when computing the real-space wave function of an exciton.

With the exciton wave function (Tamm-Dancoff, momentum Q; the convention of
``yambopy.bse.realSpace_excitonwf.ex_wf2Real``)

    Psi(r_e, r_h) = sum_kcv A_kcv psi_ck(r_e) psi*_v,k-Q(r_h),

the density of the hole is the integral of |Psi|^2 over the electron, which
the orthonormality of the Bloch functions does exactly:

    rho_h(r_h) = sum_k sum_c | sum_v A_kcv psi*_v,k-Q(r_h) |^2,

and that of the electron, the same with the roles swapped:

    rho_e(r_e) = sum_k sum_v | sum_c A_kcv psi_ck(r_e) |^2.

They are periodic with the lattice, so a unit cell holds them. And the total
weight of the wave function computed with the hole fixed at r_0 (what
``ex_wf2Real`` gives, before any normalisation) is rho_h(r_0): with the hole
where rho_h is small, the electron's map is weak, and noisy once normalised.
For bands of p or d character it vanishes at the nuclei: fixing a particle on
an atom can put it on a node.

Natural transition orbitals (NTOs) make it cheap: at each k, with M_k the
sum over the states of A_k^+ A_k (v x v) for the hole, or of conj(A_k) A_k^T
(c x c) for the electron, of eigenvalues l_kj and eigenvectors W_k,

    rho_h(r) = sum_k sum_j l_kj | sum_v conj(W_vj) psi*_v,k-Q(r) |^2,

with at most min(n_c, n_v) NTOs per k (per state) instead of n_v or n_c
bands, exact for a group of degenerate states summed. Their weights add up
to the number of states; dropping the smallest, of total weight w, drops a
density that integrates to exactly w.

The density is computed on the grid ``ex_wf2Real`` uses for the wave
function at the same cutoff, with the same plane waves: a point of it, as a
fixed position, is used as it is (``ex_wf2Real`` moves the fixed particle to
the nearest point of that grid), and the density is the one consistent with
that calculation (the cutoff changes its details).

* :func:`particle_nto` — the NTOs of the hole or of the electron at each k;
* :func:`wavefunction_grid` — the plane waves and grid of ``ex_wf2Real``;
* :func:`exciton_particle_density` — the density on that grid;
* :func:`density_maxima` — its local maxima (periodic).

Meant for ``yambopy.bse`` (next to ``realSpace_excitonwf``): YamboPy has no
particle density of an exciton. TDA only (the anti-resonant part of
``ex_wf2Real`` is not included).
"""

import numpy as np
from scipy.ndimage import maximum_filter

from yambopy.kpoints import find_kpt

__all__ = ['particle_nto', 'select_nto', 'wavefunction_grid', 'exciton_particle_density', 'density_maxima']


def _resonant(Akcv):
    """The resonant part of ``YamboExcitonDB.get_Akcv()`` coefficients: (nstates, nspin, nk, nc, nv)."""
    Akcv = np.asarray(Akcv)
    if Akcv.ndim == 6:
        if Akcv.shape[1] != 1:
            raise ValueError('Only Tamm-Dancoff coefficients are supported (no anti-resonant part)')
        Akcv = Akcv[:, 0]
    if Akcv.ndim != 5:
        raise ValueError('Akcv must have the shape (nstates, [1,] nspin, nk, nc, nv)')
    return Akcv


def particle_nto(Akcv, particle='h'):
    """
    The natural transition orbitals of the hole or of the electron at each k.

    Parameters
    ----------
    Akcv : array
        Coefficients of the states, as ``YamboExcitonDB.get_Akcv()`` gives
        them, shape (nstates, 1, nspin, nk, nc, nv) or without the second axis.
        Several states are summed (their densities add).
    particle : {'h', 'e'}
        The hole (combinations of valence bands) or the electron (of
        conduction bands).

    Returns
    -------
    weights : ndarray, shape (nspin, nk, nb)
        Weight of each NTO (>= 0), nb = nv for the hole, nc for the electron.
        They add up to the number of states.
    vectors : ndarray, shape (nspin, nk, nb, nb)
        ``vectors[s, k, :, j]``: NTO j as a combination of the bands. The
        orbital is ``sum_b conj(vectors[s, k, b, j]) * f_b`` with ``f_b`` the
        band functions as :func:`exciton_particle_density` takes them (the
        hole's conjugated).
    """
    A = _resonant(Akcv)
    if particle == 'h':
        M = np.einsum('nskcv,nskcw->skvw', A.conj(), A)
    elif particle == 'e':
        M = np.einsum('nskcv,nskdv->skcd', A.conj(), A)
    else:
        raise ValueError("particle must be 'h' or 'e'")
    weights, vectors = np.linalg.eigh(M)
    return np.clip(weights, 0.0, None), vectors


def select_nto(weights, fraction=0.999):
    """
    The NTOs to keep for `fraction` of the total weight, the largest first: a
    boolean mask of the shape of `weights`. Those dropped weigh at most
    1 - `fraction` of the total, which is what their density integrates to.
    """
    weights = np.asarray(weights)
    if fraction >= 1:
        return weights > 0
    flat = np.sort(weights.ravel())[::-1]
    total = np.cumsum(flat)
    smallest = flat[min(int(np.searchsorted(total, fraction * total[-1])), len(flat) - 1)]
    return (weights >= smallest) & (weights > 0)


def wavefunction_grid(wfcdb, wfcCutoffRy=-1):
    """
    The plane waves and the real-space grid ``ex_wf2Real`` uses at the cutoff
    `wfcCutoffRy` (Ry; -1: all of them).

    Returns
    -------
    gvecs_idx : list of ndarray
        For each irreducible k-point, the indices of its plane waves kept.
    fft_box : ndarray, shape (3,)
        Points of the grid along each lattice vector, in the unit cell.
    """
    blat = np.linalg.inv(wfcdb.ydb.lat.T)
    gvecs_idx, fft_box = [], np.zeros(3, dtype=int)
    for ik in range(len(wfcdb.gvecs)):
        idx = np.arange(wfcdb.ngvecs[ik], dtype=int)
        gvecs = wfcdb.gvecs[ik, :wfcdb.ngvecs[ik], :]
        if wfcCutoffRy > 0:
            norms = 2 * np.pi * np.linalg.norm((gvecs + wfcdb.kpts_iBZ[ik][None, :]) @ blat, axis=-1)
            idx = idx[norms < np.sqrt(wfcCutoffRy)]
        gvecs_idx.append(idx)
        kept = gvecs[idx]
        fft_box = np.maximum(fft_box, kept.max(axis=0) - kept.min(axis=0) + 3)
    return gvecs_idx, fft_box


def _bloch_coefficients(wfcdb, ik_bz, bands, gvecs_idx):
    """
    The plane-wave coefficients of `bands` at the full-BZ k-point `ik_bz`
    (rotated from the irreducible one as ``ex_wf2Real`` does), its G-vectors
    and k (crystal coordinates).
    """
    ik_ibz = wfcdb.ydb.kpoints_indexes[ik_bz]
    isym = wfcdb.ydb.symmetry_indexes[ik_bz]
    wfc, gvecs = wfcdb.get_iBZ_wf(ik_ibz)
    wfc = wfc[:, bands[0]:bands[1], :, gvecs_idx[ik_ibz]]
    gvecs = gvecs[gvecs_idx[ik_ibz]]
    kvec = wfcdb.get_iBZ_kpt(ik_ibz)
    if isym != 0:
        sym_mat = wfcdb.ydb.sym_car[isym]
        time_rev = (isym >= len(wfcdb.ydb.sym_car) / (1 + int(np.rint(wfcdb.ydb.time_rev))))
        kvec, wfc, gvecs = wfcdb.apply_symm(kvec, wfc, gvecs, time_rev, sym_mat)
    return wfc, gvecs, kvec


def exciton_particle_density(Akcv, Qpt, wfcdb, bse_bnds, particle='h', wfcCutoffRy=-1, fraction=0.999,
                             progress=None):
    """
    The density of the hole or of the electron of an exciton (or of a group
    of states, summed) on the unit-cell grid of ``ex_wf2Real``.

    Parameters
    ----------
    Akcv : array
        ``YamboExcitonDB.get_Akcv()`` of the states (see :func:`particle_nto`).
    Qpt : array, shape (3,)
        Q-point of the exciton, crystal coordinates (as for ``ex_wf2Real``).
    wfcdb : YamboWFDB
        Wave functions of the bands of the BSE.
    bse_bnds : sequence of 2 int
        BSE band range [nb1, nb2], 1-based as in yambo's input (as for
        ``ex_wf2Real``).
    particle : {'h', 'e'}
        The hole or the electron.
    wfcCutoffRy : float
        Plane-wave cutoff (Ry), that of the wave function to be computed; -1:
        all plane waves.
    fraction : float
        Share of the NTO weight kept (1: all, exact).
    progress : callable, optional
        Called with no arguments after each k-point (e.g. to report progress
        or to stop: an exception it raises stops the calculation).

    Returns
    -------
    density : ndarray, shape fft_box
        The density at the points ``(i, j, k) / fft_box`` (crystal
        coordinates). Its average over the cell is the weight kept times the
        norm of the band functions within the cutoff (1 at full cutoff): the
        number of states at most.
    info : dict
        ``fft_box``, ``weight`` (the total NTO weight: the number of states),
        ``weight_kept``, ``nto`` (NTOs used) and ``kpoints`` (k-points used).
    """
    weights, vectors = particle_nto(Akcv, particle)
    keep = select_nto(weights, fraction)
    nspin, nk, nb = weights.shape
    A = _resonant(Akcv)
    nc, nv = A.shape[-2:]
    first = min(bse_bnds) - 1 - wfcdb.min_bnd
    hole_bnds, elec_bnds = [first, first + nv], [first + nv, first + nv + nc]
    if first < 0 or elec_bnds[1] > wfcdb.nbands:
        raise ValueError('The bands of the BSE are not all in the wave-function database')
    if len(wfcdb.ydb.symmetry_indexes) != nk:
        raise ValueError('The coefficients and the wave functions have different k-points')
    gvecs_idx, fft_box = wavefunction_grid(wfcdb, wfcCutoffRy)
    volume = abs(np.linalg.det(wfcdb.ydb.lat))
    Qpt = np.asarray(Qpt, dtype=float)

    density = np.zeros(tuple(fft_box))
    used = set()
    for ik in range(nk):
        if keep[:, ik].any():
            if particle == 'e':
                wfc, gvecs, kvec = _bloch_coefficients(wfcdb, ik, elec_bnds, gvecs_idx)
            else:
                kelec = _bloch_coefficients(wfcdb, ik, [elec_bnds[0], elec_bnds[0] + 1], gvecs_idx)[2]
                ikh = find_kpt(wfcdb.ktree, kelec - Qpt)
                wfc, gvecs, _ = _bloch_coefficients(wfcdb, ikh, hole_bnds, gvecs_idx)
                wfc, gvecs = wfc.conj(), -gvecs
            for s in range(nspin):
                j = keep[s, ik]
                if not j.any():
                    continue
                combination = vectors[s, ik][:, j].conj() * np.sqrt(weights[s, ik, j])[None, :]
                orbitals = np.einsum('bj,byg->jyg', combination, wfc[s])
                n, nspinor, ng = orbitals.shape
                real = wfcdb.to_real_space(orbitals.reshape(-1, nspinor, ng), gvecs, grid=fft_box)
                # to_real_space divides by sqrt(volume): the densities are per unit-cell volume as the
                # coefficients are normalised (the e^{ik.r} phase cancels in |.|^2)
                density += np.sum(np.abs(real) ** 2, axis=(0, 1)) * volume
            used.add(ik)
        if progress is not None:
            progress()
    info = {'fft_box': fft_box, 'weight': float(weights.sum()), 'weight_kept': float(weights[keep].sum()),
            'nto': int(keep.sum()), 'kpoints': len(used)}
    return density, info


def density_maxima(density, threshold=0.1):
    """
    The local maxima of a periodic density on a grid (each point compared with
    its 26 neighbours, across the cell's faces too), of at least `threshold`
    times the largest value, the largest first.

    Returns
    -------
    indices : ndarray, shape (n, 3)
        Grid indices of the maxima.
    values : ndarray, shape (n,)
    """
    density = np.asarray(density)
    peaks = np.argwhere((density == maximum_filter(density, size=3, mode='wrap'))
                        & (density >= threshold * density.max()))
    values = density[tuple(peaks.T)]
    order = np.argsort(-values, kind='stable')
    return peaks[order], values[order]
