# Development

[← Documentation](../README.md#documentation)

How to set up a development copy, and the tests.

The architecture of the code (structure, data flows, threading, rendering, conventions and pitfalls) is explained in [architecture.md](architecture.md).

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
## Tests

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
