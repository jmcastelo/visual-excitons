# Installation

[← Documentation](../README.md#documentation)

## Dependencies

Visual Excitons depends on YamboPy for data calculations, on PySide6 for GUI elements, with PySide6-QtAds for its dockable panels, and on PyQtGraph for visualization, which requires PyOpenGL for OpenGL based 3D plots. It also uses NumPy, SciPy and netCDF4, and psutil to tell the memory available. They are all installed with it (see [Installing](#installing)).

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

## Installing

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
