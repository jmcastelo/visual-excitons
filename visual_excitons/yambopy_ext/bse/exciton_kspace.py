"""
exciton_kspace.py
=================
Where an exciton lives in reciprocal space, and what it is made of: the
weights of its transitions |A_kvc|^2 summed by k-point, for the electron and
the hole apart, and by band and band pair.

At a finite momentum Q, yambo's transitions take a hole from the valence
band at k-Q to the conduction band at k (the k of the BSE table is the
electron's). So the electron's weights are at k and the hole's at k-Q: at
Q = 0 they coincide. This is what an excitonic band structure at finite Q
needs (the hole on the valence bands at k-Q, the electron on the conduction
bands at k).

* :func:`summed_states` — the states summed for a state: itself, the states
  degenerate with it, or all those in an energy window around it, each with
  its share (equal, or by oscillator strength, as an absorption peak made of
  many close states);
* :func:`state_weights` — |A|^2 of each transition for a state or a group of
  states (normalised to 1);
* :func:`hole_kpoint_indices` — for each k of the grid, the index of k-Q;
* :func:`kpoint_weights` — the electron's and the hole's weight at each k;
* :func:`band_pair_weights`, :func:`band_weights` — by valence-conduction
  pair, and by band;
* :func:`exciton_kspace` — all of these for a state of a ``YamboExcitonDB``.

Meant for ``yambopy.bse`` / ``YamboExcitonDB``, as a replacement of
``get_exciton_weights`` (which adds the hole's weight at the electron's k,
right only at Q = 0) and ``get_exciton_transitions`` (which reads the
table's columns as (k, c, v) instead of (k, v, c), and keeps only the last
state of a group), vectorised instead of a Python loop over the transitions.
Bands and states are counted from 1, as in yambo's tables.
"""

import numpy as np

__all__ = ['summed_states', 'state_weights', 'kpoint_grid', 'hole_kpoint_indices', 'kpoint_weights', 'band_pair_weights', 'band_weights',
           'exciton_kspace']


# Below this share of the largest intensity of the whole database, a window
# has no bright state: its states are then weighted equally
DARK_INTENSITY = 1e-6


def summed_states(excdb, state, degenerate=True, degen_eps=1e-2, degen_rtol=1e-3, window=0.0, weighting='equal',
                  share_eps=1e-3):
    """
    The states summed for *state* (1-based) of a ``YamboExcitonDB``, and the
    share of each.

    * Alone, or with the states degenerate with it if *degenerate*
      (``excdb.get_degenerate``): a single state of a degenerate group is an
      arbitrary mixture of them.
    * With *window* > 0 (eV), also every state loaded whose energy is within
      *window* of that of *state*: an absorption peak made of many close
      states (e.g. the C and D peaks of transition-metal dichalcogenides).

    *weighting*: 'equal', or 'oscillator', each state in proportion to its
    intensity ``|l_residual * r_residual|``, as it contributes to the
    absorption; when none of them is bright (e.g. at a finite momentum, where
    the residuals vanish), equally. The states of a degenerate group (within
    *share_eps*, eV: degenerate by symmetry, not merely close) share its total
    intensity equally: each of them is an
    arbitrary mixture (e.g. of the K and K' excitons of a hexagonal layer),
    and its own intensity, for the field direction of the calculation, depends
    on that mixture, while the group's total does not.

    Returns
    -------
    states : list of int, 1-based, increasing
    shares : ndarray, their shares, adding up to 1
    weighting : 'equal' or 'oscillator', the weighting used
    """
    if not 1 <= state <= len(excdb.eigenvalues):
        raise ValueError(f'State {state} does not exist: the database has {len(excdb.eigenvalues)} states loaded.')
    energies = np.real(np.asarray(excdb.eigenvalues))
    states = {int(state)}
    if degenerate:
        states.update(int(s) for s in excdb.get_degenerate(state, eps=degen_eps, rtol=degen_rtol))
    if window and window > 0:
        inside = np.nonzero(np.abs(energies - energies[state - 1]) <= window + 1e-9)[0] + 1
        states.update(int(s) for s in inside)
    if excdb.eigenvectors is not None:
        states = {s for s in states if s <= len(excdb.eigenvectors)}
    states = sorted(states)
    shares = np.full(len(states), 1.0 / len(states))
    used = 'equal'
    if weighting == 'oscillator' and excdb.l_residual is not None and excdb.r_residual is not None:
        intensities = np.abs(np.asarray(excdb.l_residual) * np.asarray(excdb.r_residual))
        chosen = np.array([np.mean(intensities[np.array([g for g in excdb.get_degenerate(s, eps=share_eps,
                                                                                          rtol=0)
                                                         if g <= len(intensities)]) - 1])
                           for s in states])
        if intensities.size and chosen.sum() > DARK_INTENSITY * intensities.max():
            shares, used = chosen / chosen.sum(), 'oscillator'
    elif weighting not in ('equal', 'oscillator'):
        raise ValueError(f"Unknown weighting {weighting!r}: 'equal' or 'oscillator'.")
    return states, shares, used


