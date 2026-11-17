"""
qp_energies.py
==============
The quasiparticle energies of a yambo QP database, read by its content
(``QP_table``, ``QP_E``, ``QP_Eo``), whatever the file is called.

``yambopy.dbs.qpdb.YamboQPDB`` recognises QP databases by their file name:
it reads ``ndb.QP`` but not the same database renamed, nor the ones a GW
calculation split by bands leaves (e.g. ``ndb.QP_140_146``), which have
exactly the same variables. This reads any of them.

* :func:`qp_energies` — the QP and DFT energies on the irreducible k-points,
  for the bands of the database.

Meant for ``yambopy.dbs`` (as a reader of ``YamboQPDB``, or a replacement of
its name-based detection). Energies in eV, bands 1-based as in yambo.
"""

import numpy as np
from netCDF4 import Dataset

from yambopy.units import ha2ev

__all__ = ['qp_energies']


def qp_energies(filename):
    """
    The energies of a QP database.

    Returns
    -------
    dict with
        ``min_band``, ``max_band`` : the bands of the database (1-based, inclusive)
        ``qp`` : ndarray (nk, nb), the QP energies (eV), bands min_band to max_band
        ``dft`` : ndarray (nk, nb), the DFT energies they correct (eV)
        ``nkpoints`` : the irreducible k-points (nk), in the order of the SAVE database
    Missing entries (a band not computed at a k-point) are NaN.
    """
    with Dataset(filename) as database:
        table = np.asarray(database.variables['QP_table'][:], dtype=int)      # (band, band, k), 1-based
        energies = np.asarray(database.variables['QP_E'][:], dtype=float)     # (n, re/im), Ha
        dft = np.asarray(database.variables['QP_Eo'][:], dtype=float)         # (n,), Ha
        nkpoints = int(database.variables['QP_kpts'].shape[-1])
    bands, kpoints = table[0], table[2] - 1
    if energies.ndim == 2:
        energies = energies[:, 0]
    min_band, max_band = int(bands.min()), int(bands.max())
    qp = np.full((nkpoints, max_band - min_band + 1), np.nan)
    eo = np.full_like(qp, np.nan)
    qp[kpoints, bands - min_band] = energies * ha2ev
    eo[kpoints, bands - min_band] = dft * ha2ev
    return {'min_band': min_band, 'max_band': max_band, 'qp': qp, 'dft': eo, 'nkpoints': nkpoints}
