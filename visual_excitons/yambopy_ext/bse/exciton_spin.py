"""
exciton_spin.py
===============
The spin of excitons along any direction n: the eigenvalues of ⟨S'|S·n|S⟩
within each degenerate group, total, of the electron or of the hole, from
spinor wave functions (spin-orbit), as A. R. Kshirsagar et al., Phys. Rev. B
112, 12 (2025), and ``yambopy.bse.exciton_spin`` do it.

* :func:`spin_operator` — S·n as a 2x2 matrix;
* :func:`spin_matrix_elements` — ⟨k,m|S·n|k,n⟩ on the full grid, with memory
  proportional to the irreducible k-points;
* :func:`exciton_spin` — the spin of groups of exciton states.

``YamboWFDB.get_spin_m_e_BZ`` copies the wave functions to every k-point of
the full grid (5.9 GB for 14 bands of BiI3 on an 8x8x8 grid; far more for
denser grids). Since S acts on the spinor index only, the sum over plane
waves can be done first, on the irreducible k-points, giving small 2x2
matrices per band pair; the operator, rotated for each k-point of the full
grid, is applied to them afterwards. The result is the same (to 1e-15).

Meant for ``yambopy.dbs.wfdb`` / ``yambopy.bse.exciton_spin``. States
1-based, as in yambo.
"""

import numpy as np

from yambopy.dbs.wfdb import su2_mat
from yambopy.bse.exciton_spin import compute_exciton_spin

__all__ = ['spin_operator', 'spin_matrix_elements', 'exciton_spin']

PAULI = np.array([[[0, 1], [1, 0]], [[0, -1j], [1j, 0]], [[1, 0], [0, -1]]], dtype=complex)


def spin_operator(direction=(0.0, 0.0, 1.0)):
    """S·n = (n_x σ_x + n_y σ_y + n_z σ_z) / 2 for a direction n (Cartesian, normalised here)."""
    n = np.asarray(direction, dtype=float)
    n = n / np.linalg.norm(n)
    return 0.5 * np.einsum('i,iab->ab', n, PAULI)


def spin_matrix_elements(wfdb, operator):
    """
    ⟨k,m|O|k,n⟩ for a spin operator *operator* (2x2) on every k-point of the
    full grid of *wfdb* (a ``YamboWFDB`` with spinors): ndarray (nk_BZ, nb, nb),
    as ``YamboWFDB.get_spin_m_e_BZ`` (same conventions), without copying the
    wave functions to the full grid.
    """
    if wfdb.nspin != 1 or wfdb.nspinor != 2:
        raise ValueError('Spin matrix elements need spinor wave functions (spin-orbit coupling, nspinor = 2).')
    lattice = wfdb.ydb
    psi = wfdb.wf[:, 0]                                                 # (nk_ibz, nb, 2, ng)
    # Spinor matrices of each band pair on the irreducible k-points: small
    pairs = np.einsum('kmag,knbg->kmnab', psi.conj(), psi, optimize=True)
    rotations = lattice.sym_car
    nsym = len(rotations)
    half = nsym / (1 + int(np.rint(lattice.time_rev)))                  # time-reversal symmetries: the second half
    su2 = np.array([su2_mat(rotations[i], i >= half) for i in range(nsym)])
    symmetry, kpoint = np.asarray(lattice.symmetry_indexes), np.asarray(lattice.kpoints_indexes)
    time_reversed = symmetry >= half
    op = np.broadcast_to(np.asarray(operator, dtype=complex), (len(symmetry), 2, 2)).copy()
    op[time_reversed] = op[time_reversed].conj()
    op = su2[symmetry].conj().transpose(0, 2, 1) @ op @ su2[symmetry]
    result = np.einsum('kab,kmnab->kmn', op, pairs[kpoint], optimize=True)
    result[time_reversed] = result[time_reversed].conj()
    return result


def exciton_spin(excdb, wfdb, groups, direction=(0.0, 0.0, 1.0), matrix_elements=None):
    """
    The spin of groups of exciton states along *direction*.

    Parameters
    ----------
    excdb : ``YamboExcitonDB`` loaded with the eigenvectors of the states of *groups*
    wfdb : ``YamboWFDB`` with spinors and the bands of the BSE
    groups : list of lists of states (1-based), each a degenerate group
    direction : the spin axis n (Cartesian)
    matrix_elements : ⟨k,m|S·n|k,n⟩ of :func:`spin_matrix_elements` for that
        direction, if already computed

    Returns
    -------
    list, one dict per group: ``states``, and ``total``, ``electron``, ``hole``:
    for each state of the basis that diagonalises the total S·n within the
    group (in increasing total spin), its total spin and the electron's and
    the hole's parts in that same basis (so total = electron + hole), each a
    list of floats
    """
    if matrix_elements is None:
        matrix_elements = spin_matrix_elements(wfdb, spin_operator(direction))
    matrices = {name: compute_exciton_spin(excdb.lattice, excdb, wfdb, matrix_elements, contribution=key)
                for name, key in (('total', 'b'), ('electron', 'e'), ('hole', 'h'))}
    def block(matrix, index):
        b = matrix[np.ix_(index, index)]
        return 0.5 * (b + b.conj().T)                                    # Hermitian (numerical noise)
    result = []
    for group in groups:
        index = np.array([int(s) for s in group]) - 1
        values, basis = np.linalg.eigh(block(matrices['total'], index))
        entry = {'states': [int(s) for s in group], 'total': [float(v) for v in values]}
        for name in ('electron', 'hole'):
            part = basis.conj().T @ block(matrices[name], index) @ basis
            entry[name] = [float(v) for v in np.real(np.diag(part))]
        result.append(entry)
    return result
