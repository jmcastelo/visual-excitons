# Wave function

[← Documentation](../README.md#documentation)

Currently under active development, the Wave function panel plots 3D visualizations of the probability density of the wave function of excitons, together with the crystal structure.

## Computing the wave function

- **Exciton**: the `Q-point` (the file `ndb.BS_diago_Q<n>`) and the index of the `Exciton` at that Q-point, in increasing energy. Selecting an exciton in the spectra fills them in, and its energy is then shown below.
- **Calculation**:
  - `Fixed particle`: the hole or the electron, whose position is fixed while the probability density of the other one is computed.
  - `Position (a, b, c)`: its position in crystal coordinates of the unit cell. After computing, it is moved to the nearest point of the real-space grid of the wave function, as explained in the note shown below it.
  - `Supercell`: the number of unit cells along each lattice vector. Only odd sizes are allowed, so that the fixed particle sits in the central cell.
  - `Cutoff`: the plane-wave cutoff of the wave function, in Ry, which sets the resolution of the result: only the plane waves of the wave functions below it are used, and the real-space grid is the smallest one that holds them. The points per unit cell grow with the square root of the cutoff (for BiI3: 13, 18 and 24 along each lattice vector at 5, 10 and 20 Ry). `All plane waves` uses all those of the SAVE database, the finest grid possible (46 points for BiI3); beyond the cutoff of the DFT calculation there is nothing more to gain.

    The cutoff can also be given in `RL`, as in Yambo's input files: the number of reciprocal lattice vectors (G-vectors) of the SAVE database below it, counted from the shortest. The two fields follow each other. G-vectors come in shells of the same length, and a cutoff takes whole shells, so the RL count moves from shell to shell: typing a count inside a shell rounds it up to the end of that shell (the arrows step one shell up or down), and the cutoff in Ry is set just above that shell's energy. For WSe2, 10 Ry is 819 RL, and the next shell ends at 843 RL (10.086 Ry). Without a dataset, the RL field is empty.
  - Below the button, the size of the calculation is estimated as its parameters change: its grid, per unit cell and in the whole supercell, and the memory it needs at its peak, with the memory available. The estimate is computed from the shapes of the arrays involved (the wave functions of the bands of the exciton, the real-space arrays, the density and its display copies); it is an estimate within some tens of percent. Excitons degenerate with the one chosen (within 10 meV) are computed with it when `Sum degenerate states` is on (in the Exciton section, the same setting as in the Spectra controls' Selected exciton section), and multiply the memory; off, the exciton is computed alone. The Exciton section says which states the wave function shown sums and, when the setting has changed since it was computed, that it should be computed again. When the calculation would need more than 90% of the available memory, the estimate is shown in orange with ⚠, and `Compute wave function` asks before starting it.

    Part of the calculation runs over blocks of k-points, whose buffer can take gigabytes for fine grids and many degenerate states. The block size is reduced automatically to keep it within a quarter of the available memory: the result is the same (the sum over k-points is only split differently) and the time barely changes. For BiI3, exciton 10 (10 degenerate states) at the full cutoff needs about 3.5 GB instead of 8.8 GB. The memory available is read with [psutil](https://github.com/giampaolo/psutil) on Linux, Windows and macOS; without psutil, the estimate is shown without it.
  - Press `Compute wave function`. The wave functions of the dataset are loaded the first time only: later calculations on the same dataset, for other excitons, positions, supercells or cutoffs, skip that step and are several times faster.

## Plot types and rendering

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

## View directions

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

- `Center` centers the camera on what is shown: the middle of the box holding the visible atoms, bonds, cell boundaries and wave function. The view is also centered by itself when the supercell changes, when a dataset is opened, and when a newly computed wave function is first shown (not one restored from a session, which keeps its view); the zoom and direction are kept.
- `Orthographic projection` switches between orthographic projection (the default, where parallel lines stay parallel, convenient to inspect crystal structures) and perspective projection.

## Layers and the cell origin

The 3D view shows one periodic box of the crystal; which part of the crystal falls in it can be changed, without changing anything computed.

**Layers.** Monolayers are computed in a cell with a wide vacuum along one direction, and the layer often sits on a face of the cell (e.g. WSe2: W at c = 0, Se at c = ±0.07): the layer and its exciton are then drawn in two halves, at the bottom and the top of the cell. When the cell has such a vacuum (a gap between the atoms of at least 40% of the cell and 10 Å thick, or 5 Å along a direction with a single k-point, as in 2D calculations), `Centre the layer in the cell`, in the `Structure` section, puts the vacuum on the faces of the cell and the layer in the middle. It is on by default; untick it to see the cell of the calculation.

**Cell origin.** `Cell origin` shifts what is shown along a, b and c (in fractions of them): the atoms, bonds, wave function, fixed particle and analysis move together, wrapped in the cell. It is useful when what matters sits on the edges of the cell: a molecule or defect drawn in pieces, or an exciton whose fixed particle is near a face. `Centre on the fixed particle` puts the fixed particle in the middle; `Reset` goes back to the cell of the calculation (with the layer still centred, if ticked). While what is shown is shifted, the Calculation section has two linked rows for the fixed particle: `Position as shown`, where it is drawn, and `Position as computed`, the coordinates of the calculation (saved with the dataset); editing either updates the other. Typing c = 0.5 as shown in a centred monolayer thus puts the particle in the layer, not in the middle of the vacuum. Without a shift the two agree, and only one row is shown. The shift is rounded to whole points of the wave function's grid, and kept with the dataset and in sessions.

Wrapping the wave function is exact along directions where its supercell spans whole periods of the k-point grid (such as the vacuum direction of a monolayer: one cell, one k-point). Along others, the supercell is a window on a longer period: if the density has not decayed at its faces, the wrapped wave function shows a seam, and a note under the controls says so (a larger supercell along that direction avoids it). The analysis (plane cut and distance distribution) never wraps along such directions: it uses the wave function as computed there, so it shows no seam and its distances do not depend on the cell origin.

## Atoms and bonds

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

## Axes gizmo and cell parameters

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

## Analysis

The `Analysis` section of the Wave function controls shows two analyses of the last wave function computed in the Analysis panel, below the 3D view in the presets. Check `Show the analysis panel` to open it (closing the panel unticks it).

**Plane cut.** The probability density on a plane, as a map in the colormap of the 3D view, with a color bar (values relative to the maximum of the density in the supercell). The plane goes through the fixed particle (★), or parallel to it at the chosen `Offset` along its normal. Its normal is given in the `Plane normal in` basis, as for the view directions: Cartesian, lattice `[uvw]`, or reciprocal `(hkl)` for the lattice plane `(hkl)` (e.g. a layer of a layered material). `Perpendicular to the view` takes the plane of the screen, and orients the map as the 3D view. The density is interpolated linearly between the points of its grid; the parts of the plane outside the supercell are left blank. Atoms closer to the plane than `Atoms within` are drawn on it, fainter the farther they are. With `Show the plane in the 3D view`, the plane is drawn as an orange polygon where it cuts the supercell.

**Distance distribution.** The distribution of the distance between the free particle and the fixed one: with the hole fixed, of the electron-hole distance. It shows the probability per unit distance P(r) and, on the right axis, the probability within each distance, with the mean and the distance within which 90% of the probability lies; their values, with the root mean square and the median, are given below. They measure the size (radius) of the exciton.

Along directions where the wave function repeats with its supercell (e.g. the vacuum direction of a monolayer, computed on one cell with one k-point), distances are measured to the nearest periodic image: otherwise, with the fixed particle on a face of the cell, the part of the exciton across that face would count as far away. These distances only cover the part of the exciton inside the supercell. When the density is still significant at its edges (above 2% of its maximum), the exciton does not fit in it: the distances are underestimated, and a warning suggests computing it with a larger supercell. Increase the supercell until the warning disappears and the distances stop changing.

The analysis settings are remembered between sessions.

`Export figure…`, at the top right of the Analysis panel, draws the plane cut or the distance distribution (the tab shown, checked first) as a [publication figure](spectra.md#publication-figures) with Matplotlib: the density map in the same colormap with its atoms and the fixed particle, or P(r) with its cumulative and the mean and 90% distances. They can share a figure with the spectra and the k-space plots of the [Composition panel](composition.md).

## Export

The `Export` section of the Wave function controls, or the `File` menu, saves what is in the Wave function panel:

- **Image…** (`Ctrl+E`): the 3D view as a PNG, JPEG or TIFF image, at 1 to 4 times the size of the view on screen or at a custom width (the height keeps the proportions of the view). It shows exactly what the view shows, rendered again at the chosen size: surfaces, atoms and labels are sharp, and lines are widened in proportion. The axes gizmo and the cell parameters can be included. With `Transparent background` (PNG and TIFF), only the scene is drawn, ready to be placed on slides or figures.
- **Density…** (`Ctrl+Shift+E`): the probability density of the last wave function computed, on its real-space grid, with the atoms of the supercell (as shown, with the cell origin and the layer centring applied, or, unticking `Density as shown`, in the cell of the calculation), as:
  - a Gaussian cube file (`.cube`, lengths in Bohr), or
  - an XCrySDen XSF file (`.xsf`, lengths in Å),

  which [VESTA](https://jp-minerals.org/vesta/en/), [VMD](https://www.ks.uiuc.edu/Research/vmd/), [XCrySDen](http://www.xcrysden.org/), [Ovito](https://www.ovito.org/) or [ParaView](https://www.paraview.org/) can open, e.g. to draw isosurfaces with their own tools. The grid covers the supercell from its origin, as in the 3D view; values are relative to the maximum of the density, in scientific notation so the tails are kept. The fixed particle is not an atom: its position, the exciton and the supercell are written in the comments of the file. The file is written in the background.

File names are suggested from the dataset and the exciton (e.g. `BiI3_Bulk_8x8x8_Q1_exciton1.cube`), in the folder of the last export.
