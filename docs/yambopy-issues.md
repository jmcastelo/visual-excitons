# YamboPy issues

[← Documentation](../README.md#documentation)

Problems found in [YamboPy](https://github.com/yambo-code/yambopy) while building Visual Excitons, written to be filed as GitHub issues. Each section is one issue: its heading is the issue title, and the text below it the body, ready to copy and paste. Where Visual Excitons works around a problem, the code that does it is named; the code in `visual_excitons/yambopy_ext/` is written to be contributed to YamboPy as a fix.

Each section starts with a hidden comment (`<!-- ... -->`) with its status, when it was found and what to check before filing: it is not shown on GitHub if pasted with the body. Update the status when an issue is filed (with its link) or fixed, and add new findings at the end, with the next number.

| # | Issue | Status |
|---|---|---|
| 1 | `YamboExcitonDB.from_db_file` fails on BSE databases without a `COUPLING` variable | Not filed |
| 2 | `YamboLatticeDB.k_grid` returns a wrong grid for some datasets | Not filed |
| 3 | `YamboExcitonDB` takes the Q-point index from the file name | Not filed |
| 4 | `ExcitonDispersion` only works when every Q-point was computed | Not filed |
| 5 | Packaging uses setuptools settings that stop working after 2027-02-18 | Not filed (verify) |
| 6 | Invalid escape sequences in string literals | Not filed (verify) |
| 7 | Failing tests, and test runs that leave files in the repository | Not filed (verify) |
| 8 | `get_exciton_weights` puts the hole at the electron's k-point: wrong at finite Q | Not filed |
| 9 | `get_exciton_transitions` reads the BSE table as (k, c, v) and keeps only the last state | Not filed |
| 10 | `YamboExcitonDB.interpolate` folds the weights with the crystal's symmetries | Not filed |
| 11 | `YamboExcitonDB.interpolate` misaligns QP energies when the QP and BSE band ranges differ | Not filed |
| 12 | `YamboQPDB` recognises QP databases by file name | Not filed |
| 13 | `SkwInterpolator` does not reproduce its data for a layer with a dense k-grid | Not filed |
| 14 | Exciton weight functions loop over the transitions in Python | Not filed (enhancement) |
| 15 | No Brillouin zone geometry for oblique or 3D lattices | Not filed (enhancement) |
| 16 | `compute_exc_rep` warns about `Lkind` for databases that store it in capitals | Not filed |
| 17 | `compute_exc_rep` only prints, writes caches into the data folders and calls `exit()` | Not filed |
| 18 | `YamboWFDB.get_spin_m_e_BZ` copies the wave functions to the whole Brillouin zone | Not filed |
| 19 | `compute_exc_rep` fails at Q-points whose little group is trivial (C1) | Not filed |
| 20 | `ex_wf2Real` silently enlarges even supercells, so the Born–von Kármán supercell cannot be used | Not filed |
| 21 | No density of the hole or of the electron of an exciton | Not filed (enhancement) |
| 22 | `YamboBSEAbsorptionSpectra.get_excitons` mixes up energies, intensities and indices when states are degenerate | Not filed |

---

<!-- Status: not filed. Found 2026-11-10 (BN dataset, Yambo 5.1 r21121). Check: confirm that older revisions computed without coupling. -->
## 1. `YamboExcitonDB.from_db_file` fails on BSE databases without a `COUPLING` variable

`from_db_file` reads `database.variables['COUPLING']` unconditionally (`yambopy/dbs/excitondb.py`, introduced in bfe8e1f). BSE databases written by older Yambo versions (e.g. Yambo 5.1, revision 21121) do not have that variable, so loading any of them raises:

```
KeyError: 'COUPLING'
```

This breaks every feature that reads excitons on such datasets.

**Suggested fix:** treat a missing variable as no coupling:

```python
is_coupling = database.variables['COUPLING'][...].data if 'COUPLING' in database.variables else False
```

(Please confirm that older revisions computed without coupling.)

---

<!-- Status: not filed. Found 2026-11-14. Visual Excitons computes the grid from the expanded k-points (core/cellshift.py, kGrid). -->
## 2. `YamboLatticeDB.k_grid` returns a wrong grid for some datasets

`k_grid` does not match the k-point grid of the calculation:

| Dataset | Actual grid | `k_grid` |
|---|---|---|
| WSe2 monolayer | 72×72×1 | `[25 37 1]` |
| BiI3 bulk | 8×8×8 | `[8 7 8]` |

Counting the spacings of the expanded reduced k-points (`red_kpoints`) gives the correct grids. `k_grid` seems to be derived from the irreducible k-points rather than the full grid.

---

<!-- Status: not filed. Found 2026-11-13. -->
## 3. `YamboExcitonDB` takes the Q-point index from the file name

`from_db_file` sets `Qpt = filename.split("Q", 1)[1]` and recognises Γ by `Qpt == "1"`. As a result:

- a file whose name has no `Q` raises an `IndexError`;
- a name like `ndb.BS_diago_Q1.bak` gives `"1.bak"`, so Γ is not recognised, and for older databases without `Q-point` coordinates the exciton then gets no momentum.

Newer databases store the Q-point coordinates (`Q-point`), which could be used instead. Alternatively, the Q-point index could be accepted as an argument.

---

<!-- Status: not filed. Found 2026-11-12. Visual Excitons reads the computed Q-points from the file numbers and loads them with YamboExcitonDB (core/options.py, computedQPoints; core/calculations.py). -->
## 4. `ExcitonDispersion` only works when every Q-point was computed

`ExcitonDispersion.__init__` counts `glob(folder + '/ndb.BS_diago_Q*')` and raises `Incomplete list of qpoints (n/N)` unless the count equals `lattice.ibz_nkpoints`. It then loads `ndb.BS_diago_Q1` … `Q<n>` by position. So:

- a BSE run for only some Q-points (e.g. Q1 alone, or Q1, Q2, Q5, Q30) cannot be used, even for a non-interpolated dispersion;
- a stray file matching the pattern breaks the count.

**Suggestion:** read the Q-point indices from the file numbers, and allow a non-interpolated dispersion over the computed subset. (The SKW interpolation genuinely needs the full grid.)

---

<!-- Status: not filed. Found 2026-11-06. Check before filing: run `pip install -e .` on upstream master and read the setuptools warnings; the fork may differ. -->
## 5. Packaging uses setuptools settings that stop working after 2027-02-18

`pyproject.toml` uses `tool.setuptools.license-files` and license classifiers, which setuptools deprecates, with removal announced after 2027-02-18. The package list also makes setuptools warn about data folders being packaged implicitly (`qepy.data`, `qepy.tests`).

**Suggested fix:** use the PEP 639 `license` / `license-files` fields under `[project]`, and declare the data packages explicitly.

---

<!-- Status: not filed. Found 2026-11-10. Check before filing: count them on upstream master (python -W error::SyntaxWarning -m compileall). -->
## 6. Invalid escape sequences in string literals

About 60 string literals in `qepy`, `yamboparser` and the tutorials contain invalid escape sequences (e.g. `"\s"`, `"\G"` in non-raw strings). Python 3.12+ emits `SyntaxWarning` for them, and a future version will make them errors.

**Fix:** use raw strings (`r"..."`) or escape the backslashes.

---

<!-- Status: not filed. Found 2026-11-10 (on the ase-bz fork; they failed before its changes). Check before filing: run the tests on upstream master. -->
## 7. Failing tests, and test runs that leave files in the repository

The tests for `bse_absorption`, `dipolesdb`, `excitondb` and `outputfile` fail, as do two `schedulerpy` tests.

Running pytest over the whole project also makes the failing `schedulerpy` tests leave `pre_run_pbs.sh`, `run.sh` and `testconfig.json` in the repository root. They should write to a temporary directory instead.

---

<!-- Status: not filed. Found 2026-11-17. Fix offered: visual_excitons/yambopy_ext/bse/exciton_kspace.py (hole_kpoint_indices, kpoint_weights) and bse/exciton_bands.py (band_kpoint_weights). Evidence: tests/test_composition.py::test_weights_agree_with_yambopy_and_put_the_hole_at_k_minus_q. -->
## 8. `get_exciton_weights` puts the hole at the electron's k-point: wrong at finite Q

`YamboExcitonDB.get_exciton_weights` adds each transition's weight |A|² to its conduction band **and** to its valence band at the same k-point, the k of the BSE table:

```python
k,c,v = kcv[0:3]-1
this_weight = abs2(eivec[t])
weights[k,c] += this_weight
weights[k,v] += this_weight
```

That is right at Q = 0 only. At a finite momentum Q, a transition of yambo's table (k, v, c) takes the hole from the valence band at **k−Q** to the conduction band at **k** (the k of the table is the electron's). So the hole's weight belongs to the valence band at k−Q.

The convention can be checked from the DFT energies: for the lowest exciton of a BiI3 bulk calculation (8×8×8 grid), the weighted mean of the transition energies E_c(k) − E_v(k ∓ Q) is lower with the hole at k−Q:

| Q-point | Hole at k−Q | Hole at k+Q |
|---|---|---|
| Q12 = (0, 1/8, −1/8) | 1.392 eV | 1.442 eV |
| Q30 = (1/8, 1/4, 3/8) | 1.470 eV | 1.518 eV |

Everything built on these weights is therefore wrong at finite Q: `exciton_bs`, `interpolate`, `get_exciton_bs` and `plot_exciton_2D_ax` place the hole's contributions at the electron's k-points.

**Suggested fix:** map each k to the index of k−Q on the grid, and add the valence weight there:

```python
red_q = np.linalg.solve(lattice.rlat.T, car_qpoint)
# index of k - Q for each k of lattice.red_kpoints (modulo reciprocal lattice vectors)
holes = hole_kpoint_indices(lattice.red_kpoints, red_q)
np.add.at(weights, (k, c), w)
np.add.at(weights, (holes[k], v), w)
```

A vectorised implementation, with tests, is available (`hole_kpoint_indices`, `kpoint_weights`, `band_kpoint_weights`) and could be contributed.

---

<!-- Status: not filed. Found 2026-11-17. Fix offered: visual_excitons/yambopy_ext/bse/exciton_kspace.py (band_pair_weights, band_weights). -->
## 9. `get_exciton_transitions` reads the BSE table as (k, c, v) and keeps only the last state

`YamboExcitonDB.get_exciton_transitions` has two problems:

```python
w_k_v_to_c = np.zeros([self.nkpoints,self.nvbands,self.ncbands])
v_min = self.unique_vbands[0]
c_min = self.unique_cbands[0]
for exciton in excitons:
    ...
    for t,kcv in enumerate(self.table):
        k,c,v = kcv-1
        #k,v,c = kcv-1                 # bug?? Double-check
        this_weight = abs2(eivec[t])
        w_k_v_to_c[k,v-v_min,c-c_min] = this_weight
```

1. The table is (k, v, c): its second column holds the valence bands, as the class's own `unique_vbands` (column 1) and `transitions_v_to_c` assume. Unpacking it as `k,c,v` swaps them, so `v - v_min` is a conduction band minus the lowest valence band and `c - c_min` a valence band minus the lowest conduction band: indices out of range (an `IndexError`, or negative indices wrapping around). For BiI3, with valence bands 139–148 and conduction bands 149–152, `v - v_min` runs from 10 to 13 on an axis of length 10.
2. It assigns (`=`) instead of adding (`+=`), so for several states (e.g. a degenerate group) only the last one counts.

**Suggested fix:** `k, v, c = kcv[0:3] - 1` and `w_k_v_to_c[k, v - v_min, c - c_min] += this_weight`.

---

<!-- Status: not filed. Found 2026-11-17. Fix offered: visual_excitons/yambopy_ext/bse/exciton_bands.py (interpolate_exciton_bands, interpolate_on_grid). Explanation: docs/architecture.md, "Excitonic band structure: interpolation". -->
## 10. `YamboExcitonDB.interpolate` folds the weights with the crystal's symmetries

To interpolate the exciton weights along the path, `interpolate` folds them into the irreducible wedge and runs SKW with the crystal's symmetries:

```python
ibz_weights = np.zeros([lat.ibz_nkpoints, self.mband - self.start_band])
for ik_bz, ik_ibz in enumerate(lat.kpoints_indexes): ibz_weights[ik_ibz] = weights[ik_bz]
```

This takes the weight of one member of each star (the last) for all of them, which is only right if the weights have the full symmetry of the crystal. They often do not:

- at a finite Q, they only have the symmetry of the little group of Q;
- even at Γ, a single state of a degenerate group is an arbitrary mixture of the group, without the full symmetry (only the sum over the group has it).

**Suggestion:** interpolate the weights on the full grid, with no symmetry. SKW without symmetries is correct but costly on dense grids (about 3 s for an 8×8×8 grid, but over 6 minutes, unfinished, for 72×72). A periodic cubic spline on the full grid (`scipy.ndimage.map_coordinates` with `mode='grid-wrap'`) is exact at the grid points, smooth and costs nothing; clipping at zero removes its tiny undershoots next to sharp peaks. Energies, which have the full symmetry, can keep SKW. An implementation is available (`interpolate_exciton_bands`, `interpolate_on_grid`), together with the finite-Q weights of issue 8.

---

<!-- Status: not filed. Found 2026-11-17 (BiI3 bulk: ndb.QP bands 140-157, BSE bands 139-152). Evidence: tests/test_band_structure.py::test_at_gamma_the_energies_are_yambopys. Fix offered: yambopy_ext/bse/exciton_bands.py (band_energies_ibz) and yambopy_ext/dbs/qp_energies.py. -->
## 11. `YamboExcitonDB.interpolate` misaligns QP energies when the QP and BSE band ranges differ

With a `YamboQPDB`, `interpolate` takes the QP energies of the BSE bands from the first columns of the QP database, whatever band the database starts at:

```python
else:
    # eigs = energies.eigenvalues_qp[:, self.start_band:self.mband]
    # Is this correct???
    eigs = energies.eigenvalues_qp[:, 0:(self.mband - self.start_band)]
```

When the two ranges start at different bands, every band gets the energies of another. For a BiI3 calculation whose QP database covers bands 140–157 and whose BSE uses bands 139–152, the band drawn as 139 has the energies of band 140, the one drawn as 140 those of band 141, and so on: the whole excitonic band structure is shifted by one band.

**Suggested fix:** use the database's own band range (`min_band`), `eigenvalues_qp[:, b - min_band]` for band b, and decide what to do with BSE bands outside the QP range (e.g. the DFT energy corrected as the nearest QP band, or an error). The QP and DFT energies of the databases also have different zeros (5.745 eV apart for BiI3), which matters when mixing them.

---

<!-- Status: not filed. Found 2026-11-17. Fix offered: visual_excitons/yambopy_ext/dbs/qp_energies.py (reads QP_table, QP_E, QP_Eo). -->
## 12. `YamboQPDB` recognises QP databases by file name

`YamboQPDB.from_db` reads only files the YamboFile parser recognises as QP databases by their name. A QP database with another name fails, although it has exactly the same variables (`QP_table`, `QP_E`, `QP_Eo`, `QP_kpts`):

- a renamed copy;
- the databases a GW calculation split by bands leaves, e.g. `ndb.QP_140_146`.

For `ndb.QP_140_146`:

```
File ".../yambopy/dbs/qpdb.py", line 31, in __init__
    self.kpoints_iku  = np.array(qps['Kpoint'])
KeyError: 'Kpoint'
```

**Suggestion:** recognise QP databases by their content (the variables above) rather than their name. A small reader that does so is available (`qp_energies`).

---

<!-- Status: not filed. Found 2026-11-17 (WSe2 monolayer, 72x72x1 grid, 469 irreducible k-points, spin-orbit). Check before filing: reproduce on upstream master; the dataset is not public, offer it or a smaller one that shows the same. Visual Excitons checks the fit and falls back to a spline of the full-grid energies (yambopy_ext/bse/exciton_bands.py, interpolate_energies). -->
## 13. `SkwInterpolator` does not reproduce its data for a layer with a dense k-grid

For a WSe2 monolayer with a 72×72×1 k-point grid (469 irreducible k-points, spin-orbit coupling), the SKW interpolation of the DFT energies does not go through the energies it is fitted to: evaluated at the irreducible k-points, it misses them by up to 1.13 eV, and along a path the bands oscillate by 1–2 eV. SciPy warns that the linear system (`scipy.linalg.solve(hmat, ...)`) is ill-conditioned. For a BiI3 bulk calculation (8×8×8 grid) the same code reproduces the data to 1e-14 eV.

How it is called (as in `YamboExcitonDB.interpolate`):

```python
kpoints = car_red(np.array([k / lat.alat for k in lat.ibz_kpoints]), lat.rlat)
symrel = [s for s, t in zip(lat.sym_rec_red, lat.time_rev_list) if not t]
skw = SkwInterpolator(5, kpoints, eigs[None], 0, 0, (lat.lat, lat.red_atomic_positions, lat.atomic_numbers),
                      symrel, bool(lat.time_rev))
error = np.abs(skw.interp_kpts(kpoints).eigens[0] - eigs).max()     # 1.13 eV
```

What does not seem to be the cause:

- the symmetries: applied as SKW does (`omat.T @ k`), they rebuild the full 5184-point grid from the irreducible points, and no two irreducible points are equivalent;
- other symmetry choices: without time reversal, or with all 24 operations, the fit fails as well;
- the vacuum axis: stretching c in the cell given to SKW makes it worse.

A possible cause: the search box for the lattice vectors of the star functions (`rmax`) has the same size along the three axes, which suits a cube rather than a thin layer with a single k-plane.

**Suggestion:** check the fit (`interp_kpts` at the input k-points) and warn or fail when it does not reproduce the data, rather than returning oscillating bands. (Visual Excitons now does this check and falls back to a spline of the full-grid energies.)

---

<!-- Status: not filed. Enhancement. Found 2026-11-17. Implementation offered: visual_excitons/yambopy_ext/bse/exciton_kspace.py. -->
## 14. Exciton weight functions loop over the transitions in Python

`get_exciton_weights`, `get_exciton_total_weights` and `get_exciton_transitions` loop over every transition of the BSE table in Python, which is slow for large tables (e.g. 82,944 transitions for a WSe2 72×72 grid), and more so for several states.

**Suggestion:** vectorise them with NumPy, e.g. `np.bincount(table[:, 0] - 1, weights=w, minlength=nk)` for the weight per k-point and `np.add.at` per band. The vectorised versions (`state_weights`, `kpoint_weights`, `band_pair_weights`, `band_weights`) analyse the 82,944-transition table in 0.05 s, and could be contributed with issues 8 and 9.

---

<!-- Status: not filed. Enhancement. Found 2026-11-17. Implementation offered: visual_excitons/yambopy_ext/bz/wigner_seitz.py, with tests. -->
## 15. No Brillouin zone geometry for oblique or 3D lattices

`yambopy.plot.plotting.BZ_Wigner_Seitz` draws the first Brillouin zone as a matplotlib patch for hexagonal and rectangular 2D lattices only (oblique lattices are not supported, and 3D zones not at all), and `BrillouinZone` builds paths but has no zone geometry.

**Suggestion:** compute the Wigner–Seitz cell of the reciprocal lattice with the Voronoi construction (`scipy.spatial.Voronoi`), which works for every lattice. An implementation is available: `wigner_seitz_cell` (vertices, edges and faces in 3D), `wigner_seitz_polygon` (2D), `plane_section` (the zone cut by a plane) and `fill_wigner_seitz` (the points of a k-grid inside the zone), tested on cubic, hexagonal, FCC, BCC and triclinic lattices.

---

<!-- Status: not filed. Found 2026-11-17 (BiI3 bulk, Yambo database with Lkind "BAR"). -->
## 16. `compute_exc_rep` warns about `Lkind` for databases that store it in capitals

`compute_exc_rep` checks the kind of the BSE kernel with lowercase strings:

```python
if iqpt==1 and 'bar' not in excdb.Lkind:
    print(f"Warning: You are using Lkind={excdb.Lkind} at q=0, but 'Lbar' is recommended. ...")
```

Databases can store it in capitals (here `Lkind = "BAR"`), so the check fails and a calculation done the recommended way gets the warning:

```
Warning: You are using Lkind=BAR at q=0, but 'Lbar' is recommended. Symmetries are broken in this way.
```

**Suggested fix:** compare case-insensitively, e.g. `'bar' not in excdb.Lkind.lower()` (and the same for `'full'`).

---

<!-- Status: not filed. Found 2026-11-17. A version returning its results is offered: visual_excitons/yambopy_ext/bse/exciton_symmetry.py (exciton_irreps). -->
## 17. `compute_exc_rep` only prints, writes caches into the data folders and calls `exit()`

`yambopy.bse.exciton_irreps.compute_exc_rep` does the group-theory analysis of the excitons well, but it is hard to use from other code:

- it returns nothing: the little group and the representations are only printed;
- it writes files where the data are: `Dmat_elec_Cache_spglib.npy` (and `BS_left_ev_Cache_qpt_<n>.npy`) into the BSE folder, and `Symmetry_info_excitons.txt` into the current directory, which may be read-only or shared;
- for projective representations it calls `exit("Error : Projective representations are not implemented")`, which ends the whole Python process (an interactive session, a notebook kernel or a GUI) instead of raising an exception;
- it loads the eigenvectors of all the states (or the states asked plus 100), even when the representation of one exciton is wanted.

**Suggestions:** return the results (e.g. a list of energy, degeneracy and decomposition, plus the little group), make caching optional with a chosen location, raise `NotImplementedError` instead of `exit()`, and accept the states to analyse. The electronic representation matrices (`wfdb.Dmat`) could also be passed in, as they serve every Q-point of a dataset.

---

<!-- Status: not filed. Found 2026-11-17 (BiI3 bulk 8x8x8: a 5.90 GiB array for 14 bands). Fix offered: visual_excitons/yambopy_ext/bse/exciton_spin.py (spin_matrix_elements), checked identical to 1e-15 (tests/test_character.py). -->
## 18. `YamboWFDB.get_spin_m_e_BZ` copies the wave functions to the whole Brillouin zone

To compute the spin matrix elements ⟨k,m|S|k,n⟩ on the full grid, `get_spin_m_e_BZ` already rotates the spin operator instead of the wave functions, but then copies the irreducible wave functions to every k-point of the zone:

```python
wfc_tmps = self.wf[:,0,...][kpt_idx]
nk, nb, nspinor, ng = wfc_tmps.shape
S_me = S_z_tmp[:,None,:,:]@wfc_tmps
```

That is one array of nk_BZ × nbands × 2 × ng complex numbers, and another of the same size for `S_me`. For a BiI3 bulk calculation (8×8×8 grid, 14 bands) it fails:

```
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 5.90 GiB for an array with shape (512, 14, 2, 27626) and data type complex128
```

and it would need far more for denser grids (e.g. 5184 k-points for 72×72), which makes `compute_exc_spin_iqpt` unusable there.

**Suggested fix:** since S acts on the spinor index only, sum over the plane waves first, on the irreducible k-points, and apply the rotated operator afterwards:

```python
psi = self.wf[:, 0]                                                   # (nk_ibz, nb, 2, ng)
P = np.einsum('kmag,knbg->kmnab', psi.conj(), psi, optimize=True)     # (nk_ibz, nb, nb, 2, 2): small
S_me = np.einsum('kab,kmnab->kmn', S_z_tmp, P[kpt_idx], optimize=True)
S_me[time_rev] = S_me[time_rev].conj()
```

This gives the same matrix elements (to 1e-15 for BiI3), about 30 times faster, with memory proportional to the irreducible k-points only.

---

<!-- Status: not filed. Found 2026-11-17 (BiI3 bulk, Q12 = (0, 1/8, -1/8), little group C1). Worked around in visual_excitons/yambopy_ext/bse/exciton_symmetry.py (reshapes the table). -->
## 19. `compute_exc_rep` fails at Q-points whose little group is trivial (C1)

For a Q-point whose little group is only the identity (C1), `get_pg_info` returns the character table as a one-dimensional array:

```python
>>> get_pg_info(np.array([np.eye(3)]))[3]
array([1.])          # shape (1,), where (1, 1) is expected
```

`decompose_rep2irrep` then fails on it (`np.einsum('j,j,rj->r', ...)`):

```
ValueError: Einstein sum subscript j does not contain the correct number of indices for operand 2.
```

so `compute_exc_rep` cannot analyse excitons at such Q-points (e.g. Q12 = (0, 1/8, −1/8) of a BiI3 bulk calculation, where every exciton is simply A).

**Suggested fix:** return the table as a 2D array (irreps × classes) in `get_pg_info` for every group, or reshape it in `decompose_rep2irrep`: `char_table = np.asarray(char_table).reshape(len(irrep_labels), len(class_order))`.

---

<!-- Status: not filed. Found 2026-11-18 (BiI3 bulk 8x8x8, checking the hole density of yambopy_ext.bse.exciton_particle_density against ex_wf2Real). Check: whether an even supercell is ever needed by other users, and what the docstring should promise. -->
## 20. `ex_wf2Real` silently enlarges even supercells, so the Born–von Kármán supercell cannot be used

`ex_wf2Real_kernel` (`yambopy/bse/realSpace_excitonwf.py`) increases every even supercell size by one, so that the fixed particle can sit in the central cell:

```python
for i in range(3):
    if supercell[i]%2 == 0:
        print('Warning : Even supercell given, so increasing'
              + ' supercell size along %d direction by 1'%(i+1))
        supercell[i] = supercell[i] +1
```

It also modifies the caller's list in place. Only a printed warning tells, and printed output is easily lost (e.g. in a GUI or a notebook with output captured).

This matters when the supercell is meant to be the Born–von Kármán supercell (the k-point grid, e.g. 8 × 8 × 8), over which the exciton wave function is exactly periodic: asking for it gives 9 × 9 × 9 cells, one more period slab of the exciton. For example, the total weight of the wave function over the supercell is then not the density of the fixed particle at its position (it is, over exactly one period), off by about 1 % for an exciton of BiI3.

**Suggested fix:** do not modify the argument (copy it), and either allow even supercells (placing the fixed particle in the cell `supercell // 2`, not necessarily central) or raise a `ValueError` that says why sizes must be odd; return the supercell used (already in `supercell_latvecs`, but not as sizes).

---

<!-- Status: not filed (enhancement). Found 2026-11-18. Code to contribute: visual_excitons/yambopy_ext/bse/exciton_particle_density.py, with tests in tests/yambopy_ext/test_exciton_particle_density.py. -->
## 21. No density of the hole or of the electron of an exciton

`ex_wf2Real` computes the exciton wave function with one particle fixed, but nothing in YamboPy tells where to fix it. The natural guide is the density of that particle, wherever the other one is: for the hole

    ρ_h(r_h) = ∫ |Ψ(r_e, r_h)|² dr_e = Σ_k Σ_c | Σ_v A_kcv ψ*_v,k−Q(r_h) |²

(and for the electron the same with c and v swapped), exact by the orthonormality of the Bloch functions. The total weight of the wave function computed with the hole at r₀ is ρ_h(r₀), so fixing the hole where ρ_h is small gives a weak, noisy electron density; for bands of p or d character ρ_h vanishes at the nuclei (10⁻⁴ of its maximum on the iodine atoms of BiI3, whose maxima are 0.8–0.9 Å away), so the common choice of fixing the hole on an atom can be poor.

With natural transition orbitals per k-point (the eigenvectors of Σ_states A_k⁺A_k), it takes at most min(n_c, n_v) orbitals per k and a second or two on the grid `ex_wf2Real` uses at 10 Ry (BiI3 8×8×8, WSe2 72×72×1), exactly for groups of degenerate states.

**Proposal:** add `exciton_particle_density` (the density on the grid of `ex_wf2Real` at a given cutoff, so that its maxima are fixed positions used as they are), `particle_nto` and `density_maxima` to `yambopy.bse`, e.g. next to `realSpace_excitonwf`; an implementation following YamboPy's conventions is in Visual Excitons (`yambopy_ext/bse/exciton_particle_density.py`).

---

<!-- Status: not filed. Found 2026-11-19 (WSe2 72x72x1, validating against Dogadov et al. 2026). Worked around in visual_excitons/core/calculations.py (computeAbsorption). -->
## 22. `YamboBSEAbsorptionSpectra.get_excitons` mixes up energies, intensities and indices when states are degenerate

`get_excitons` takes the energies from `excitondb.get_nondegenerate()` (one per degenerate group) and the intensities from `excitondb.get_intensities()` (one per state), and pairs them by position:

```python
energies, indices = self.excitondb.get_nondegenerate(eps=eps)
intensities = self.excitondb.get_intensities()
for i in range(len(energies)):
    if energies[i] < max_energy and intensities[i] > min_intensity:
        excitons.append((energies[i], intensities[i], i))
```

As soon as a group is degenerate, the two lists have different lengths and every entry after it pairs the energy of one group with the intensity of another state. The third value, `i`, is the position in the list of groups (0-based), not the state's index, although that is what a caller needs to select the exciton (and `indices`, which holds the states, is not used).

For WSe2 at Γ (72×72×1, 10 states): states 1–2 (1.638 and 1.643 eV) are dark, the bright A doublet is states 3–4 (1.6868 eV, intensities 1 and 0.22), then states 5–6 (1.8298 eV, dark). `get_excitons(min_intensity=0.1)` returns `(1.6868, 1.0, 2)` and `(1.8298, 0.22, 3)`: a bright exciton at 1.83 eV that does not exist, and indices that, read as states, are a dark exciton (2) and the second state of A (3, 0-based). Even with no degeneracy at all, the index is 0-based where `YamboExcitonDB` counts states from 1 (e.g. `get_degenerate`).

**Proposal:** return every state, with its own energy, intensity and index (1-based, as yambo):

```python
energies = self.excitondb.eigenvalues.real
intensities = self.excitondb.get_intensities()
excitons = [(e, s, n + 1) for n, (e, s) in enumerate(zip(energies, intensities))
            if e < max_energy and s > min_intensity]
```

and, if degenerate groups are wanted as one entry, sum the intensities over each group (as `Degen_Step` tries to do afterwards) and keep the index of its first state. Visual Excitons now builds the list this way (`core/calculations.computeAbsorption`).
