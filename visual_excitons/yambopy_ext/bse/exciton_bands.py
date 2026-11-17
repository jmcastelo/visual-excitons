"""
exciton_bands.py
================
The excitonic band structure at any momentum Q: the electronic bands along
a path, each with the weight of the exciton on it ("fat bands"), the hole's
on the valence bands and the electron's on the conduction bands.

At a finite Q, yambo's transitions take the hole from the valence band at
k-Q to the conduction band at k (see :mod:`exciton_kspace`). So the weight
on a valence band at k is that of the hole at k (transitions whose electron
is at k+Q), and on a conduction band at k that of the electron at k. At
Q = 0 both are at the same k.

How each part is interpolated along the path (the reasons are in the notes
of each function):

* energies: SKW (``yambopy.tools.skw``) on the irreducible k-points, with
  the crystal's symmetries (energies have them all), as YamboPy does;
* weights: linearly on the full k-point grid, periodic, with no symmetry.
  At a finite Q the weights only have the symmetry of the little group of Q
  (and a single state of a degenerate group not even that): folding them
  into the irreducible wedge, as ``YamboExcitonDB.interpolate`` does, is
  wrong. SKW without symmetries on the full grid is right but costly (it
  takes minutes for a 72x72 grid) and, being a Fourier fit of peaked data,
  rings into small negative weights; linear interpolation is exact at the
  grid points, never negative and costs nothing.

* :func:`band_kpoint_weights` — the weight on each band at each k-point;
* :func:`interpolate_on_grid` — periodic multilinear interpolation of
  values on a regular grid at any points;
* :func:`band_energies_ibz` — DFT or QP energies of the bands of the BSE;
* :func:`interpolate_energies` — SKW interpolation of energies with symmetries;
* :func:`interpolate_exciton_bands` — the band structure of states of a
  ``YamboExcitonDB`` along a path.

Meant for ``yambopy.bse`` / ``YamboExcitonDB``: a replacement of
``interpolate`` (Γ only, symmetric weights; its QP energies are taken from
the first columns of the QP database whatever its band range, which shifts
them by a band when the ranges differ) and of ``get_exciton_weights``.
Bands and states 1-based, as in yambo; energies in eV.
"""

import itertools

import numpy as np

from yambopy.lattice import car_red
from yambopy.tools.skw import SkwInterpolator

from .exciton_kspace import state_weights, kpoint_grid, hole_kpoint_indices

__all__ = ['band_kpoint_weights', 'interpolate_on_grid', 'band_energies_ibz', 'interpolate_energies',
           'interpolate_exciton_bands']


def band_kpoint_weights(table, weights, nkpoints, first_band, last_band, hole_indices=None):
    """
    The weight of the exciton on each band at each k-point: the electron's
    on the conduction bands, the hole's on the valence bands.

    Parameters
    ----------
    table : ndarray (nt, >=3), yambo's BSE table: k (the electron's), v, c, 1-based
    weights : ndarray (nt,), the weight of each transition
    nkpoints : int, the k-points of the full grid
    first_band, last_band : the bands of the result (1-based, inclusive)
    hole_indices : ndarray (nk,), the index of k-Q for each k; None at Q = 0

    Returns
    -------
    ndarray (nkpoints, last_band - first_band + 1)
    """
    table = np.asarray(table)
    k = table[:, 0].astype(int) - 1
    v, c = table[:, 1].astype(int), table[:, 2].astype(int)
    result = np.zeros((nkpoints, last_band - first_band + 1))
    np.add.at(result, (k, c - first_band), weights)
    holes = k if hole_indices is None else np.asarray(hole_indices)[k]
    np.add.at(result, (holes, v - first_band), weights)
    return result


def interpolate_on_grid(red_kpoints, values, red_points, grid=None):
    """
    Values given on a regular grid of the Brillouin zone, at other points:
    multilinear interpolation, periodic (points in reduced coordinates, any
    cell). Exact at the grid points; between them, a weighted average of the
    corners of the grid cell, so never outside the range of the values.

    Parameters
    ----------
    red_kpoints : ndarray (nk, 3), the full grid (any order)
    values : ndarray (nk, ...), the values at the grid points
    red_points : ndarray (np, 3), where to interpolate
    grid : the points along each axis (found from *red_kpoints* if None)

    Returns
    -------
    ndarray (np, ...)
    """
    red = np.asarray(red_kpoints, dtype=float)
    values = np.asarray(values, dtype=float)
    grid = np.asarray(kpoint_grid(red) if grid is None else grid, dtype=int)
    # The values on the grid, by grid indices
    indices = np.round((red % 1.0) * grid).astype(int) % grid
    table = np.full(tuple(grid) + values.shape[1:], np.nan)
    table[tuple(indices.T)] = values
    if np.isnan(table).any():
        raise ValueError('The k-points do not fill a regular grid.')

    scaled = (np.asarray(red_points, dtype=float) % 1.0) * grid
    base = np.floor(scaled).astype(int)
    frac = scaled - base
    result = np.zeros((len(scaled),) + values.shape[1:])
    for corner in itertools.product((0, 1), repeat=3):
        corner = np.array(corner)
        factor = np.prod(np.where(corner, frac, 1.0 - frac), axis=1)
        idx = (base + corner) % grid
        result += factor.reshape((-1,) + (1,) * (values.ndim - 1)) * table[tuple(idx.T)]
    return result


