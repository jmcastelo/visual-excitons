"""
exciton_symmetry.py
===================
The symmetry of excitons: the irreducible representations of the little
group of their momentum Q that their degenerate groups transform as (e.g. Au,
E_g), from the group theory of M. Nalabothula et al., Phys. Rev. B 113,
205130 (2026), as ``yambopy.bse.exciton_irreps.compute_exc_rep`` does it.

Unlike ``compute_exc_rep``, it returns its results instead of printing them,
writes no files, raises exceptions instead of calling ``exit()``, analyses
only the states asked, and takes the electronic representation matrices of
a previous call (they serve every Q-point of a dataset), computing only
those of the symmetries it needs (the little group of Q).

* :func:`crystal_symmetries` — the crystal's symmetry operations (spglib);
* :func:`little_group` — those that leave Q unchanged;
* :func:`degenerate_groups` — states grouped by energy;
* :func:`exciton_irreps` — the representations of groups of states.

Meant for ``yambopy.bse.exciton_irreps``. States 1-based, as in yambo;
energies in eV.
"""

import numpy as np

from yambopy.bse.rotate_excitonwf import rotate_exc_wf
from yambopy.symmetries.point_group_ops import get_pg_info, decompose_rep2irrep
from yambopy.tools.degeneracy_finder import find_degeneracy_evs

__all__ = ['crystal_symmetries', 'little_group', 'degenerate_groups', 'exciton_irreps']


def crystal_symmetries(lattice, tol=1e-4):
    """
    The symmetry operations of the crystal of *lattice* (a ``YamboLatticeDB``)
    from spglib, which finds all of them (non-symmorphic ones included), not
    only those of the SAVE database.

    Returns
    -------
    rotations : ndarray (nsym, 3, 3), Cartesian
    translations : ndarray (nsym, 3), Cartesian (Bohr)
    """
    from yambopy.symmetries.crystal_symmetries import Crystal_Symmetries
    symmetries = Crystal_Symmetries(lattice, tol=tol)
    return np.asarray(symmetries.rotations, dtype=float), np.asarray(symmetries.translations, dtype=float)


def little_group(rotations, lat, red_qpoint, tol=1e-5):
    """
    The indices of the *rotations* (Cartesian) that leave Q unchanged, up to a
    reciprocal lattice vector. *red_qpoint* in the crystal coordinates
    ``lat @ car_qpoint`` (as ``compute_exc_rep``).
    """
    lat = np.asarray(lat, dtype=float)
    inverse = np.linalg.inv(lat)
    q = np.asarray(red_qpoint, dtype=float)
    result = []
    for isym, rotation in enumerate(rotations):
        difference = lat @ rotation @ inverse @ q - q
        if np.linalg.norm(difference - np.rint(difference)) < tol:
            result.append(isym)
    return result


def degenerate_groups(energies, atol=1e-3, rtol=1e-3):
    """The states (1-based) grouped by degenerate energies (eV): a list of lists, in increasing energy."""
    energies = np.asarray(energies, dtype=float)
    order = np.argsort(energies)
    groups = find_degeneracy_evs(energies[order], atol=atol, rtol=rtol)
    return [sorted(int(order[i]) + 1 for i in group) for group in groups]


