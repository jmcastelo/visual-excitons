"""Ring around the selected exciton in the 2D plots."""

import pyqtgraph as pg
from PySide6.QtGui import QColor

# Orange: stands out against the light and dark plot backgrounds and the curve colors
HIGHLIGHT_COLOR = QColor(255, 140, 0)


class ExcitonHighlight:
    """
    Ring marking the selected exciton on a plot item. The plots are cleared on
    every redraw, so the ring is kept here and added back with `addTo`.
    """

    def __init__(self):
        self.item = pg.ScatterPlotItem(symbol='o', size=18, pxMode=True, brush=None,
                                       pen=pg.mkPen(HIGHLIGHT_COLOR, width=2.5))
        self.item.setZValue(100)  # above curves and points

    def setPositions(self, positions):
        if positions:
            xs, ys = zip(*positions)
            self.item.setData(x=list(xs), y=list(ys))
        else:
            self.item.setData(x=[], y=[])

    def addTo(self, plotItem):
        if self.item.scene() is None:
            plotItem.addItem(self.item)