def band_energies_ibz(dft_ibz, first_band, last_band, qp=None):
    """
    The energies of bands *first_band* to *last_band* (1-based) on the
    irreducible k-points: DFT, or QP if *qp* (from
    ``yambopy_ext.dbs.qp_energies.qp_energies``) is given.

    QP energies keep the QP database's energy zero. A band outside the range
    of the QP database gets its DFT energy (moved to that zero) corrected as
    the nearest band of the database at the same k-point, a scissor-like
    estimate.

    Parameters
    ----------
    dft_ibz : ndarray (nk, nbands), DFT energies (e.g. ``YamboElectronsDB.eigenvalues_ibz[0]``), bands from 1

    Returns
    -------
    energies : ndarray (nk, nb)
    estimated : list of the bands whose QP energies are estimated (outside the QP range)
    """
    dft_ibz = np.asarray(dft_ibz, dtype=float)
    dft = dft_ibz[:, first_band - 1:last_band]
    if qp is None:
        return dft, []
    lo, hi = qp['min_band'], qp['max_band']
    if qp['qp'].shape[0] != dft_ibz.shape[0]:
        raise ValueError(f'The QP database has {qp["qp"].shape[0]} k-points, the SAVE database {dft_ibz.shape[0]}.')
    # The difference of energy zeros between the SAVE and the QP database (one number)
    overlap = slice(lo - 1, min(hi, dft_ibz.shape[1]))
    offset = float(np.nanmean(dft_ibz[:, overlap] - qp['dft'][:, :overlap.stop - overlap.start]))
    correction = qp['qp'] - qp['dft']
    energies, estimated = np.empty_like(dft), []
    for column, band in enumerate(range(first_band, last_band + 1)):
        if lo <= band <= hi:
            energies[:, column] = qp['qp'][:, band - lo]
        else:
            nearest = min(max(band, lo), hi)
            energies[:, column] = dft[:, column] - offset + correction[:, nearest - lo]
            estimated.append(band)
    if np.isnan(energies).any():
        raise ValueError('The QP database does not have every band at every k-point.')
    return energies, estimated


def interpolate_energies(lattice, energies_ibz, red_points, lpratio=5):
    """
    SKW interpolation of energies on the irreducible k-points of *lattice*
    (a ``YamboLatticeDB``), with the crystal's symmetries, at *red_points*
    (reduced coordinates): ndarray (np, nb). As ``YamboExcitonDB.interpolate``
    does for the energies.
    """
    kpoints = car_red(np.array([k / lattice.alat for k in lattice.ibz_kpoints]), lattice.rlat)
    # skw wants the symmetries of the direct lattice: those of the reciprocal one, without time reversal
    symrel = [sym for sym, trev in zip(lattice.sym_rec_red, lattice.time_rev_list) if not trev]
    cell = (lattice.lat, lattice.red_atomic_positions, lattice.atomic_numbers)
    skw = SkwInterpolator(lpratio, kpoints, np.asarray(energies_ibz, dtype=float)[None], 0, 0, cell, symrel,
                          bool(lattice.time_rev), verbose=0)
    return skw.interp_kpts(np.asarray(red_points, dtype=float)).eigens[0]


def interpolate_exciton_bands(excdb, red_path, states, energies_ibz, degenerate=True, degen_eps=1e-2,
                              degen_rtol=1e-3, lpratio=5):
    """
    The excitonic band structure of *states* (1-based) of *excdb* along a path.

    Parameters
    ----------
    excdb : ``YamboExcitonDB`` loaded with its eigenvectors (any Q)
    red_path : ndarray (np, 3), the path (reduced coordinates of ``excdb.lattice``)
    states : the states whose weights are shown (summed, divided by their number)
    energies_ibz : ndarray (nk_ibz, nb), the energies of the bands of the BSE
        (``excdb.start_band + 1`` to ``excdb.mband``) on the irreducible k-points
        (see :func:`band_energies_ibz`)
    degenerate : add the states degenerate with each of *states*

    Returns
    -------
    dict with
        ``energies``, ``weights`` : ndarray (np, nb), along the path
        ``bands`` : (first, last), the bands (1-based)
        ``states`` : the states summed
        ``red_qpoint`` : Q, reduced
        ``nvbands`` : the valence bands among them
    """
    if excdb.eigenvectors is None:
        raise ValueError('The database has no eigenvectors: load it with Load_WF=True (and run yambo with WRbsWF).')
    states = sorted({int(s) for s in states})
    if degenerate:
        states = sorted({d for s in states for d in excdb.get_degenerate(s, eps=degen_eps, rtol=degen_rtol)
                         if d <= len(excdb.eigenvectors)})
    lattice = excdb.lattice
    first, last = int(excdb.start_band) + 1, int(excdb.mband)
    red_kpoints = np.asarray(lattice.red_kpoints, dtype=float)

    car_qpoint = np.zeros(3) if excdb.car_qpoint is None else np.asarray(excdb.car_qpoint, dtype=float)
    red_qpoint = np.linalg.solve(np.asarray(lattice.rlat, dtype=float).T, car_qpoint)
    gamma = np.allclose(red_qpoint - np.round(red_qpoint), 0.0, atol=1e-6)
    holes = None if gamma else hole_kpoint_indices(red_kpoints, red_qpoint)

    weights = band_kpoint_weights(excdb.table, state_weights(excdb.eigenvectors, states), len(red_kpoints),
                                  first, last, holes)
    return {'energies': interpolate_energies(lattice, energies_ibz, red_path, lpratio),
            'weights': interpolate_on_grid(red_kpoints, weights, red_path),
            'bands': (first, last), 'states': states, 'red_qpoint': red_qpoint,
            'nvbands': int(len(np.unique(np.asarray(excdb.table)[:, 1])))}
