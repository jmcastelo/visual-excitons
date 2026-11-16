# Datasets and the System panel

[← Documentation](../README.md#documentation)

A dataset is the set of directories with the databases of one calculation:

- **SAVE** directory: contains `ns.db1`. The Bravais lattice type (`ibrav` index and variant) and parameters are detected from it, from the symmetry of the cell: centred lattices (FCC, BCC, body-centred tetragonal...) are recognised whatever primitive vectors the calculation used, and whatever their orientation.
- **BSE** directory: contains the `ndb.BS_diago_Q*` files, one per Q-point: `ndb.BS_diago_Q<n>` is the n-th Q-point of the irreducible list of the grid. Only some may have been computed (e.g. Q1 alone, for the optical spectrum, or Q1, Q2, Q5, Q30): the [System panel](#the-system-panel) and the status bar then say so (`4 of 90 Q-points`), and the program uses what there is:
  - The dispersion shows the computed Q-points that lie on the Q-path, without the interpolated curves (the interpolation needs every Q-point), with a note saying so. The points of each exciton are joined by straight lines, in the style of its curve (also in exported figures); untick `Draw the lines`, in the `Curves` section of the [Appearance panel](appearance.md), to show the points alone. With Q1 alone: lines at the exciton energies at Γ.
  - `Q-point` in the Absorption section adds the spectrum of any computed Q-point, on the path or not.
  - The Q-point of the wave function only takes computed ones.
  - The band structure needs Q1 (Γ).
- **GW** directory: contains the QP database, for DFT+GW+BSE calculations. QP databases are recognised by their content, whatever their names: e.g. `ndb.QP_140_146`, left by a calculation split by bands, or a renamed copy. When there are several, `ndb.QP` is used, otherwise the one with the widest band range, and `QP database` lets you choose another (with its bands and k-points); the choice is kept with the dataset and in sessions.

BSE databases with other names than `ndb.BS_diago_Q<n>` are recognised by their content too, as long as their name gives their Q-point as YamboPy reads it (the number after the first `Q`, e.g. `BSE_Q5`); those that do not, and two databases for the same Q-point, are reported.

**Checks.** The databases of a dataset share no identifier, but they can be checked against each other; the result is shown below the directories (`Details…` lists every check):

- The QP database was computed on the SAVE directory: same lattice constants, same k-points, and its DFT energies are those of the SAVE directory (up to the constant shift Yambo applies). Otherwise: an error.
- The BSE databases use bands of the SAVE directory, and those of newer Yambo versions, which store their Q-point, are of the Q-point their name gives. A sample of them is read, the first and last included.
- The bands of the BSE are within those the QP database corrects; a warning otherwise, since Yambo then applied no correction, or an extrapolated one, to the others.
- The BSE databases agree with each other; different Yambo revisions are mentioned.

The BSE databases with standard names are not opened when a dataset is opened (there can be hundreds, and reading each takes about 15 ms), and the checks read a sample of them. `Check all BSE` reads every one of them, in the background (with progress and `Cancel`; about a second for a hundred): each must be a BSE database and, for those of newer Yambo versions, of the Q-point its name gives. It catches files renamed with standard names that are not what their name says. Its result is kept until the BSE files change.

These files must be coherent, i.e. correspond to calculations of the same system.

`File › Open dataset…` (`Ctrl+O`) takes the folder of a calculation and finds these directories inside it. The SAVE directory is searched first; the BSE and GW directories are then searched next to it, so a folder with several systems is never mixed up. For example, opening `data/BiI3_Bulk_8x8x8` finds its `save`, `diagos` and `qp` subdirectories. The calculation type is set from whether a GW directory was found. `File › Open recent` lists the last datasets.

On start, the most recent dataset is opened again, with its Q-path. On the first run, the `BiI3` test dataset in `data/BiI3_Bulk_8x8x8` is opened if present (it is not included in the repository). Its Q-path must be set to `LGZF` instead of the default one, once: it is remembered from then on.
## The System panel

- **Data**: the calculation type and the three directories, which can also be chosen one by one with `Browse…` or typed in. A green tick or a red cross below each shows whether its databases were found.
- **Crystal lattice**: the detected `ibrav` and variant, and the lattice parameters `a`, `b`, `c` in Å (hover over them for their value in Bohr) and `α`, `β`, `γ` in degrees.
- **Q-path**: the labels of the high-symmetry points along the path, as a string such as `GLB1,BZGX` (commas separate disconnected sections; spaces or hyphens may separate the labels, as in `G-L-B1`). A label is one capital letter or a capitalised Greek name (`G` is Γ; `Sigma`, `Lambda`...), optionally followed by a subscript and primes, e.g. `X1`, `Sigma1`, `K'`; the plots show them typeset (Γ, Σ₁, K′, and `K|U` where the path jumps), and its sampling, by number of points or by density: points per Bohr⁻¹ of path length in reciprocal space (without 2π; 300 by default, about 100 to 250 points along the default paths of common crystals). Press `Set Q-path` to apply it. The Q-path is saved with the dataset, together with its sampling, the lattice type and the extra high-symmetry points: when the dataset is opened again, in this session or a later one, it is restored and applied, so the dispersion can be computed right away. A saved path that no longer applies (e.g. to a different lattice) is dropped, with a message in the status bar.
- **High-symmetry points**: the points of the Brillouin zone of the lattice, with their fractional coordinates `k₁`, `k₂`, `k₃` relative to the reciprocal lattice vectors. Right-click the table to add extra points, which can then be used in the Q-path, or to delete them.
