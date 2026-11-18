# Visual Excitons

Visual Excitons is a graphical program to explore the excitons computed with [Yambo](https://www.yambo-code.eu/), reading its databases through [YamboPy](https://github.com/yambo-code/yambopy). It plots the excitonic dispersion along a path of the Brillouin zone, the absorption spectra at each Q-point and the excitonic band structure at any Q-point, and shows where an exciton lives in reciprocal space and what it is made of. It also computes and draws the wave function of a chosen exciton in real space, as isosurfaces or a volume, together with the crystal structure, and analyses its size.

Its panels can be arranged freely, or by layouts for each step of the work. Calculations run in the background, and whole setups can be saved as session files. The 2D plots, the k-space plots of an exciton and the analysis of its wave function can be exported as publication figures, or as Matplotlib scripts that recreate them, and the 3D view as images or density files for VESTA and similar programs.

**Under development.**

## Quick start

```
python -m venv visual-excitons-env
source visual-excitons-env/bin/activate        # on Windows: visual-excitons-env\Scripts\activate
pip install git+https://github.com/jmcastelo/visual-excitons.git
visual-excitons
```

See [Installation](docs/installation.md) for the requirements and the YamboPy fork it uses.

## Documentation

Using the program:

- [Installation](docs/installation.md): requirements, dependencies and installing.
- [The main window](docs/interface.md): the panels and how to arrange them, layouts, background calculations, themes, and what is resumed on start.
- [Datasets and the System panel](docs/datasets.md): opening the databases of a calculation, how they are recognised and checked, partial calculations, the crystal lattice and the Q-path.
- [Spectra](docs/spectra.md): dispersion, absorption and band structure (at any Q), selecting excitons, and publication figures.
- [Composition of an exciton](docs/composition.md): where the selected exciton lives in reciprocal space (a map of its k-points, in 3D for bulk crystals), what it is made of (band pairs, bands, k-points), and its symmetry and spin, at Γ or finite Q.
- [Appearance of the plots](docs/appearance.md): colors, lines, symbols, axes and legend of the 2D plots.
- [Wave function](docs/wavefunction.md): computing it, plot types and colormaps, view directions, layers and the cell origin, atoms and bonds, analysis and export.
- [Sessions](docs/sessions.md): saving and opening whole setups, with their results.

Working on the program:

- [Development](docs/development.md): setting up a development copy, and the tests.
- [Architecture](docs/architecture.md): how the code is organised, data flows, threading, rendering, conventions and pitfalls.
- [YamboPy issues](docs/yambopy-issues.md): problems found in YamboPy, written to be filed as GitHub issues (and the fixes offered).

## Future features

- Expand the tool to include electronic band structure plots.

## License

Visual Excitons is free software, licensed under the [GNU General Public License](LICENSE), version 2 or (at your option) any later version, the same license as [YamboPy](https://github.com/yambo-code/yambopy).