def exciton_irreps(excdb, wfdb, groups, symmetries=None, dmats=None, symm_tol=1e-2):
    """
    The irreducible representations that groups of exciton states transform as.

    Parameters
    ----------
    excdb : ``YamboExcitonDB`` loaded with the eigenvectors of the states of *groups*
    wfdb : ``YamboWFDB`` with the bands of the BSE
    groups : list of lists of states (1-based), each a degenerate group (see
        :func:`degenerate_groups`); a group that is not closed under the
        symmetries gives no integer decomposition (an error for that group)
    symmetries : (rotations, translations) of :func:`crystal_symmetries`; found if None
    dmats : dict, symmetry index -> its electronic representation matrices
        (``wfdb.Dmat``); those missing are computed and added to it, so that
        the same dict serves later calls (other Q-points of the dataset)
    symm_tol : tolerance of the decomposition into irreducible representations

    Returns
    -------
    dict with
        ``point_group`` : the Schoenflies label of the little group of Q
        ``operations`` : the indices of its symmetries (in *symmetries*)
        ``classes`` : the labels of its classes
        ``groups`` : one dict per group: ``states``, ``energy`` (their mean),
            ``irreps`` (e.g. 'Au', '2Ag + E_1g'), or ``error`` if it could not
            be decomposed

    Raises
    ------
    NotImplementedError
        For a BSE with coupling (not Tamm-Dancoff), and for Q-points where
        non-symmorphic symmetries give projective representations.
    """
    lattice = excdb.lattice
    rotations, translations = crystal_symmetries(lattice) if symmetries is None else symmetries
    car_qpoint = np.zeros(3) if excdb.car_qpoint is None else np.asarray(excdb.car_qpoint, dtype=float)
    red_qpoint = np.asarray(lattice.lat, dtype=float) @ car_qpoint
    operations = little_group(rotations, lattice.lat, red_qpoint)
    if not operations:
        raise ValueError('No symmetry leaves Q unchanged: check the symmetries.')

    akcv = excdb.get_Akcv()
    if akcv.shape[1] != 1:
        raise NotImplementedError('The symmetry of excitons of a BSE with coupling (beyond Tamm-Dancoff) '
                                  'needs the left eigenvectors: not implemented.')
    for isym in operations:
        # Projective representations (non-symmorphic symmetries at boundary Q-points): not implemented
        shift = rotations[isym].T @ car_qpoint - car_qpoint
        phase = shift @ translations[isym]
        if abs(phase - np.rint(phase)) > 1e-3:
            raise NotImplementedError('At this Q-point non-symmorphic symmetries give projective representations: '
                                      'not implemented.')

    dmats = {} if dmats is None else dmats
    missing = [isym for isym in operations if isym not in dmats]
    if missing:
        computed = wfdb.Dmat(symm_mat=rotations[missing], frac_vec=translations[missing], time_rev=False)
        for isym, dmat in zip(missing, computed):
            dmats[isym] = dmat

    lat = np.asarray(lattice.lat, dtype=float)
    inverse = np.linalg.inv(lat)
    point_group, classes, class_dict, char_table, irreps = get_pg_info(rotations[operations])
    # (irreps, classes): get_pg_info gives the trivial group's (C1) table as a 1D array
    char_table = np.asarray(char_table).reshape(len(irreps), len(classes))
    representatives = np.zeros(len(classes), dtype=int)
    class_orders = np.zeros(len(classes), dtype=int)
    for label, members in class_dict.items():
        representatives[label] = min(members)
        class_orders[label] = len(members)

    energies = np.real(np.asarray(excdb.eigenvalues))
    result = []
    for group in groups:
        group = [int(s) for s in group]
        ak = akcv[np.array(group) - 1]
        traces = np.zeros(len(operations), dtype=complex)
        for position, isym in enumerate(operations):
            rotated = rotate_exc_wf(ak, lat @ rotations[isym] @ inverse, wfdb.kBZ, red_qpoint, dmats[isym], False,
                                    ktree=wfdb.ktree)
            phase = np.exp(1j * 2 * np.pi * np.dot(car_qpoint, translations[isym]))
            traces[position] = phase * np.einsum('m...,m...->', ak.conj(), rotated, optimize=True)
        characters = traces[representatives]
        entry = {'states': group, 'energy': float(np.mean(energies[np.array(group) - 1]))}
        try:
            entry['irreps'] = decompose_rep2irrep(characters, char_table, len(operations), class_orders, irreps,
                                                  tol=symm_tol).strip()
        except AssertionError:
            entry['error'] = ('Not a representation: the states are not a closed degenerate group '
                              '(an accidental near-degeneracy, or states missing).')
        result.append(entry)
    return {'point_group': str(point_group), 'operations': [int(i) for i in operations],
            'classes': [str(c) for c in classes], 'groups': result}
