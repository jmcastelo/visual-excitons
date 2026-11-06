# Visual Excitons

Within the framework of YamboPy, this is a GUI to explore exciton properties visually.

**UNDER DEVELOPMENT!**

## Dependencies

Visual Excitons depends on YamboPy for data calculations, on PySide6 for GUI elements, and on PyQtGraph for visualization, which requires PyOpenGL for OpenGL based 3D plots.

### YamboPy

"Create automatic workflows for yambo and quantum espresso using python. Work directly with netCDF databases. Do pre/post-processing, data analysis and plotting for yambo and quantum espresso."

- https://github.com/yambo-code/yambopy
- https://github.com/jmcastelo/yambopy/tree/ase-bz

### PySide6

"Qt for Python offers the official Python bindings for Qt, which enables you to use Python to write your Qt applications."

- https://doc.qt.io/qtforpython-6

### PyQtGraph

"PyQtGraph is a pure-python graphics and GUI library built on PyQt / PySide and numpy. It is intended for use in mathematics / scientific / engineering applications."

- https://www.pyqtgraph.org
- https://github.com/pyqtgraph/pyqtgraph

## How to develop?

Clone this repository, for example in `~/visual-excitons`:

```
git clone https://github.com/jmcastelo/visual-excitons.git ~/visual-excitons
```

Create virtual environment, activate it and install dependencies:

```
cd ~/visual-excitons
python -m venv .venv
source .venv/bin/activate
pip install pyside6 pyqtgraph pyopengl
```

