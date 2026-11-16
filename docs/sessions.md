# Sessions

[← Documentation](../README.md#documentation)

A session file (`.vxsession`) keeps a whole setup, to come back to it later or to share it: the dataset, its Q-path, all the parameters and display settings, the exact view of the 3D scene, the `Appearance` of the 2D plots (with the style of each curve, e.g. a color per absorption spectrum) and, optionally, the computed results. Keep several sessions of the same dataset for different figures or excitons, e.g. one per exciton with its own view and colormap.

- The program opens with a start page, with `Open dataset…` and `Open session…` buttons and the recent sessions and datasets, one click away. `File › New session` (`Ctrl+N`) closes the dataset and its results and goes back to it; preferences (how the wave function and the plots are displayed) stay as they are, and the dataset keeps its parameters for when it is opened again.
- `File › Save session` (`Ctrl+S`) saves the current setup in its session file, or asks for one the first time; `Save session as…` (`Ctrl+Shift+S`) saves it in a new one. The name of the session is shown in the title of the window: `Untitled` until it is saved.
- `File › Open session…` (`Ctrl+Shift+O`) and `Open recent session` restore a session.
- Changes not yet saved in the session are marked with `*` after its name in the title: parameters, display settings, the view of the 3D scene, the Appearance of the plots and, when results are stored in sessions, new results. Undoing a change removes the mark; opening or closing sections, the layout of the panels and the theme are not part of a session, so they do not count. An `Untitled` session is marked only when it has results, which would be lost (its parameters are kept with the dataset anyway), and only when results are stored in sessions. Closing the window, starting a new session, or opening another dataset or session, with unsaved changes asks whether to save them (`Save`, which asks for a file for an `Untitled` session), lose them (`Discard`) or go back (`Cancel`).
- `Store results in sessions` (on by default) stores the computed results: dispersion, absorption spectra, band structure, the selected exciton and the wave function. Opening the session then shows them at once, without computing anything. The files stay small (the wave function is stored compressed, in single precision): e.g. 0.2 MB for a BiI3 session with all of them.

When a session is opened:

- If its dataset is no longer where it was (moved, or on another computer), you are asked to locate its folder.
- Its results are only shown if the databases are the same as when it was saved (same files, sizes and modification times; when the dataset was moved, the same files and sizes). Otherwise the parameters are restored, and the results can be computed again.

Opening another dataset leaves the current session for a new `Untitled` one: `Save session` then asks for a file, so that one setup never overwrites another. Session files are zip archives with a readable `session.json` and the results in `results.npz`.
