# Sessions

[← Documentation](../README.md#documentation)

A session file (`.vxsession`) keeps a whole setup, to come back to it later or to share it: the dataset, its Q-path, all the parameters and display settings, the exact view of the 3D scene, the `Appearance` of the 2D plots (with the style of each curve, e.g. a color per absorption spectrum), the choices of the last figure and 3D image exports and, optionally, the computed results. What depends on your screen or habits is not in sessions: the layout of the panels, the theme, the zoom of the 2D plots (exported figures use the data ranges), the folder of the exports. Keep several sessions of the same dataset for different figures or excitons, e.g. one per exciton with its own view and colormap.

- The program opens with a start page, with `Open dataset…` and `Open session…` buttons and the recent sessions and datasets, one click away. `File › New session` (`Ctrl+N`) closes the dataset and its results and goes back to it; preferences (how the wave function and the plots are displayed) stay as they are, and the dataset keeps its parameters for when it is opened again.
- `File › Save session` (`Ctrl+S`) saves the current setup in its session file, or asks for one the first time; `Save session as…` (`Ctrl+Shift+S`) saves it in a new one. The name of the session is shown in the title of the window: `Untitled` until it is saved.
- `File › Open session…` (`Ctrl+Shift+O`) and `Open recent session` restore a session.
- Changes not yet saved in the session are marked with `*` after its name in the title: parameters, display settings, the view of the 3D scene, the Appearance of the plots and, when results are stored in sessions, new results. Undoing a change removes the mark; opening or closing sections, the layout of the panels and the theme are not part of a session, so they do not count. An `Untitled` session is marked only when it has results that would be lost: when results are stored in sessions and not kept between runs (see below); its parameters are kept with the dataset anyway. Closing the window, starting a new session, or opening another dataset or session, with unsaved changes asks whether to save them (`Save`, which asks for a file for an `Untitled` session), lose them (`Discard`) or go back (`Cancel`).
- `Store results in session files` (on by default, in `File › Results and storage…`) stores the computed results: dispersion, absorption spectra, band structure, the selected exciton and the wave function. Opening the session then shows them at once, without computing anything. The files stay small (the wave function is stored compressed, in single precision): e.g. 0.2 MB for a BiI3 session with all of them.

When a session is opened:

- If its dataset is no longer where it was (moved, or on another computer), you are asked to locate its folder.
- Its results are only shown if the databases are the same as when it was saved (same files, sizes and modification times; when the dataset was moved, the same files and sizes). Otherwise the parameters are restored, and the results can be computed again.

## Results kept between runs

Without saving a session, the results of each dataset are kept for the next time: when you open another dataset, start a new session or close the program, the results of the dataset open are kept, and they come back when it is opened again, from `Open dataset…`, the recent datasets or the start page: dispersion, absorption spectra, band structure, the selected exciton, its composition, symmetry and spin, the hole or electron density, and the wave function up to a size (100 MB by default; larger ones are computed again when needed).

- They are only shown if the databases did not change since (the same check as for sessions); otherwise they are dropped, and the status bar says so.
- A session opened with its own results shows those; a session saved without results gets the ones kept for its dataset.
- They take at most 1 GB in all by default: beyond that, the datasets not opened for longest lose theirs first.
- They are written when a dataset is left (or the program closed): results computed since a dataset was opened are lost if the program crashes.
- They are kept, one session file per dataset without preferences, in the cache folder of your system by default (on Linux `~/.cache/VisualExcitons/Visual Excitons/results`).

## Results and storage

`File › Results and storage…` gathers what is stored where:

- **Sessions**: `Store results in session files`.
- **Results kept between runs**: `Keep results between runs` (on by default; off, an `Untitled` session with results asks to be saved before they are lost), the space they may take in all (0.1 to 100 GB) and the largest wave function kept with them (it cannot exceed the total). What they take now, and `Clear` to forget them all. Lowering the space drops the datasets not opened for longest at once.
- **Symmetry matrices**: the representation matrices of the symmetry analysis of the Composition panel, kept for each dataset because they take a while to compute (about 12 s per symmetry operation for BiI3 8×8×8). What they take, and `Clear`.
- **Location**: the folder where both are kept (`Browse…`, or `Default` for the cache folder of your system). Changing it moves what is kept there to the new folder; if that fails (e.g. no space), nothing is moved and the folder in use stays.

The settings apply with `OK`; the `Clear` buttons act at once. They are preferences of the program, not part of sessions.

Opening another dataset leaves the current session for a new `Untitled` one: `Save session` then asks for a file, so that one setup never overwrites another. Session files are zip archives with a readable `session.json` and the results in `results.npz`.
