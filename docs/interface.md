# The main window

[← Documentation](../README.md#documentation)

The main window is made of panels:

- **System**: the data of a calculation, its crystal lattice and the Q-path.
- **Dispersion**, **Absorption** and **Band structure**: the excitonic spectra.
- **Wave function**: the exciton wave function in real space, with the crystal structure.
- **Composition**: where the selected exciton lives in reciprocal space and what it is made of (see [Composition of an exciton](composition.md)).
- **Analysis**: cuts of the wave function and the distribution of electron–hole distances (see [Analysis](wavefunction.md#analysis)).
- **Spectra controls** and **Wave function controls**: the parameters, made of collapsible sections. Click a section header to open or close it; the panel scrolls when its open sections do not fit.
- **Appearance**: the style of the 2D plots (see [Appearance of the plots](appearance.md)).

**Arranging the panels.** Drag a panel by its tab to put it next to another one, or onto it to make them tabs of one area; the drop indicators show where it will go. The button at the top right of a panel area floats it in its own window (or double-click its tab), and the cross closes it. A floating panel has an `Attach` button in its title bar that puts it back into the main window where it was: as a tab with the same panels, or on the same side of the same neighbour (next to a related panel when those are gone); `Layout › Attach floating panels` does it for all of them (closed panels stay closed, and open where they were when shown again). `View › Panels` shows or hides each panel.

The `Layout` menu arranges the panels for each step of the usual workflow, or shows all of them:

| Layout | Shortcut | Panels |
|---|---|---|
| System | `Ctrl+1` | System |
| Spectra | `Ctrl+2` | Dispersion, absorption, band structure, the composition of the selected exciton, the spectra controls and the Appearance panel |
| Wave function | `Ctrl+3` | Wave function, analysis (when on) and the wave function controls |
| Overview | `Ctrl+4` | All of them: the spectra on the left, the wave function in the middle, the controls, the Appearance and the System panel as tabs on the right |

Your own arrangements can be kept too: `Layout › Save layout as…` saves the current one under a name, which then appears in the `Layout` menu; `Layout › Delete layout` removes it. The arrangement of the panels is kept between restarts; it is not stored in session files, since it depends on your screen rather than on the data.

The status bar shows the dataset loaded (name, Bravais lattice and number of Q-points) and what is being computed.

**Calculations run in the background**, so the window stays usable while they run: you can rotate the 3D view, look at the spectra or change display settings meanwhile. The status bar shows the running calculation, its current stage (e.g. `Loading the wave functions`, `Real-space wave function`) with a progress bar, and how many more are queued. `Cancel` or `Esc` stops it and drops the queued ones; it stops within a fraction of a second. Calculations run one at a time, in the order requested; requesting the same kind of calculation again (e.g. editing the absorption range several times) replaces the queued one instead of piling up. Opening another dataset cancels the calculations on the previous one. Errors are reported in a dialog.

**Themes.** `View › Theme` switches between the `System` look, a `Light` theme and a `Dark` theme. The plots and the 3D view follow the theme: dark plots on the dark theme, light ones on the light theme. Curves that keep their default color follow it too; colors chosen in the Appearance panel are kept.

**Resuming where you left off.** The program opens with no dataset, on a start page with the recent sessions and datasets (see [Sessions](sessions.md)). What it keeps from the last time:

- The window: its size, the arrangement of the panels (and your saved layouts), the theme, and which sections of the control panels are open.
- Preferences: how the wave function is displayed (plot type, iso level, number of levels, style, opacities, volume settings), the view (basis, preset, direction and up vectors, side, projection), the structure (atoms, names, bonds and boundaries shown, atom and bond sizes, bond colors), the axes gizmo and cell parameters shown, whether bright excitons are labelled, and the `Appearance` of the 2D plots (lines, symbols, axes colors and fonts, legend, band structure fill and weight factor). Colors that were the theme's defaults follow the theme, so a style made on the dark theme still suits the light one.
- The parameters of each dataset, restored when it is opened again: its Q-path, the number of excitons of the dispersion, the absorption range, step and bright threshold, the exciton chosen (Q-point and index), the fixed particle with the positions of the hole and the electron, the supercell and the cutoff, and the view of the 3D scene (rotation, zoom and pan).

Each dataset keeps its own parameters: switching to another one and back, or opening it again later from `Open recent` or `Open dataset`, brings them back; a dataset opened for the first time starts from the defaults. Results (dispersion, spectra, wave function) are not kept this way: compute them again, with the parameters already set, or save a [session](sessions.md).
