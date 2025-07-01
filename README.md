# visual-excitons
Within the framework of Yambopy, this is a GUI to explore exciton properties visually.

UNDER DEVELOPMENT!

### Dependencies

Yambopy:

"Create automatic workflows for yambo and quantum espresso using python. Work directly with netCDF databases. Do pre/post-processing, data analysis and plotting for yambo and quantum espresso."

- https://github.com/yambo-code/yambopy
- https://github.com/jmcastelo/yambopy/tree/ase-bz

PySide6:

"Qt for Python offers the official Python bindings for Qt, which enables you to use Python to write your Qt applications."

- https://doc.qt.io/qtforpython-6

PyQtGraph:

"PyQtGraph is a pure-python graphics and GUI library built on PyQt / PySide and numpy. It is intended for use in mathematics / scientific / engineering applications."

- https://www.pyqtgraph.org
- https://github.com/pyqtgraph/pyqtgraph

### How to develop?

Create virtual environment, activate it and install dependencies:

```
python -m venv .venv
source .venv/bin/activate
pip install pyside6 pyqtgraph
```

Current development depends on the following Yambopy fork's branch:

- https://github.com/jmcastelo/yambopy/tree/ase-bz

So this dependency must be installed after cloning that fork and switching to that branch (ase-bz). Then:

```
pip install --editable . --config-settings editable_mode=compat
```

Finally, run as follows:
```
python main.py
```