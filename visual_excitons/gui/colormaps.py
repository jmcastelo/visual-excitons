"""
Colormaps of the probability density (isosurfaces and volume).

The density is never negative, so only sequential colormaps are offered: most
of them perceptually uniform (equal steps in density look like equal steps in
color), from matplotlib and from Peter Kovesi's CET collection, both shipped
with PyQtGraph.
"""

import copy

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QIcon, QImage, QPixmap

DEFAULT_COLORMAP = 'Viridis'

# (group, [(label, PyQtGraph name, description)])
COLORMAP_GROUPS = [
    ('Perceptually uniform', [
        ('Viridis', 'viridis', 'Blue to yellow (default)'),
        ('Plasma', 'plasma', 'Blue to purple to yellow'),
        ('Inferno', 'inferno', 'Black to red to pale yellow; low densities nearly black'),
        ('Magma', 'magma', 'Black to pink to pale yellow; low densities nearly black'),
        ('Cividis', 'cividis', 'Blue to yellow, readable with color-vision deficiencies'),
    ]),
    ('Others', [
        ('Fire', 'CET-L3', 'Black to red to yellow to white'),
        ('Blues', 'CET-L12', 'Pale to deep blue, low densities light'),
        ('Sunset', 'CET-L17', 'Cream to orange to purple, low densities light'),
        ('Blue-magenta-yellow', 'CET-L8', 'Dark blue to magenta to yellow'),
        ('Greys', 'CET-L1', 'Black to white'),
        ('Turbo', 'turbo', 'Rainbow, improved: high contrast but not perceptually uniform'),
    ]),
]

COLORMAPS = {label: (name, description) for group, maps in COLORMAP_GROUPS for label, name, description in maps}


def makeColormap(label=DEFAULT_COLORMAP, reverse=False):
    """The ColorMap of `label` (see COLORMAPS), reversed if requested; viridis for unknown labels."""
    name = COLORMAPS.get(label, COLORMAPS[DEFAULT_COLORMAP])[0]
    # A copy: reversing must not change the colormap shared by PyQtGraph
    colormap = copy.deepcopy(pg.colormap.get(name))
    if reverse:
        colormap.reverse()
    return colormap


def colormapIcon(colormap, width=64, height=14):
    """A horizontal gradient of `colormap`, low densities on the left."""
    lut = np.ascontiguousarray(colormap.getLookupTable(0.0, 1.0, width, alpha=False)[:, :3], dtype=np.uint8)
    rows = np.ascontiguousarray(np.repeat(lut[None, :, :], height, axis=0))
    image = QImage(rows.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
    return QIcon(QPixmap.fromImage(image))
