"""
Code meant for YamboPy (https://github.com/yambo-code/yambopy), kept here
until it is added there, as a replacement or an enhancement of its own.

Its layout mirrors YamboPy's (``bz``, ``bse``), and it follows YamboPy's
conventions rather than this program's: snake_case names, NumPy-style
docstrings, reduced and Cartesian coordinates as ``YamboLatticeDB`` gives
them (``red_kpoints``, ``rlat``: Bohr⁻¹, without 2π), yambo's 1-based band
and exciton indices. It depends only on NumPy, SciPy and YamboPy: nothing
from the rest of this program (no Qt), so that each module can be moved as
it is. Its tests are in ``tests/yambopy_ext``, also without Qt.
"""
