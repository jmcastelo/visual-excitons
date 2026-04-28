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

Currently under active development, this tabs plots 3D visualizations of the probability density of the wave function of excitons. Several types of plots are being developed: isosurfaces and volumetric graphs.

## Future features

- Save and load configurations to disk.
- Finite-Q band structure plots.
- Expand the tool to include electronic band structure plots.