def state_weights(eigenvectors, states, shares=None):
    """
    |A_t|^2 of each transition t, summed over *states* (1-based), each with
    its share in *shares* (equal by default: divided by their number), so
    that they add up to 1: the weights of a degenerate group, which do not
    depend on the basis chosen within it.
    """
    states = np.atleast_1d(np.asarray(states, dtype=int))
    if np.any(states < 1):
        raise ValueError('States are counted from 1.')
    shares = np.full(len(states), 1.0 / len(states)) if shares is None else np.asarray(shares, dtype=float)
    if shares.shape != states.shape:
        raise ValueError('One share per state.')
    vectors = np.asarray(eigenvectors)[states - 1]
    return np.tensordot(shares / shares.sum(), np.abs(vectors) ** 2, axes=1)


def kpoint_grid(red_kpoints, tol=1e-4):
    """The number of points along each axis of the regular grid *red_kpoints* (reduced coordinates)."""
    red = np.asarray(red_kpoints, dtype=float)
    grid = []
    for axis in range(3):
        values = np.unique(np.round(red[:, axis] % 1.0, 6) % 1.0)
        steps = np.diff(np.concatenate([values, [values[0] + 1.0]]))
        grid.append(1 if len(values) < 2 else int(round(1.0 / steps[steps > tol].min())))
    return grid


def hole_kpoint_indices(red_kpoints, red_qpoint, grid=None, tol=1e-4):
    """
    For each k of the grid *red_kpoints* (reduced coordinates), the index of
    k - *red_qpoint* in it (modulo reciprocal lattice vectors).

    *grid*, the number of points along each axis, is found from the points
    if not given. Raises ValueError if Q is not a vector of the grid.
    """
    red = np.asarray(red_kpoints, dtype=float)
    q = np.asarray(red_qpoint, dtype=float)
    grid = np.asarray(kpoint_grid(red, tol) if grid is None else grid, dtype=int)

    def keys(points):
        scaled = (points % 1.0) * grid
        rounded = np.round(scaled)
        if np.any(np.abs(scaled - rounded) > tol * np.max(grid)):
            raise ValueError('Point not on the grid (is Q a vector of the k-point grid?).')
        return [tuple(key) for key in (rounded.astype(int) % grid)]

    index = {key: i for i, key in enumerate(keys(red))}
    try:
        return np.array([index[key] for key in keys(red - q)])
    except KeyError:
        raise ValueError('k - Q is not a point of the grid.') from None


def kpoint_weights(table, weights, nkpoints, hole_indices=None):
    """
    The weight of the electron and of the hole at each k-point.

    Parameters
    ----------
    table : ndarray (nt, >=3), yambo's BSE table: k (the electron's), v, c, 1-based
    weights : ndarray (nt,), the weight of each transition (see :func:`state_weights`)
    nkpoints : int, the number of k-points of the full grid
    hole_indices : ndarray (nk,), the index of k-Q for each k (see
        :func:`hole_kpoint_indices`); None at Q = 0

    Returns
    -------
    electron, hole : ndarray (nkpoints,)
    """
    k = np.asarray(table)[:, 0].astype(int) - 1
    electron = np.bincount(k, weights=weights, minlength=nkpoints)
    hole = electron.copy() if hole_indices is None else np.bincount(np.asarray(hole_indices)[k], weights=weights,
                                                                    minlength=nkpoints)
    return electron, hole