Note that depending on the PyQtGraph version, you may need to install specific version 6.9.0 or 6.8.3 of PySide6. On this issue, see this [question](https://stackoverflow.com/questions/79678479/pyqtgraph-not-working-on-example-in-pythonguis-website-pyside6-with-pyqtgraph). Current versions (as of 01.2025) do **not** need this downgrade.

```
pip install --force-reinstall -v "pyside6==6.9.0"
```

Current development depends on the following YamboPy fork's branch:

- https://github.com/jmcastelo/yambopy/tree/ase-bz

So this dependency must be installed after cloning that fork, for example in `~/yambopy`:

```
git clone https://github.com/jmcastelo/yambopy ~/yambopy
```

and switching to that branch (ase-bz):

```
cd ~/yambopy
git switch ase-bz
```

Then, install it within the previously activated virtual environment:

```
pip install --editable . --config-settings editable_mode=compat
```

The last option of the previous command is useful for some IDEs to detect YamboPy's package, as noted [here](https://stackoverflow.com/questions/76301782/why-are-pycharm-and-pylance-not-detecting-packages-installed-in-editable-mode).

Since this version of YamboPy yields an error related to netCDF4, for versions of this last package greater than 1.7.1, we must downgrade it:

```
pip install --force-reinstall -v "netCDF4==1.7.1"
```

Finally, run Visual Excitons as follows:

```
python visual_excitons/main.py
```

## Usage instructions

Visual Excitons provides the user with three tabs: `Options`, `2D Graphs` and `3D Graphs`.

### Options

Within this tab you can select three directories where to find the relevant files containing the data of your calculations:

- **SAVE** Directory: contains a valid `ns.db1`. The Bravais lattice type (`ibrav` index and variant) and parameters should be automatically detected from it.
- **Diago** Directory: contains several valid `ndb.BS_diago_Q*` files corresponding to a Q-point each.
- **QP** Directory: contains a valid `ndb.QP` file.

Note that this set of files must be coherent, so they must correspond to calculations performed on the same system.

To each Bravais lattice type, a Brillouin zone corresponds, with a set of high-symmetry points which are identified by a label and three fractional coordinates relative to the reciprocal basis vectors, all displayed on a table. You can add and remove extra special points if you right-click on the table to open a corresponding action menu.

Also, you can choose a Q-path different from the default one, consistent with your calculations, by specifying the labels that identify the high-symmetry points, and possibly the extra special points you may have defined. Since interpolation of the relevant magnitudes is performed on this Q-path, the number of points comprising it or their density can be selected. When you are happy with your choices, press the `Set Q-Path` button.

#### Default datasets

By default, and for testing purposes, data files corresponding to a `BiI3` calculation (not included in the repository) are selected, the Q-path of which must be chosen as `LGZF` instead of the default one.

### 2D Graphs

This tab contains three customizable plots for the excitons, and several options and actions widgets. They are arranged on regions of the tab which can be resized and hidden by dragging the handle on the borders between regions.

- **Dispersion**:
  - Choose the number of excitons contributing to this graph on the text box and press the `Compute Dispersion` button.
  - Left-click on its points to plot their contribution to the absorption of the system.
  - Press the `CTRL` key while clicking to select a set of points whose absorption plots will be displayed together.

- **Absorption**:
  - The range and resolution (in eV) of this graph can be changed with associated text boxes.
  - You can filter by intensity the points corresponding to the excitons on the absorption curves.
  - Their labels can be toggled with the `Show Labels` button.

- **Band structure**:
  - Excitonic weights are displayed.
  - Only for Gamma points, at the moment.

The visual style of the graphs can be changed via a set of widgets on the right. You can explore them to customize the colors, widths, fonts, etc. of the axes, curves, points and the rest of the elements of the graphs.

Thanks to PyQtGraph, you can explore the 2D graphs using the mouse. Left-clicking on a graph and dragging you can move it, and with the wheel you can scale it proportionally on both axes. The same is true for each individual axis. Also, several plot options can be changed, and you can take some actions on the graphs too, by right-clicking on them, which opens a menu with the following entries:

- **View all**: resets the graph so that it is entirely shown within its frame.
- **X axis** and **Y axis**: change their range and invert them, among other actions.
- **Mouse Mode**: change behaviour of mouse left button between translation of the graph and selection of a portion of it.
- **Plot Options**: feel free to explore them!
- **Export**: allows exporting the plot to different formats (CSV, HDF5, Image File, Matplotlib Window or SVG).

### 3D Graphs

Currently under active development, this tabs plots 3D visualizations of the probability density of the wave function of excitons. Several types of plots are being developed: isosurfaces, isosurfaces-set and volumetric graphs.

#### Plot types and rendering

The `Plot parameters` group on the right controls how the probability density is displayed. Choose the display mode with `Plot type`; only the controls of the selected mode are shown:

- **Isosurface**: a single translucent surface at the level set with the `Iso level` slider, with lighting that reveals its 3D shape.
- **Isosurface set**: a number of nested translucent surfaces (`Number of levels`), evenly spaced between the lowest and highest density and colored with the viridis colormap. Their look is chosen with `Isosurface set style`:
  - `Lit, edges emphasized` (default): soft lighting gives shape cues, and the surfaces become more opaque near their outlines so nested shells remain distinguishable.
  - `Edges only (x-ray)`: no lighting, only the more opaque outlines. Lighter and more see-through.
- **Volumetric**: the density rendered as a translucent cloud, colored like the isosurfaces. Light is absorbed through it as through a fog whose thickness grows with the density, so dense regions look more opaque. Three controls apply:
  - `Volume opacity` (default 0.8): the opacity along the densest line of sight through the cloud. It means the same whatever the shape or extent of the density and the resolution of the grid. Low values give a light, see-through cloud, and high values a denser one.
  - `Volume contrast` (default 1.0): a power applied to the density before computing the opacity. Values above 1 fade the low-density tails so that the core stands out, and values below 1 bring the tails out. Colors keep following the actual density.
  - `Slices per voxel`: the rendering quality. The volume is drawn as a stack of slices, and more slices give a smoother result. It does not change the overall opacity.

Each isosurface type keeps its own transparency, set with `Isosurface opacity` and `Isosurface set opacity` respectively.

Translucent surfaces are drawn from back to front, and are re-sorted whenever the view is rotated, panned or zoomed. This way, overlapping and nested surfaces blend correctly from any viewpoint.

Atoms are drawn as lit spheres in their Jmol colors, sized by their covalent radii (see [Atoms and bonds](#atoms-and-bonds)). Their chemical symbols are shown as labels on the surface of each atom, facing the viewer. Labels behave like the rest of the scene: they scale with zoom, are hidden by atoms in front of them, and are tinted by translucent surfaces in front of them.

The 3D view uses antialiasing, so edges of atoms, lines and surfaces are smooth.

#### View directions

The `View` group on the right lets you look at the lattice and the wave function from well-defined directions, given either in Cartesian coordinates or in terms of the crystal lattice.

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

Other view controls in the same group:

- `Center view` centers the camera on the plotted cells.
- `Orthographic projection` switches between orthographic projection (the default, where parallel lines stay parallel, convenient to inspect crystal structures) and perspective projection.
- Checkboxes toggle the visibility of the lattice, the atom names and the cell boundaries.

#### Atoms and bonds

The `Atoms and bonds` group on the right shows the structure in ball-and-stick style.

**Bonds.** Two atoms are bonded when their distance is at most `Bond tolerance` (default 1.15) times the sum of their covalent radii. This is the criterion used by [ASE](https://wiki.fysik.dtu.dk/ase/ase/neighborlist.html), Jmol and VESTA. The covalent radii are those of Cordero *et al.*, [Dalton Trans. 2832 (2008)](https://doi.org/10.1039/B801115J). Raise the tolerance to include longer bonds, and lower it to drop them. Bonds to atoms of neighbouring cells are found too, so periodic structures are fully connected.

Each atom draws its own half of each of its bonds, from its center to the bond midpoint:

- A bond between two atoms inside the supercell is drawn whole, in two halves.
- A bond to an atom outside the supercell is drawn only up to its midpoint. Atoms at the boundary thus show their full coordination, without adding atoms beyond the supercell.

Bond controls:

- `View bonds`: toggles the bonds.
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

All of this can be toggled from the `Axes` group on the right:

- `Cartesian axes x, y, z`
- `Lattice vectors a, b, c`
- `Reciprocal vectors a*, b*, c*`
- `Axis labels`
- `Cell parameters`

## Future features

- Save and load configurations to disk.
- Finite-Q band structure plots.
- Expand the tool to include electronic band structure plots.