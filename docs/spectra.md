# Spectra

[← Documentation](../README.md#documentation)

Three panels plot the excitonic dispersion, the absorption spectra and the band structure (side by side in the `Spectra` layout, with the dispersion above the band structure).

Spectra controls:

- **Dispersion**: choose the number of excitons and press `Compute dispersion`. Then click a point of the dispersion to plot the absorption spectrum at its Q-point; `Ctrl`-click to keep several spectra together. Clicking a point also selects its exciton (see **Selected exciton** below).
- **Absorption**: `Q-point` and `Add spectrum` show the spectrum of a computed Q-point chosen by its number, e.g. one off the Q-path, with those shown. The energy range and step of the spectra (in eV), and the `Bright threshold`. With `Automatic range` (the default), each spectrum spans the energies of its own excitons, plus a margin of 0.5 eV (five times the broadening of the peaks) on both sides; the range of the spectra plotted is shown below. Untick it to set the range by hand with `From` and `To`. Excitons with at least this intensity (relative to the brightest) are marked as bright points on the spectrum; the rest, as dark bars below it. `Label bright excitons` shows the index and intensity of each bright exciton.
- **Selected exciton**: click an exciton on the dispersion, or a bright exciton on an absorption spectrum, to select it. It is marked with an orange ring on both plots (on the absorption spectrum, when it is bright there). Its index, Q-point and energy are shown here and in the status bar, and the exciton is selected in the Wave function controls too. `Sum degenerate states` (on by default) adds the states degenerate with the exciton (within 10 meV) to everything about it: its wave function, its [composition](composition.md) and its band structure. A single state of a degenerate group is an arbitrary mixture of them, without the symmetry of the crystal; the setting is kept with the dataset and in sessions, and a copy of it is in the Wave function controls. `Show its composition` opens the [Composition](composition.md) panel: where it lives in reciprocal space and what it is made of. `Compute its wave function` computes it with the settings of the Wave function controls (fixed particle and position, supercell, cutoff) and brings the Wave function panel to the front. The memory it needs is shown below the button, with the settings used; as for `Compute wave function`, it is shown in orange with ⚠ when it likely does not fit in the memory available, and the program asks before starting it.
- **Export**: `Export figure…` (also `File › Export 2D figure…`, `Ctrl+Shift+F`) makes publication figures of the plots, drawn with [Matplotlib](https://matplotlib.org) (see [Publication figures](#publication-figures)).

## Publication figures

The export dialog draws the plots with Matplotlib, as figures for papers, with the colors, line styles and symbols set in the [Appearance panel](appearance.md), and shows a preview:

- **Panels**: the dispersion, the absorption spectra and the band structure (those computed), alone or combined, in the order of the list (drag them to reorder), in a row or in a column, with panel letters (a), (b)... With `Dispersion and absorption on one energy axis`, the absorption is drawn rotated next to the dispersion, sharing its energy axis, over the range of the dispersion and of the bright excitons.
- **Size**: in cm, with the widths of one column (8.6 cm), one and a half (12.9 cm) and two columns (17.8 cm) of usual two-column journals, or any other.
- **Fonts**: DejaVu Sans or Serif, STIX (similar to Times) or Computer Modern (as LaTeX), and their size in points.
- **Contents**: the legend of the spectra, the bright (in their colors) and dark (in grey) excitons below the absorption, the index of the bright excitons, a ring around the selected exciton, typeset path labels (Γ for G, Greek letters, subscripts and primes, e.g. Σ₁ and K′), titles.
- **Files**: `Save figure…` saves it as PDF, SVG or EPS (vector graphics, best for papers) or PNG or TIFF at the chosen resolution. `Save as script…` saves a Python script and its data file (`.npz`) that recreate the figure with Matplotlib: edit its options (size, fonts, panels...) or its code, and run it with `python`. It does not need Visual Excitons, only NumPy and Matplotlib, so it can be kept with a paper and adapted to a journal's style.

The figures use the data as computed: e.g. the absorption spectra are sampled every `Step` of the `Absorption` section, which shows as straight segments when the shared energy axis zooms into them; use a smaller step for smoother curves. The last options of the dialog are remembered.

## Band structure

The excitonic band structure of the excitons selected (clicked on the dispersion, or on an absorption spectrum, `Ctrl`-click for several), at their Q-point, Γ or any other computed one: the electronic bands along the Q-path, DFT or quasiparticle (with GW), each drawn as wide as the weight of the excitons on it. Its title says the Q-point; hover over the plot for how to read it.

- At Γ the electron and the hole are at the same k-point: a transition at k weighs on its valence and conduction bands at k.
- At a finite Q, a transition takes the hole from the valence band at k−Q to the conduction band at k. So the width of a **valence** band at k is the weight of the **hole** at k (transitions to the electron at k+Q), and that of a **conduction** band at k the weight of the **electron** at k. The two can be at different places of the path, or the hole's off it (see the hole's map in the [Composition](composition.md) panel).
- With `Sum degenerate states` (see **Selected exciton** above), the states degenerate with each exciton clicked are added to it.
- The weights of several excitons are added up and divided by their number.
- With GW, bands outside the range of the QP database (e.g. a BSE band below its first band) get their DFT energy corrected as the nearest band of the database, at each k-point; the plot's tooltip names them.

How the energies and the weights are interpolated along the path, and why, is explained in the [architecture notes](architecture.md#excitonic-band-structure-interpolation).

## Exploring the plots

Thanks to PyQtGraph, you can explore the 2D graphs using the mouse. Left-clicking on a graph and dragging you can move it, and with the wheel you can scale it proportionally on both axes. The same is true for each individual axis. Also, several plot options can be changed, and you can take some actions on the graphs too, by right-clicking on them, which opens a menu with the following entries:

- **View all**: resets the graph so that it is entirely shown within its frame.
- **X axis** and **Y axis**: change their range and invert them, among other actions.
- **Mouse Mode**: change behaviour of mouse left button between translation of the graph and selection of a portion of it.
- **Plot Options**: feel free to explore them!
- **Export**: allows exporting the plot to different formats (CSV, HDF5, Image File, Matplotlib Window or SVG).
