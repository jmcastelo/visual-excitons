"""
Analysis panel below the 3D view: the density on a plane, and the
distribution of distances from the fixed particle. Lengths shown in angstrom.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QTabWidget, QWidget, QVBoxLayout, QLabel

from visual_excitons.core.atomic_data import BOHR_TO_ANGSTROM, chemical_symbols, jmol_colors, covalent_radii
from .theme import PLOT_COLORS
from .inspector import NoteLabel

# Above this density on the faces of the supercell (relative to the maximum),
# the supercell cuts the exciton noticeably
TRUNCATION_WARNING = 0.02


class AnalysisWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self.dark = False
        self.plots = []

        # Plane cut

        self.cutPlot = pg.PlotWidget()
        self.cutPlot.setAspectLocked(True)
        self.cutPlot.setLabel('bottom', 'along u', units='Å')
        self.cutPlot.setLabel('left', 'along v', units='Å')
        self.image = pg.ImageItem(axisOrder='row-major')
        self.cutPlot.addItem(self.image)
        self.colorBar = pg.ColorBarItem(values=(0, 1), interactive=False, label='Density (relative to its maximum in the supercell)')
        self.colorBar.setImageItem(self.image, insert_in=self.cutPlot.getPlotItem())
        self.atomsItem = pg.ScatterPlotItem(pxMode=False)
        self.cutPlot.addItem(self.atomsItem)
        self.atomLabels = []
        self.particleItem = pg.ScatterPlotItem(symbol='star', size=16, brush=pg.mkBrush('w'), pen=pg.mkPen('k', width=1.2))
        self.particleItem.setZValue(10)
        self.cutPlot.addItem(self.particleItem)
        self.cutNote = NoteLabel()
        self.plots.append(self.cutPlot)

        cutTab = QWidget()
        layout = QVBoxLayout(cutTab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.cutPlot, 1)
        layout.addWidget(self.cutNote)
        self.addTab(cutTab, 'Plane cut')

        # Distance from the fixed particle

        self.radialPlot = pg.PlotWidget()
        self.radialPlot.setLabel('bottom', 'Distance from the fixed particle', units='Å')
        self.radialPlot.setLabel('left', 'Probability per Å')
        self.radialPlot.showAxis('right')
        self.radialPlot.setLabel('right', 'Probability within the distance')
        self.radialCurve = self.radialPlot.plot()
        # Cumulative probability on the right axis, in its own view box
        self.cumulativeView = pg.ViewBox()
        self.radialPlot.getPlotItem().scene().addItem(self.cumulativeView)
        self.radialPlot.getAxis('right').linkToView(self.cumulativeView)
        self.cumulativeView.setXLink(self.radialPlot.getPlotItem())
        self.cumulativeView.setYRange(0, 1.02, padding=0)
        self.cumulativeView.setMouseEnabled(x=False, y=False)
        self.cumulativeCurve = pg.PlotCurveItem()
        self.cumulativeView.addItem(self.cumulativeCurve)
        self.radialPlot.getPlotItem().vb.sigResized.connect(self._syncCumulativeView)
        self.meanLine = pg.InfiniteLine(angle=90, movable=False, label='mean', labelOpts={'position': 0.92})
        self.r90Line = pg.InfiniteLine(angle=90, movable=False, label='90%', labelOpts={'position': 0.92})
        for line in (self.meanLine, self.r90Line):
            self.radialPlot.addItem(line)
        self.plots.append(self.radialPlot)

        self.statistics = QLabel()
        self.statistics.setTextFormat(Qt.TextFormat.RichText)
        self.statistics.setWordWrap(True)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet('color: #d9822b')
        self.warning.hide()

        radialTab = QWidget()
        layout = QVBoxLayout(radialTab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.radialPlot, 1)
        layout.addWidget(self.statistics)
        layout.addWidget(self.warning)
        self.addTab(radialTab, 'Distance distribution')

        self.setDarkTheme(False)
        self.clear()

    def _syncCumulativeView(self):
        self.cumulativeView.setGeometry(self.radialPlot.getPlotItem().vb.sceneBoundingRect())

    # Content

    def clear(self, message='Compute a wave function to analyse it.'):
        self.image.clear()
        self.atomsItem.clear()
        self.particleItem.clear()
        for label in self.atomLabels:
            self.cutPlot.removeItem(label)
        self.atomLabels.clear()
        self.cutNote.setText(message)
        self.radialCurve.setData([], [])
        self.cumulativeCurve.setData([], [])
        self.statistics.setText(message)
        self.warning.hide()

    def setColormap(self, colormap):
        self.colorBar.setColorMap(colormap)

    def showCut(self, cut, atoms, particleLabel, offset):
        """
        `cut` from analysis.planeCut; `atoms`: (numbers, in-plane positions,
        distances to the plane) from analysis.atomsNearPlane, lengths in Bohr.
        """
        values = cut['values']
        s, t = cut['s'] * BOHR_TO_ANGSTROM, cut['t'] * BOHR_TO_ANGSTROM
        step = (s[1] - s[0]) if len(s) > 1 else 1.0
        self.image.setImage(values, autoLevels=False)
        self.image.setRect(QRectF(s[0] - step / 2, t[0] - step / 2, s[-1] - s[0] + step, t[-1] - t[0] + step))
        maximum = float(np.nanmax(values)) if np.isfinite(values).any() else 1.0
        self.colorBar.setLevels((0.0, maximum if maximum > 0 else 1.0))

        # Atoms near the plane, fainter the farther they are from it
        for label in self.atomLabels:
            self.cutPlot.removeItem(label)
        self.atomLabels.clear()
        numbers, positions, distances = atoms
        positions = np.asarray(positions) * BOHR_TO_ANGSTROM
        tolerance = max(np.abs(distances).max(), 1e-9) if len(distances) else 1.0
        spots = []
        for z, (x, y), d in zip(numbers, positions, distances):
            alpha = int(255 * (1.0 - 0.6 * abs(d) / tolerance))
            color = [int(255 * c) for c in jmol_colors[z]]
            spots.append({'pos': (x, y), 'size': covalent_radii[z], 'brush': pg.mkBrush(*color, alpha),
                          'pen': pg.mkPen(0, 0, 0, alpha, width=1)})
            label = pg.TextItem(chemical_symbols[z], anchor=(0.5, 0.5), color=(255, 255, 255, alpha))
            label.setPos(x, y)
            self.cutPlot.addItem(label, ignoreBounds=True)
            self.atomLabels.append(label)
        self.atomsItem.setData(spots)

        # The fixed particle, at the origin of the in-plane coordinates when the
        # plane goes through it
        if abs(offset) < 1e-9:
            self.particleItem.setData([0.0], [0.0])
        else:
            self.particleItem.clear()
        self.cutNote.setText(f'Plane through the {particleLabel}' + (f', shifted {offset * BOHR_TO_ANGSTROM:+.2f} Å '
                             'along its normal' if abs(offset) > 1e-9 else ' (★)') +
                             '. Atoms within the chosen distance of the plane are shown, fainter the farther they are.')
        # Continuous: also right when the panel is shown or resized later
        self.cutPlot.getPlotItem().enableAutoRange()

    def showRadial(self, result, particleLabel):
        """`result` from analysis.radialDistribution (lengths in Bohr)."""
        r = result['r'] * BOHR_TO_ANGSTROM
        self.radialCurve.setData(r, result['probability'] / BOHR_TO_ANGSTROM, stepMode=None)
        self.cumulativeCurve.setData(r, result['cumulative'])
        self.meanLine.setValue(result['mean'] * BOHR_TO_ANGSTROM)
        self.r90Line.setValue(result['r90'] * BOHR_TO_ANGSTROM)
        self.radialPlot.getPlotItem().enableAutoRange()

        other = 'electron' if particleLabel == 'hole' else 'hole'
        a = BOHR_TO_ANGSTROM
        self.statistics.setText(
            f'Distance of the {other} from the {particleLabel}: mean <b>{result["mean"] * a:.2f} Å</b>, '
            f'root mean square {result["rms"] * a:.2f} Å, median {result["median"] * a:.2f} Å; '
            f'90% of the probability within {result["r90"] * a:.2f} Å.')
        if result['boundary'] > TRUNCATION_WARNING:
            self.warning.setText(f'The density is still {100 * result["boundary"]:.0f}% of its maximum at the edge of '
                                 'the supercell: the exciton does not fit in it, so these distances are '
                                 'underestimated. Compute it with a larger supercell.')
            self.warning.show()
        else:
            self.warning.hide()

    # Theme

    def setDarkTheme(self, dark: bool):
        self.dark = dark
        colors = PLOT_COLORS[dark]
        foreground, background = colors['foreground'], colors['background']
        for plot in self.plots:
            plot.setBackground(background)
            for name in ('left', 'bottom', 'right'):
                axis = plot.getAxis(name)
                axis.setPen(foreground)
                axis.setTextPen(foreground)
        self.radialCurve.setPen(pg.mkPen((70, 130, 230), width=2))
        self.cumulativeCurve.setPen(pg.mkPen(foreground, width=1.5, style=Qt.PenStyle.DashLine))
        for line, color in ((self.meanLine, (230, 120, 30)), (self.r90Line, (150, 150, 150))):
            line.setPen(pg.mkPen(color, width=1.5, style=Qt.PenStyle.DotLine))
            line.label.setColor(color)
        self.colorBar.axis.setPen(foreground)
        self.colorBar.axis.setTextPen(foreground)