def band_pair_weights(table, weights):
    """
    The weight of each valence-conduction pair, largest first: a list of
    (v, c, weight), bands 1-based.
    """
    table = np.asarray(table)
    pairs = table[:, 1].astype(int) * 100000 + table[:, 2].astype(int)
    unique, inverse = np.unique(pairs, return_inverse=True)
    totals = np.bincount(inverse, weights=weights)
    order = np.argsort(-totals)
    return [(int(unique[i] // 100000), int(unique[i] % 100000), float(totals[i])) for i in order]


def band_weights(table, weights):
    """
    The weight of each valence band (the hole's) and of each conduction band
    (the electron's): two dicts band -> weight, bands 1-based.
    """
    table = np.asarray(table)
    result = []
    for column in (1, 2):
        bands = table[:, column].astype(int)
        unique, inverse = np.unique(bands, return_inverse=True)
        totals = np.bincount(inverse, weights=weights)
        result.append({int(b): float(w) for b, w in zip(unique, totals)})
    return result[0], result[1]


def exciton_kspace(excdb, state, degenerate=True, degen_eps=1e-2, degen_rtol=1e-3, window=0.0, weighting='equal'):
    """
    The reciprocal-space analysis of exciton *state* (1-based) of a
    ``YamboExcitonDB`` loaded with its eigenvectors, summed over the states
    degenerate with it if *degenerate*, and over those within *window* (eV)
    of it, with *weighting* (see :func:`summed_states`).

    Returns
    -------
    dict with
        ``states`` : list of the states summed (1-based)
        ``shares`` : list, the share of each, and ``weighting``, the weighting used
        ``energy`` : the energy of *state* (eV)
        ``red_qpoint`` : Q in reduced coordinates
        ``electron``, ``hole`` : ndarray (nk,), the weights at each k-point of
            ``excdb.lattice.red_kpoints`` (the hole's at k-Q)
        ``pairs`` : list of (v, c, weight), largest first
        ``valence``, ``conduction`` : dicts band -> weight
    """
    if excdb.eigenvectors is None:
        raise ValueError('The database has no eigenvectors: load it with Load_WF=True '
                         '(and run yambo with WRbsWF).')
    if not 1 <= state <= len(excdb.eigenvalues):
        raise ValueError(f'State {state} does not exist: the database has {len(excdb.eigenvalues)} states loaded.')
    states, shares, used = summed_states(excdb, state, degenerate, degen_eps, degen_rtol, window, weighting)
    lattice = excdb.lattice
    weights = state_weights(excdb.eigenvectors, states, shares)
    red_kpoints = np.asarray(lattice.red_kpoints, dtype=float)
    car_qpoint = np.zeros(3) if excdb.car_qpoint is None else np.asarray(excdb.car_qpoint, dtype=float)
    red_qpoint = np.linalg.solve(np.asarray(lattice.rlat, dtype=float).T, car_qpoint)
    gamma = np.allclose(red_qpoint - np.round(red_qpoint), 0.0, atol=1e-6)
    holes = None if gamma else hole_kpoint_indices(red_kpoints, red_qpoint)
    electron, hole = kpoint_weights(excdb.table, weights, len(red_kpoints), holes)
    valence, conduction = band_weights(excdb.table, weights)
    return {'states': [int(s) for s in states], 'shares': [float(x) for x in shares], 'weighting': used,
            'energy': float(np.real(excdb.eigenvalues[state - 1])),
            'red_qpoint': red_qpoint, 'electron': electron, 'hole': hole,
            'pairs': band_pair_weights(excdb.table, weights), 'valence': valence, 'conduction': conduction}
