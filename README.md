# Visual Excitons

Within the framework of YamboPy, this is a GUI to explore exciton properties visually.

**UNDER DEVELOPMENT!**

## Dependencies

Visual Excitons depends on YamboPy for data calculations, on PySide6 for GUI elements, with PySide6-QtAds for its dockable panels, and on PyQtGraph for visualization, which requires PyOpenGL for OpenGL based 3D plots. It also uses NumPy, SciPy and netCDF4, and psutil to tell the memory available. They are all installed with it (see [Installation](#installation)).

### YamboPy

"Create automatic workflows for yambo and quantum espresso using python. Work directly with netCDF databases. Do pre/post-processing, data analysis and plotting for yambo and quantum espresso."

- https://github.com/yambo-code/yambopy
- https://github.com/jmcastelo/yambopy/tree/ase-bz

### PySide6

"Qt for Python offers the official Python bindings for Qt, which enables you to use Python to write your Qt applications."

- https://doc.qt.io/qtforpython-6

### PySide6-QtAds

Python bindings of the Qt Advanced Docking System, which provides the dockable panels of the main window. Each release is built for one exact PySide6 version, which is the PySide6 version installed with it.

- https://github.com/mborgerson/pyside6_qtads
- https://github.com/githubuser0xFFFF/Qt-Advanced-Docking-System

### PyQtGraph

"PyQtGraph is a pure-python graphics and GUI library built on PyQt / PySide and numpy. It is intended for use in mathematics / scientific / engineering applications."

- https://www.pyqtgraph.org
- https://github.com/pyqtgraph/pyqtgraph

## Installation

Visual Excitons needs Python 3.10 or later and a graphics card with OpenGL (any recent one). In a virtual environment:

```
python -m venv visual-excitons-env
source visual-excitons-env/bin/activate        # on Windows: visual-excitons-env\Scripts\activate
pip install git+https://github.com/jmcastelo/visual-excitons.git
```

This installs Visual Excitons and everything it needs, including the YamboPy fork it depends on (see below). Then start it with:

```
visual-excitons
```

or `python -m visual_excitons`. To update it, run the `pip install` command again with `--upgrade`.

**Why a fork of YamboPy.** Visual Excitons needs the Brillouin-zone tools (Bravais lattices, high-symmetry points, Q-paths) of the `ase-bz` branch of [jmcastelo/yambopy](https://github.com/jmcastelo/yambopy/tree/ase-bz), which the official YamboPy does not have yet. The installation takes it from there.

## How to develop?

The architecture of the code (structure, data flows, threading, rendering, conventions and pitfalls) is explained in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Clone this repository, for example in `~/visual-excitons`, create a virtual environment in it, and install the program in editable mode (your changes to the code take effect without reinstalling) with the test tools:

```
git clone https://github.com/jmcastelo/visual-excitons.git ~/visual-excitons
cd ~/visual-excitons
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

Run it with `visual-excitons`, `python -m visual_excitons` or `python visual_excitons/main.py`.

**Working on the YamboPy fork too.** The command above installs the fork from GitHub. To work on it as well, clone it (e.g. in `~/yambopy`), switch to the `ase-bz` branch and install it in editable mode, **after** installing Visual Excitons:

```
git clone https://github.com/jmcastelo/yambopy ~/yambopy
cd ~/yambopy
git switch ase-bz
pip install -e . --config-settings editable_mode=compat
```

The last option helps some IDEs find the package, as noted [here](https://stackoverflow.com/questions/76301782/why-are-pycharm-and-pylance-not-detecting-packages-installed-in-editable-mode). Setuptools warns that this `compat` mode is transitional and will be removed: when it is, install without it, and add the fork's folder to the analysis paths of your editor instead (e.g. `basedpyright.analysis.extraPaths` in VS Code). Installing Visual Excitons again later (`pip install -e .`) replaces the editable fork by the one on GitHub: reinstall the editable fork afterwards, or use `pip install -e . --no-deps`.

**Version.** The version of Visual Excitons is set in `visual_excitons/__init__.py` (`__version__`), which the packaging and the About box read. The package is described in `pyproject.toml`, with the minimum versions of its dependencies.

### Tests

The tests use [pytest](https://docs.pytest.org) and [pytest-qt](https://pytest-qt.readthedocs.io), installed with the `test` extra (`pip install -e ".[test]"`, above).

Run them from the repository root:

```
pytest
```

They need no display: Qt runs on its offscreen platform, and the application settings are written to a temporary directory, so your own are never touched.

**In parallel.** The tests run in parallel processes ([pytest-xdist](https://pytest-xdist.readthedocs.io), installed with the `test` extra), without saturating the computer: one process per physical CPU core and at most half the CPU threads (4 processes on a 4-core, 8-thread CPU), only as many as fit in the free memory (about 1 GB each, keeping 2 GB free), and one thread each for the numerical libraries. On a 4-core CPU, the default run takes about 15 s instead of about 30 s. To run them serially, e.g. to debug a test with breakpoints, add `-n0`.

The suite covers:

- `test_bonds.py`: bond detection on crystals with known coordination, periodic images, half bonds in supercells.
- `test_rendering.py`: sphere and cylinder meshes, the opacity calibration of the volume, cell parameters.
- `test_core.py`: datasets, options, exciton selection, error reporting of calculations, absorption curves and their styles.
- `test_tasks.py`: background calculations (worker thread, ordering, progress, cancellation, queue replacement, the hooks into yambopy's progress).
- `test_gui.py`: the main window and its panels (preset and saved layouts, themes, exciton selection across panels, controls).
- `test_analysis.py`: plane cuts (exact interpolation, masking, plane axes, intersection with the supercell) and the distance distribution (radii of a Gaussian, truncation warning).
- `test_memory.py`: the real-space grid (as yambopy's, for several cutoffs), the memory estimate and the block size, and the display upsampling.
- `test_figures.py`: publication figures (panels, arrangements, shared energy axis, styles, fonts and formats, data files), the exported scripts run in a separate Python, and the export dialog.
- `test_session.py`: session files (format, versions, interrupted saves, fingerprints), results round trip, and a whole setup through the window (changed and moved datasets).
- `test_export.py`: the density files (read back and checked), and the image export: the rendering checks need OpenGL, which Qt's offscreen platform lacks, so they run in a separate process on the display (`render_checks.py`), and are skipped without one.
- `test_persistence.py`: parameters kept between sessions, preferences and per dataset.
- `test_appearance.py`: the styles of the 2D plots kept between sessions (each curve's too), and theme colors following the theme.
- `test_environment.py`: the test run itself (number of processes, threads of the numerical libraries).
- `test_workflow.py`: end-to-end calculations on the `BiI3` dataset (dispersion, absorption, selection, wave function), also in the background with progress and cancellation.

Tests that read the datasets in `data/` (not in the repository; marked `data`) are skipped when these are missing. The end-to-end tests are slow (marked `slow`, about 40 s) and do not run by default. Run them on their own, after the others:

```
pytest              # the fast tests, in parallel
pytest -m slow      # the slow tests, serially
```

The slow tests always run serially, in a single process, with at most half the CPU threads: each loads gigabytes of wave functions (about 3 GB at its peak), and next to other test processes, or after all the other tests in the same process (`pytest -m "slow or not slow"`, which needs about 5 GB), they can exhaust the memory of a 16 GB computer in use.

## Usage instructions

The main window is made of panels:

- **System**: the data of a calculation, its crystal lattice and the Q-path.
- **Dispersion**, **Absorption** and **Band structure**: the excitonic spectra.
- **Wave function**: the exciton wave function in real space, with the crystal structure.
- **Analysis**: cuts of the wave function and the distribution of electron–hole distances (see below).
- **Spectra controls** and **Wave function controls**: the parameters, made of collapsible sections. Click a section header to open or close it; the panel scrolls when its open sections do not fit.
- **Appearance**: the style of the 2D plots (see [Appearance of the plots](#appearance-of-the-plots)).

**Arranging the panels.** Drag a panel by its tab to put it next to another one, or onto it to make them tabs of one area; the drop indicators show where it will go. The button at the top right of a panel area floats it in its own window (or double-click its tab), and the cross closes it. `View › Panels` shows or hides each panel.

The `Layout` menu arranges the panels for each step of the usual workflow, or shows all of them:

| Layout | Shortcut | Panels |
|---|---|---|
| System | `Ctrl+1` | System |
| Spectra | `Ctrl+2` | Dispersion, absorption, band structure, the spectra controls and the Appearance panel |
| Wave function | `Ctrl+3` | Wave function, analysis (when on) and the wave function controls |
| Overview | `Ctrl+4` | All of them: the spectra on the left, the wave function in the middle, the controls, the Appearance and the System panel as tabs on the right |

Your own arrangements can be kept too: `Layout › Save layout as…` saves the current one under a name, which then appears in the `Layout` menu; `Layout › Delete layout` removes it. The arrangement of the panels is kept between restarts; it is not stored in session files, since it depends on your screen rather than on the data.

The status bar shows the dataset loaded (name, Bravais lattice and number of Q-points) and what is being computed.

**Calculations run in the background**, so the window stays usable while they run: you can rotate the 3D view, look at the spectra or change display settings meanwhile. The status bar shows the running calculation, its current stage (e.g. `Loading the wave functions`, `Real-space wave function`) with a progress bar, and how many more are queued. `Cancel` or `Esc` stops it and drops the queued ones; it stops within a fraction of a second. Calculations run one at a time, in the order requested; requesting the same kind of calculation again (e.g. editing the absorption range several times) replaces the queued one instead of piling up. Opening another dataset cancels the calculations on the previous one. Errors are reported in a dialog.

**Themes.** `View › Theme` switches between the `System` look, a `Light` theme and a `Dark` theme. The plots and the 3D view follow the theme: dark plots on the dark theme, light ones on the light theme. Curves that keep their default color follow it too; colors chosen in the Appearance panel are kept.

**Resuming where you left off.** When the program is opened again, it resumes where it was left:

- The window: its size, the arrangement of the panels (and your saved layouts), the theme, and which sections of the control panels are open.
- Preferences: how the wave function is displayed (plot type, iso level, number of levels, style, opacities, volume settings), the view (basis, preset, direction and up vectors, side, projection), the structure (atoms, names, bonds and boundaries shown, atom and bond sizes, bond colors), the axes gizmo and cell parameters shown, whether bright excitons are labelled, and the `Appearance` of the 2D plots (lines, symbols, axes colors and fonts, legend, band structure fill and weight factor). Colors that were the theme's defaults follow the theme, so a style made on the dark theme still suits the light one.
- The last dataset, with its own parameters: its Q-path, the number of excitons of the dispersion, the absorption range, step and bright threshold, the exciton chosen (Q-point and index), the fixed particle with the positions of the hole and the electron, the supercell and the cutoff, and the view of the 3D scene (rotation, zoom and pan).

Each dataset keeps its own parameters: switching to another one and back, or opening it again later from `Open recent` or `Open dataset`, brings them back; a dataset opened for the first time starts from the defaults. Results (dispersion, spectra, wave function) are not kept this way: compute them again, with the parameters already set, or save a session (below).

### Sessions

A session file (`.vxsession`) keeps a whole setup, to come back to it later or to share it: the dataset, its Q-path, all the parameters and display settings, the exact view of the 3D scene, the `Appearance` of the 2D plots (with the style of each curve, e.g. a color per absorption spectrum) and, optionally, the computed results. Keep several sessions of the same dataset for different figures or excitons, e.g. one per exciton with its own view and colormap.

- `File › Save session` (`Ctrl+S`) saves the current setup in its session file, or asks for one the first time; `Save session as…` (`Ctrl+Shift+S`) saves it in a new one. The name of the session is shown in the title of the window.
- `File › Open session…` (`Ctrl+Shift+O`) and `Open recent session` restore a session.
- `Store results in sessions` (on by default) stores the computed results: dispersion, absorption spectra, band structure, the selected exciton and the wave function. Opening the session then shows them at once, without computing anything. The files stay small (the wave function is stored compressed, in single precision): e.g. 0.2 MB for a BiI3 session with all of them.

When a session is opened:

- If its dataset is no longer where it was (moved, or on another computer), you are asked to locate its folder.
- Its results are only shown if the databases are the same as when it was saved (same files, sizes and modification times; when the dataset was moved, the same files and sizes). Otherwise the parameters are restored, and the results can be computed again.

Opening another dataset or session leaves the current session: `Save session` then asks for a file, so that one setup never overwrites another. Session files are zip archives with a readable `session.json` and the results in `results.npz`.

### Datasets

A dataset is the set of directories with the databases of one calculation:

- **SAVE** directory: contains `ns.db1`. The Bravais lattice type (`ibrav` index and variant) and parameters are detected from it.
- **BSE** directory: contains the `ndb.BS_diago_Q*` files, one per Q-point.
- **GW** directory: contains `ndb.QP`, for DFT+GW+BSE calculations.

These files must be coherent, i.e. correspond to calculations of the same system.

`File › Open dataset…` (`Ctrl+O`) takes the folder of a calculation and finds these directories inside it. The SAVE directory is searched first; the BSE and GW directories are then searched next to it, so a folder with several systems is never mixed up. For example, opening `data/BiI3_Bulk_8x8x8` finds its `save`, `diagos` and `qp` subdirectories. The calculation type is set from whether a GW directory was found. `File › Open recent` lists the last datasets.

On start, the most recent dataset is opened again, with its Q-path. On the first run, the `BiI3` test dataset in `data/BiI3_Bulk_8x8x8` is opened if present (it is not included in the repository). Its Q-path must be set to `LGZF` instead of the default one, once: it is remembered from then on.

### System

- **Data**: the calculation type and the three directories, which can also be chosen one by one with `Browse…` or typed in. A green tick or a red cross below each shows whether its databases were found.
- **Crystal lattice**: the detected `ibrav` and variant, and the lattice parameters `a`, `b`, `c` in Å (hover over them for their value in Bohr) and `α`, `β`, `γ` in degrees.
- **Q-path**: the labels of the high-symmetry points along the path, as a string such as `GLB1,BZGX` (commas separate disconnected sections), and its sampling, by number of points or by density. Press `Set Q-path` to apply it. The Q-path is saved with the dataset, together with its sampling, the lattice type and the extra high-symmetry points: when the dataset is opened again, in this session or a later one, it is restored and applied, so the dispersion can be computed right away. A saved path that no longer applies (e.g. to a different lattice) is dropped, with a message in the status bar.
- **High-symmetry points**: the points of the Brillouin zone of the lattice, with their fractional coordinates `k₁`, `k₂`, `k₃` relative to the reciprocal lattice vectors. Right-click the table to add extra points, which can then be used in the Q-path, or to delete them.

### Spectra

Three panels plot the excitonic dispersion, the absorption spectra and the band structure (side by side in the `Spectra` layout, with the dispersion above the band structure).

Spectra controls:

- **Dispersion**: choose the number of excitons and press `Compute dispersion`. Then click a point of the dispersion to plot the absorption spectrum at its Q-point; `Ctrl`-click to keep several spectra together. Clicking a point also selects its exciton (see below).
- **Absorption**: the energy range and step of the spectra (in eV), and the `Bright threshold`. With `Automatic range` (the default), each spectrum spans the energies of its own excitons, plus a margin of 0.5 eV (five times the broadening of the peaks) on both sides; the range of the spectra plotted is shown below. Untick it to set the range by hand with `From` and `To`. Excitons with at least this intensity (relative to the brightest) are marked as bright points on the spectrum; the rest, as dark bars below it. `Label bright excitons` shows the index and intensity of each bright exciton.
- **Selected exciton**: click an exciton on the dispersion, or a bright exciton on an absorption spectrum, to select it. It is marked with an orange ring on both plots (on the absorption spectrum, when it is bright there). Its index, Q-point and energy are shown here and in the status bar, and the exciton is selected in the Wave function controls too. `Compute its wave function` computes it with the settings of the Wave function controls (fixed particle and position, supercell, cutoff) and brings the Wave function panel to the front. The memory it needs is shown below the button, with the settings used; as for `Compute wave function`, it is shown in orange with ⚠ when it likely does not fit in the memory available, and the program asks before starting it.
- **Export**: `Export figure…` (also `File › Export 2D figure…`, `Ctrl+Shift+F`) makes publication figures of the plots, drawn with [Matplotlib](https://matplotlib.org) (see below).

#### Appearance of the plots

The Appearance panel sets the style of the 2D plots. Open it on a plot with the palette button in the title bar of the plot's panel, or with `Appearance…` in the plot's right-click menu; the tabs at its top switch between the three plots. Its sections, those of the plot chosen:

- **Curves**: the line pattern, color and width. `Apply to` chooses whether the changes apply to all the curves or to one of them (named after its exciton, Q-point or band); clicking a curve in a plot chooses it there. With all the curves, `Gradient` colors them along a range of hues, from the first color to the last.
- **Symbols** (dispersion and absorption): the shape and size of the points; `Different shape per curve` gives each curve a shape of its own.
- **Axes**: the color and font of the title, axis labels and tick labels, the color and width of the axes, and the background. With `Same axes style for all plots`, the changes apply to the three plots.
- **Legend** (absorption): its text color and size, background (`None` for a transparent one), border and position.
- **Fill** (band structure): the color of the excitonic weights around the bands, and their scale (`Weight factor`).

The color and font buttons show the current value and open a dialog that previews the change on the plot as you pick: `OK` keeps it, `Cancel` restores the style as it was, each curve's included. The Appearance is kept between sessions and in session files.

**Publication figures.** The export dialog draws the plots with Matplotlib, as figures for papers, with the colors, line styles and symbols set in the Appearance panel, and shows a preview:

- **Panels**: the dispersion, the absorption spectra and the band structure (those computed), alone or combined, in the order of the list (drag them to reorder), in a row or in a column, with panel letters (a), (b)... With `Dispersion and absorption on one energy axis`, the absorption is drawn rotated next to the dispersion, sharing its energy axis, over the range of the dispersion and of the bright excitons.
- **Size**: in cm, with the widths of one column (8.6 cm), one and a half (12.9 cm) and two columns (17.8 cm) of usual two-column journals, or any other.
- **Fonts**: DejaVu Sans or Serif, STIX (similar to Times) or Computer Modern (as LaTeX), and their size in points.
- **Contents**: the legend of the spectra, the bright (in their colors) and dark (in grey) excitons below the absorption, the index of the bright excitons, a ring around the selected exciton, Γ instead of G on the path, titles.
- **Files**: `Save figure…` saves it as PDF, SVG or EPS (vector graphics, best for papers) or PNG or TIFF at the chosen resolution. `Save as script…` saves a Python script and its data file (`.npz`) that recreate the figure with Matplotlib: edit its options (size, fonts, panels...) or its code, and run it with `python`. It does not need Visual Excitons, only NumPy and Matplotlib, so it can be kept with a paper and adapted to a journal's style.

The figures use the data as computed: e.g. the absorption spectra are sampled every `Step` of the `Absorption` section, which shows as straight segments when the shared energy axis zooms into them; use a smaller step for smoother curves. The last options of the dialog are remembered.

Band structure:

- Excitonic weights are displayed.
- Only for Gamma points, at the moment.

Thanks to PyQtGraph, you can explore the 2D graphs using the mouse. Left-clicking on a graph and dragging you can move it, and with the wheel you can scale it proportionally on both axes. The same is true for each individual axis. Also, several plot options can be changed, and you can take some actions on the graphs too, by right-clicking on them, which opens a menu with the following entries:

- **View all**: resets the graph so that it is entirely shown within its frame.
- **X axis** and **Y axis**: change their range and invert them, among other actions.
- **Mouse Mode**: change behaviour of mouse left button between translation of the graph and selection of a portion of it.
- **Plot Options**: feel free to explore them!
- **Export**: allows exporting the plot to different formats (CSV, HDF5, Image File, Matplotlib Window or SVG).

### Wave function

Currently under active development, the Wave function panel plots 3D visualizations of the probability density of the wave function of excitons, together with the crystal structure.

#### Computing the wave function

- **Exciton**: the `Q-point` (the file `ndb.BS_diago_Q<n>`) and the index of the `Exciton` at that Q-point, in increasing energy. Selecting an exciton in the spectra fills them in, and its energy is then shown below.
- **Calculation**:
  - `Fixed particle`: the hole or the electron, whose position is fixed while the probability density of the other one is computed.
  - `Position (a, b, c)`: its position in crystal coordinates of the unit cell. After computing, it is moved to the nearest point of the real-space grid of the wave function, as explained in the note shown below it.
  - `Supercell`: the number of unit cells along each lattice vector. Only odd sizes are allowed, so that the fixed particle sits in the central cell.
  - `Cutoff`: the plane-wave cutoff of the wave function, in Ry, which sets the resolution of the result: only the plane waves of the wave functions below it are used, and the real-space grid is the smallest one that holds them. The points per unit cell grow with the square root of the cutoff (for BiI3: 13, 18 and 24 along each lattice vector at 5, 10 and 20 Ry). `All plane waves` uses all those of the SAVE database, the finest grid possible (46 points for BiI3); beyond the cutoff of the DFT calculation there is nothing more to gain.
  - Below the button, the size of the calculation is estimated as its parameters change: its grid, per unit cell and in the whole supercell, and the memory it needs at its peak, with the memory available. The estimate is computed from the shapes of the arrays involved (the wave functions of the bands of the exciton, the real-space arrays, the density and its display copies); it is an estimate within some tens of percent. Excitons degenerate with the one chosen are computed with it, and multiply the memory. When the calculation would need more than 90% of the available memory, the estimate is shown in orange with ⚠, and `Compute wave function` asks before starting it.

    Part of the calculation runs over blocks of k-points, whose buffer can take gigabytes for fine grids and many degenerate states. The block size is reduced automatically to keep it within a quarter of the available memory: the result is the same (the sum over k-points is only split differently) and the time barely changes. For BiI3, exciton 10 (10 degenerate states) at the full cutoff needs about 3.5 GB instead of 8.8 GB. The memory available is read with [psutil](https://github.com/giampaolo/psutil) on Linux, Windows and macOS; without psutil, the estimate is shown without it.
  - Press `Compute wave function`. The wave functions of the dataset are loaded the first time only: later calculations on the same dataset, for other excitons, positions, supercells or cutoffs, skip that step and are several times faster.

#### Plot types and rendering

The `Display` section of the Wave function controls controls how the probability density is displayed. Choose the display mode with `Plot type`; only the controls of the selected mode are shown:

- **Isosurface**: a single translucent surface at the level set with the `Iso level` slider, with lighting that reveals its 3D shape.
- **Isosurface set**: a number of nested translucent surfaces (`Number of levels`), evenly spaced between the lowest and highest density and colored with the viridis colormap. Their look is chosen with `Isosurface set style`:
  - `Lit, edges emphasized` (default): soft lighting gives shape cues, and the surfaces become more opaque near their outlines so nested shells remain distinguishable.
  - `Edges only (x-ray)`: no lighting, only the more opaque outlines. Lighter and more see-through.
- **Volumetric**: the density rendered as a translucent cloud, colored like the isosurfaces. Light is absorbed through it as through a fog whose thickness grows with the density, so dense regions look more opaque. Three controls apply:
  - `Volume opacity` (default 0.8): the opacity along the densest line of sight through the cloud. It means the same whatever the shape or extent of the density and the resolution of the grid. Low values give a light, see-through cloud, and high values a denser one.
  - `Volume contrast` (default 1.0): a power applied to the density before computing the opacity. Values above 1 fade the low-density tails so that the core stands out, and values below 1 bring the tails out. Colors keep following the actual density.
  - `Slices per voxel`: the rendering quality. The volume is drawn as a stack of slices, and more slices give a smoother result. It does not change the overall opacity.

Each isosurface type keeps its own transparency, set with `Isosurface opacity` and `Isosurface set opacity` respectively.

**Colormap.** The colors of the density, for all plot types, are chosen with `Colormap`; each entry shows its gradient, from low to high density. The density is never negative, so the colormaps offered are sequential:

- Perceptually uniform, from matplotlib: `Viridis` (default), `Plasma`, `Inferno`, `Magma`, and `Cividis`, readable with color-vision deficiencies. Equal steps in density look like equal steps in color, so they do not create false features.
- Others, from the [CET collection](https://colorcet.com/) of perceptually uniform colormaps: `Fire`, `Blues`, `Sunset` (light at low densities, which suits the light theme), `Blue-magenta-yellow` and `Greys`; and `Turbo`, an improved rainbow with high contrast but not perceptually uniform.

`Reverse` swaps the ends of the colormap. Colormaps that start dark (e.g. `Inferno`, `Magma`, `Fire`) hide the low densities on the dark theme, and those that start light (`Blues`, `Sunset`) on the light one: reverse them, or pick another, to suit the background. The choice is remembered between sessions.

**Smoothing.** `Smoothing` displays the density on a grid 2 or 3 times finer, interpolated with cubic splines from the computed one: isosurfaces and volume look smoother, especially when zoomed in or at low cutoffs. It adds no physical detail (that needs a higher cutoff), and the analysis and the exported files use the computed grid. The finer copy is computed once per wave function. Plots that take a while to prepare (with smoothing, or isosurface sets on fine grids) are prepared in the background, with their progress in the status bar, while the previous plot stays shown; the window stays responsive, and rotating stays smooth even with nearly a million triangles.

Translucent surfaces are drawn from back to front, and are re-sorted whenever the view is rotated, panned or zoomed. This way, overlapping and nested surfaces blend correctly from any viewpoint.

Atoms are drawn as lit spheres in their Jmol colors, sized by their covalent radii (see [Atoms and bonds](#atoms-and-bonds)). Their chemical symbols are shown as labels on the surface of each atom, facing the viewer. Labels behave like the rest of the scene: they scale with zoom, are hidden by atoms in front of them, and are tinted by translucent surfaces in front of them.

The 3D view uses antialiasing, so edges of atoms, lines and surfaces are smooth.

#### View directions

The `View` section of the Wave function controls lets you look at the lattice and the wave function from well-defined directions, given either in Cartesian coordinates or in terms of the crystal lattice.

**Convention.** A view direction is the *direction of projection*: the direction from the viewer into the screen, as in [VESTA](http://jp-minerals.org/vesta/en/doc/VESTAch10.html). For example, viewing along lattice direction `[0 0 1]` means looking down the `c` axis, with `c` pointing away from you. The literature is not unanimous on this sign. In transmission electron microscopy, for instance, the zone axis is usually taken antiparallel to the electron beam, i.e. pointing towards the observer ([JEMS](https://www.jems-swiss.ch/Home/Help/ZoneAxis.htm), [Wikipedia: Zone axis](https://en.wikipedia.org/wiki/Zone_axis)). The `View from the opposite side` checkbox flips the direction, so both conventions are available. It is checked by default, so the initial view (Cartesian `x + y + z`) places the camera in the positive octant, looking towards the origin.

**Bases.** Direction and up vectors are interpreted in the basis chosen in the `Basis` selector:

- **Cartesian**: components along `x`, `y`, `z`.
- **Lattice [uvw]**: the lattice vector `u a + v b + w c`.
- **Reciprocal (hkl)**: the reciprocal-lattice vector `h a* + k b* + l c*`, i.e. the normal to the `(hkl)` planes. This is useful for looking perpendicular to atomic planes, for example to the layers of a layered material.

The lattice and reciprocal bases use the lattice vectors read from `ns.db1`, so they are only available once a valid **SAVE** directory has been loaded.

**Presets.** Each basis comes with a set of presets in the `Preset` selector:

- Cartesian: `x`, `y`, `z`, `x + y`, `x + z`, `y + z`, `x + y + z`.
- Lattice: `a [1 0 0]`, `b [0 1 0]`, `c [0 0 1]`, `[1 1 0]`, `[1 0 1]`, `[0 1 1]`, `[1 1 1]`.
- Reciprocal: `a*`, `b*`, `c*` (normals to `(1 0 0)`, `(0 1 0)`, `(0 0 1)`) and the normals to `(1 1 0)`, `(1 0 1)`, `(0 1 1)`, `(1 1 1)`.

Note that lattice directions are defined with respect to the cell stored in `ns.db1`. For a rhombohedral primitive cell, such as that of bulk `BiI3`, the hexagonal `c` axis is the lattice direction `[1 1 1]`, not `[0 0 1]`.

**Custom directions.** How to set your own view:

1. Choose a basis.
2. Type the three components of the view direction in the `Direction` boxes. Selecting a preset fills them in, so you can start from one and modify it.
3. Optionally, type an up vector in the `Up (optional)` boxes, in the same basis. Its component perpendicular to the view direction will point upwards on the screen. Unlike in VESTA, it does not need to be perpendicular to the view direction. Left empty (`auto`), the up direction is `z`, or `y` when looking along `z`.
4. Press `Apply` or `Enter`. Invalid input, such as a zero direction, is reported in red below the controls.

**Rotation modes.** PyQtGraph's 3D view supports two camera rotation methods, and the view directions behave identically in both:

- `quaternion` (current default): mouse dragging rotates freely, like a trackball, and any up vector is honored.
- `euler`: mouse dragging works like a turntable that keeps `z` vertical on the screen, so a custom up vector only takes effect when looking along `±z`.

Other view controls in the same section:

- `Center` centers the camera on the plotted cells.
- `Orthographic projection` switches between orthographic projection (the default, where parallel lines stay parallel, convenient to inspect crystal structures) and perspective projection.

#### Atoms and bonds

The `Structure` section of the Wave function controls shows the crystal structure in ball-and-stick style. Its checkboxes toggle the atoms, their names, the bonds and the cell boundaries.

**Bonds.** Two atoms are bonded when their distance is at most `Bond tolerance` (default 1.15) times the sum of their covalent radii. This is the criterion used by [ASE](https://wiki.fysik.dtu.dk/ase/ase/neighborlist.html), Jmol and VESTA. The covalent radii are those of Cordero *et al.*, [Dalton Trans. 2832 (2008)](https://doi.org/10.1039/B801115J). Raise the tolerance to include longer bonds, and lower it to drop them. Bonds to atoms of neighbouring cells are found too, so periodic structures are fully connected.

Each atom draws its own half of each of its bonds, from its center to the bond midpoint:

- A bond between two atoms inside the supercell is drawn whole, in two halves.
- A bond to an atom outside the supercell is drawn only up to its midpoint. Atoms at the boundary thus show their full coordination, without adding atoms beyond the supercell.

Bond controls:

- `Bond radius` (default 0.12 Å): the thickness of the bonds.
- `Bond color`: either each half in the color of its atom (`Atom colors`, the default, as in VESTA), or `Uniform grey`.

**Atom size.** Atoms are drawn with their covalent radius times `Atom radius scale` (default 0.5). A covalent radius is defined so that a bond length is about the sum of the radii of its two atoms. At scale 1, bonded atoms therefore touch each other, and their bonds are hidden inside them. Smaller scales reveal a bond's length times about `1 - scale`.

The size of the spheres has no physical meaning, so choose it for what you want to see:

- Small atoms hide less of the wave function and show the bonds clearly.
- Scales close to 1, with the bonds off, show how the atoms pack, e.g. the van der Waals gaps of layered materials.

**Units.** Lengths are in Bohr internally, as read from the Yambo databases. Lengths shown to the user, such as the bond radius and the cell parameters, are in Å.

#### Axes gizmo and cell parameters

The axes gizmo in the lower-left corner of the 3D view follows the orientation of the camera and shows, as 3D arrows with labels at their tips:

- **Cartesian axes** `x`, `y`, `z`: thin grey arrows.
- **Lattice vectors** `a`, `b`, `c`: bold red, green and blue arrows, as in VESTA.
- **Reciprocal vectors** `a*`, `b*`, `c*`: light red, green and blue arrows, off by default. Each of them is perpendicular to the other two lattice vectors, e.g. `a*` to `b` and `c`. They help to interpret the views along the normals to `(hkl)` planes.

Scene coordinates are in Bohr, so the lattice vectors are about an order of magnitude longer than the Cartesian unit vectors. Since the gizmo has a fixed size, each set of arrows is scaled separately: the longest arrow of each set has the same length. Directions, angles and length ratios within a set are preserved, so an elongated cell still looks elongated. Lengths are not comparable between sets, and their actual values are shown in the cell parameters box.

The **cell parameters** box in the top-left corner of the 3D view shows the lattice constants `a`, `b`, `c` (in Å) and the angles `α`, `β`, `γ`. When the reciprocal vectors are shown, it also shows `a*`, `b*`, `c*` (in Å⁻¹, including the factor 2π) and the angles `α*`, `β*`, `γ*`.

Arrows pointing towards or away from the viewer look short, since they are seen foreshortened. Their labels may overlap the center of the gizmo.

All of this can be toggled from the `Axes` section of the Wave function controls:

- `Cartesian axes x, y, z`
- `Lattice vectors a, b, c`
- `Reciprocal vectors a*, b*, c*`
- `Axis labels`
- `Cell parameters`

#### Analysis

The `Analysis` section of the Wave function controls shows two analyses of the last wave function computed in the Analysis panel, below the 3D view in the presets. Check `Show the analysis panel` to open it (closing the panel unticks it).

**Plane cut.** The probability density on a plane, as a map in the colormap of the 3D view, with a color bar (values relative to the maximum of the density in the supercell). The plane goes through the fixed particle (★), or parallel to it at the chosen `Offset` along its normal. Its normal is given in the `Plane normal in` basis, as for the view directions: Cartesian, lattice `[uvw]`, or reciprocal `(hkl)` for the lattice plane `(hkl)` (e.g. a layer of a layered material). `Perpendicular to the view` takes the plane of the screen, and orients the map as the 3D view. The density is interpolated linearly between the points of its grid; the parts of the plane outside the supercell are left blank. Atoms closer to the plane than `Atoms within` are drawn on it, fainter the farther they are. With `Show the plane in the 3D view`, the plane is drawn as an orange polygon where it cuts the supercell.

**Distance distribution.** The distribution of the distance between the free particle and the fixed one: with the hole fixed, of the electron-hole distance. It shows the probability per unit distance P(r) and, on the right axis, the probability within each distance, with the mean and the distance within which 90% of the probability lies; their values, with the root mean square and the median, are given below. They measure the size (radius) of the exciton.

These distances only cover the part of the exciton inside the supercell. When the density is still significant at its edges (above 2% of its maximum), the exciton does not fit in it: the distances are underestimated, and a warning suggests computing it with a larger supercell. Increase the supercell until the warning disappears and the distances stop changing.

The analysis settings are remembered between sessions.

#### Export

The `Export` section of the Wave function controls, or the `File` menu, saves what is in the Wave function panel:

- **Image…** (`Ctrl+E`): the 3D view as a PNG, JPEG or TIFF image, at 1 to 4 times the size of the view on screen or at a custom width (the height keeps the proportions of the view). It shows exactly what the view shows, rendered again at the chosen size: surfaces, atoms and labels are sharp, and lines are widened in proportion. The axes gizmo and the cell parameters can be included. With `Transparent background` (PNG and TIFF), only the scene is drawn, ready to be placed on slides or figures.
- **Density…** (`Ctrl+Shift+E`): the probability density of the last wave function computed, on its real-space grid, with the atoms of the supercell, as:
  - a Gaussian cube file (`.cube`, lengths in Bohr), or
  - an XCrySDen XSF file (`.xsf`, lengths in Å),

  which [VESTA](https://jp-minerals.org/vesta/en/), [VMD](https://www.ks.uiuc.edu/Research/vmd/), [XCrySDen](http://www.xcrysden.org/), [Ovito](https://www.ovito.org/) or [ParaView](https://www.paraview.org/) can open, e.g. to draw isosurfaces with their own tools. The grid covers the supercell from its origin, as in the 3D view; values are relative to the maximum of the density, in scientific notation so the tails are kept. The fixed particle is not an atom: its position, the exciton and the supercell are written in the comments of the file. The file is written in the background.

File names are suggested from the dataset and the exciton (e.g. `BiI3_Bulk_8x8x8_Q1_exciton1.cube`), in the folder of the last export.

## Future features

- Finite-Q band structure plots.
- Expand the tool to include electronic band structure plots.

## License

Visual Excitons is free software, licensed under the [GNU General Public License](LICENSE), version 2 or (at your option) any later version, the same license as [YamboPy](https://github.com/yambo-code/yambopy).
