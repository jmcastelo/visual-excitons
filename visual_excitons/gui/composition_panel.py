"""
The Composition panel: where the selected exciton lives in reciprocal space
(a map of the weights of its k-points, on a plane or, for bulk crystals, in
the Brillouin zone in 3D) and what it is made of (band pairs, bands and
k-points), from Calculations.composition.
"""

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PySide6.QtCore import Qt, Signal, Slot, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QPainter, QPicture, QPolygonF, QPen, QBrush, QQuaternion
from PySide6.QtWidgets import (QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
                               QSpinBox, QDoubleSpinBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QHeaderView, QSizePolicy, QAbstractItemView, QSplitter)

from visual_excitons.core.kspace import (planeMap, planeIndices, zonePoints, nearestSpecialPoint, planeBasis,
                                         TO_INVERSE_ANGSTROM)
from visual_excitons.core.options import tickLabels
from .persistence import PersistentState, GLOBAL, DATASET
from .colormaps import COLORMAP_GROUPS, DEFAULT_COLORMAP, makeColormap, colormapIcon
from .axes_3d_widget import AxisGizmo
from .inspector import NoteLabel
from .theme import PLOT_COLORS
from .gl_style import (OPAQUE_STAGE, LABEL_STAGE, TRANSLUCENT_STAGE, OPAQUE_GL_OPTIONS, TRANSLUCENT_GL_OPTIONS,
                       headlightShader, enableMultisampling, spheresMeshData)
from .sorted_mesh_item import SortedMeshItem

PARTICLES = ['Electron', 'Hole', 'Electron + hole']
# Smallest weight shown on the logarithmic scale (relative to the largest)
LOG_FLOOR = 1e-3
# Rows of the tables of band pairs and k-points
TOP_ROWS = 12


class TileMapItem(pg.GraphicsObject):
    """One polygon (`tile`, around each point) per point, filled with its color."""

    def __init__(self):
        super().__init__()
        self.picture = QPicture()
        self.bounds = QRectF()

    def setData(self, points, tile, colors, clip=None):
        """`clip`: a polygon (the zone) outside which nothing is drawn."""
        self.picture = QPicture()
        painter = QPainter(self.picture)
        painter.setPen(Qt.PenStyle.NoPen)
        if clip is not None and len(clip) >= 3:
            from PySide6.QtGui import QPainterPath
            path = QPainterPath()
            path.addPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in clip]))
            path.closeSubpath()
            painter.setClipPath(path)
        shape = [QPointF(float(x), float(y)) for x, y in tile]
        for (x, y), color in zip(points, colors):
            painter.setBrush(QBrush(QColor(int(color[0]), int(color[1]), int(color[2]))))
            painter.drawPolygon(QPolygonF([QPointF(p.x() + x, p.y() + y) for p in shape]))
        painter.end()
        if len(points):
            extent = np.abs(np.asarray(tile)).max()
            low, high = np.min(points, axis=0) - extent, np.max(points, axis=0) + extent
            self.bounds = QRectF(low[0], low[1], high[0] - low[0], high[1] - low[1])
        else:
            self.bounds = QRectF()
        self.prepareGeometryChange()
        self.update()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return self.bounds


class KSpaceView(gl.GLViewWidget):
    """The Brillouin zone in 3D: its edges, special points, Q-path and the k-points as spheres."""

    def __init__(self, parent=None):
        # Quaternions, as the real-space view: free rotation, and a camera state to keep
        super().__init__(parent, rotationMethod='quaternion')
        enableMultisampling(self)
        self.gizmo = None
        self.items3D = []

    def attachGizmo(self, gizmo, margin=10):
        self.gizmo = gizmo
        gizmo.margin = margin
        gizmo.setParent(self)
        self.repositionGizmo()
        gizmo.show()
        gizmo.raise_()

    def repositionGizmo(self):
        if self.gizmo is not None:
            self.gizmo.move(self.gizmo.margin, self.height() - self.gizmo.height() - self.gizmo.margin)

    def paint(self, **kwargs):
        # glClear() respects the depth write mask, which the translucent spheres
        # (drawn last) turn off: without this, the next frame would not clear the
        # depth buffer, and everything would fail the depth test (as in
        # ExcitonWfWidget.paint)
        from OpenGL import GL
        GL.glDepthMask(GL.GL_TRUE)
        super().paint(**kwargs)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.repositionGizmo()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.gizmo is not None:
            self.gizmo.sync()

    def wheelEvent(self, event):
        super().wheelEvent(event)
        if self.gizmo is not None:
            self.gizmo.sync()

    def clearItems(self):
        for item in self.items3D:
            self.removeItem(item)
        self.items3D = []

    def addItem3D(self, item):
        self.addItem(item)
        self.items3D.append(item)

    def cameraState(self):
        rotation, center = self.opts['rotation'], self.opts['center']
        return {'rotation': [rotation.scalar(), rotation.x(), rotation.y(), rotation.z()],
                'distance': float(self.opts['distance']), 'center': [center.x(), center.y(), center.z()]}

    def setCameraState(self, state):
        if not isinstance(state, dict):
            return
        w, x, y, z = (float(v) for v in state['rotation'])
        rotation = QQuaternion(w, x, y, z)
        if rotation.length() < 1e-9:
            raise ValueError('invalid camera rotation')
        self.setCameraParams(rotation=rotation.normalized(), distance=float(state['distance']),
                             center=pg.Vector(*(float(c) for c in state['center'])))
        if self.gizmo is not None:
            self.gizmo.sync()


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().setVisible(False)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def fill(widget, rows):
    widget.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            if c and isinstance(value, str) and value.endswith('%'):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            widget.setItem(r, c, item)


def percent(weight):
    return f'{100 * weight:.1f} %'


def fraction(value, tol=1e-4):
    """A reduced coordinate as a short fraction where it is one (½, ⅓...), else a decimal."""
    for denominator in (1, 2, 3, 4, 6, 8):
        numerator = round(value * denominator)
        if abs(value * denominator - numerator) < tol * denominator:
            return str(numerator) if denominator == 1 else f'{numerator}/{denominator}'
    return f'{value:.3f}'


class CompositionPanel(QWidget):
    # The composition is wanted: the panel was shown, or the degeneracy setting changed
    compositionNeeded = Signal()
    exportDataRequested = Signal()
    exportImageRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.composition = None
        self.crystal = None          # lat, rlat, red_kpoints, grid, layer axis, special points, Q-path
        self.spheresShown = 0        # k-points drawn in 3D
        self.dark = False
        self.persistence = PersistentState()

        # What it is: the exciton and its states (with those degenerate with it per
        # Options.sumDegenerate, in the Selected exciton section)
        self.infoLabel = QLabel('Select an exciton in a spectrum.')
        self.infoLabel.setWordWrap(True)
        self.infoLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.exportDataButton = QPushButton('Export data…')
        self.exportDataButton.setToolTip('The weights of every k-point (electron and hole) and the composition, '
                                         'as a CSV file')
        self.exportDataButton.clicked.connect(self.exportDataRequested)
        header = QHBoxLayout()
        header.addWidget(self.infoLabel, 1)
        header.addWidget(self.exportDataButton)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.buildKSpaceTab(), 'k-space')
        self.tabs.addTab(self.buildTransitionsTab(), 'Transitions')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(header)
        layout.addWidget(self.tabs, 1)

        p = self.persistence
        p.remember('particle', self.particleComboBox)
        p.remember('scale', self.scaleComboBox)
        p.remember('colormap', self.colormapComboBox)
        p.remember('view', self.viewComboBox)
        p.remember('threshold', self.thresholdSpinBox)
        p.remember('opacity', self.opacitySpinBox)
        p.remember('qPath', self.qPathCheckBox)
        p.remember('plane', self.planeSpinBox, DATASET)
        # The 3D camera: None until the zone is fitted or the camera moved, so
        # that a dataset without one of its own gets the zone fitted
        self.cameraSet = False
        p.remember('camera', scope=DATASET, get=self.cameraSetting, set=self.restoreCamera)
        self.setDarkTheme(False)
        self.updateControls()

    def showEvent(self, event):
        super().showEvent(event)
        # Computed only while shown: brought up, it catches up with the selected exciton
        self.compositionNeeded.emit()

    # Construction

    def buildKSpaceTab(self):
        self.particleComboBox = QComboBox()
        self.particleComboBox.addItems(PARTICLES)
        self.particleComboBox.setToolTip('Whose k-points: the electron\'s (k), the hole\'s (k−Q), or both '
                                         '(the same at Γ)')
        self.scaleComboBox = QComboBox()
        self.scaleComboBox.addItems(['Linear', 'Logarithmic'])
        self.scaleComboBox.setToolTip('Color scale of the weights, relative to the largest; logarithmic brings out '
                                      'small contributions (down to 0.1 %)')
        self.colormapComboBox = QComboBox()
        self.colormapComboBox.setIconSize(QSize(48, 12))
        for group, maps in COLORMAP_GROUPS:
            if self.colormapComboBox.count():
                self.colormapComboBox.insertSeparator(self.colormapComboBox.count())
            for label, name, description in maps:
                self.colormapComboBox.addItem(colormapIcon(makeColormap(label)), label)
        self.colormapComboBox.setCurrentText(DEFAULT_COLORMAP)
        self.viewComboBox = QComboBox()
        self.viewComboBox.addItems(['3D', 'Plane'])
        self.viewComboBox.setToolTip('The Brillouin zone in 3D, or a plane of k-points (bulk crystals)')
        self.planeSpinBox = QSpinBox()
        self.planeSpinBox.setToolTip('The plane of k-points shown: its index along the third reciprocal vector '
                                     '(0 goes through Γ), or the sum over all of them')
        self.planeLabel = QLabel('Plane:')
        self.thresholdLabel = QLabel('Hide below:')
        self.thresholdSpinBox = QDoubleSpinBox(minimum=0.0, maximum=99.0, singleStep=1.0, decimals=1, suffix=' %')
        self.thresholdSpinBox.setValue(5.0)
        self.thresholdSpinBox.setToolTip('k-points weighing less than this (relative to the largest) are not drawn '
                                         'in 3D, so that those behind are seen')
        self.opacityLabel = QLabel('Opacity:')
        self.opacitySpinBox = QDoubleSpinBox(minimum=0.05, maximum=1.0, singleStep=0.05, decimals=2)
        self.opacitySpinBox.setValue(0.6)
        self.opacitySpinBox.setToolTip('Opacity of the spheres of the k-points in 3D: translucent, those behind '
                                       'show through')
        self.qPathCheckBox = QCheckBox('Q-path')
        self.qPathCheckBox.setToolTip('The Q-path of the dispersion, where it lies in what is shown')
        self.exportImageButton = QPushButton('Export image…')
        self.exportImageButton.setToolTip('What the k-space tab shows, as an image')
        self.exportImageButton.clicked.connect(self.exportImageRequested)

        for widget in (self.particleComboBox, self.scaleComboBox, self.colormapComboBox, self.viewComboBox):
            widget.currentIndexChanged.connect(self.redraw)
            widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.viewComboBox.currentIndexChanged.connect(self.updateControls)
        self.planeSpinBox.valueChanged.connect(self.redraw)
        self.thresholdSpinBox.valueChanged.connect(self.redraw)
        self.opacitySpinBox.valueChanged.connect(self.redraw)
        self.qPathCheckBox.toggled.connect(self.redraw)

        row1 = QHBoxLayout()
        for widget in (QLabel('Particle:'), self.particleComboBox, QLabel('Scale:'), self.scaleComboBox,
                       QLabel('Colormap:'), self.colormapComboBox):
            row1.addWidget(widget)
        row1.addStretch(1)
        row2 = QHBoxLayout()
        self.viewLabel = QLabel('View:')
        for widget in (self.viewLabel, self.viewComboBox, self.planeLabel, self.planeSpinBox, self.thresholdLabel,
                       self.thresholdSpinBox, self.opacityLabel, self.opacitySpinBox, self.qPathCheckBox):
            row2.addWidget(widget)
        row2.addStretch(1)
        row2.addWidget(self.exportImageButton)

        # The plane map
        self.mapPlot = pg.PlotWidget()
        self.mapPlot.setAspectLocked(True)
        self.mapPlot.setLabel('bottom', 'k₁', units='Å⁻¹')
        self.mapPlot.setLabel('left', 'k₂', units='Å⁻¹')
        for name in ('left', 'bottom'):
            self.mapPlot.getAxis(name).enableAutoSIPrefix(False)
        self.tiles = TileMapItem()
        self.mapPlot.addItem(self.tiles)
        self.outline = pg.PlotDataItem()
        self.mapPlot.addItem(self.outline)
        self.pathItem = pg.PlotDataItem(connect='finite')
        self.mapPlot.addItem(self.pathItem)
        self.specialItem = pg.ScatterPlotItem(size=6)
        self.mapPlot.addItem(self.specialItem)
        self.specialLabels = []
        self.colorBar = pg.ColorBarItem(values=(0, 1), interactive=False, label='Weight (relative to the largest)')
        plotItem = self.mapPlot.getPlotItem()
        plotItem.layout.addItem(self.colorBar, 2, 5)
        plotItem.layout.setColumnFixedWidth(4, 5)

        # The zone in 3D
        self.view3D = KSpaceView()
        self.gizmo = AxisGizmo(target=self.view3D, size=160)
        self.gizmo.setShowLattice(False)
        self.gizmo.setShowReciprocal(True)
        self.view3D.attachGizmo(self.gizmo)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.mapPlot)
        self.stack.addWidget(self.view3D)
        self.kspaceNote = NoteLabel()

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.kspaceNote)
        return tab

    def buildTransitionsTab(self):
        self.pairsTable = table(['Valence', 'Conduction', 'Weight'])
        self.pairsTable.setToolTip('The valence-conduction band pairs of the transitions, largest first '
                                   '(bands numbered as in yambo)')
        self.bandsTable = table(['Band', 'Of', 'Weight'])
        self.bandsTable.setToolTip('The weight of each band: valence bands for the hole, conduction bands for '
                                   'the electron')
        self.kpointsTable = table(['Particle', 'k (reduced)', 'Near', 'Weight'])
        self.kpointsTable.setToolTip('The k-points weighing most, for the electron (k) and for the hole (k−Q), '
                                     'with the special point they are at or near')
        left = QSplitter(Qt.Orientation.Vertical)
        left.addWidget(self.pairsTable)
        left.addWidget(self.bandsTable)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.kpointsTable)
        splitter.setSizes([400, 500])
        return splitter

    # Content

    def setCrystal(self, lat, rlat, red_kpoints, grid, layerAxis, specialPoints, qPath=None):
        """The crystal the compositions belong to (see MainWindow.updateCompositionCrystal)."""
        changed = self.crystal is None or not np.array_equal(self.crystal['lat'], np.asarray(lat))
        self.crystal = {'lat': np.asarray(lat, dtype=float), 'rlat': np.asarray(rlat, dtype=float),
                        'red': np.asarray(red_kpoints, dtype=float), 'grid': [int(n) for n in grid],
                        'layer': layerAxis, 'special': dict(specialPoints),
                        'path': None if qPath is None else np.asarray(qPath, dtype=float)}
        planes = planeIndices(self.crystal['grid'], self.axis())
        self.planeSpinBox.blockSignals(True)
        self.planeSpinBox.setRange(planes[0] - 1, planes[-1])
        self.planeSpinBox.setSpecialValueText('Sum')
        self.planeSpinBox.setSuffix(f' / {self.crystal["grid"][self.axis()]}')
        self.planeSpinBox.blockSignals(False)
        self.updateControls()
        if changed and not self.cameraSet:
            self.fitView3D()
        self.redraw()

    def cameraSetting(self):
        return self.view3D.cameraState() if self.cameraSet else None

    def restoreCamera(self, state):
        if isinstance(state, dict):
            self.view3D.setCameraState(state)
            self.cameraSet = True
        else:
            self.cameraSet = False

    def setQPath(self, qPath):
        if self.crystal is not None:
            self.crystal['path'] = None if qPath is None else np.asarray(qPath, dtype=float)
            self.redraw()

    @Slot(object)
    def setComposition(self, composition):
        self.composition = composition
        self.updateInfo()
        self.fillTables()
        self.redraw()

    @Slot(str)
    def showProblem(self, reason):
        """Why there is nothing to show for the selected exciton."""
        self.setComposition(None)
        self.infoLabel.setText(reason)

    def clear(self):
        """No crystal (another dataset, or none): its camera is that of the next."""
        self.crystal = None
        self.cameraSet = False
        self.setComposition(None)

    def isLayer(self):
        return self.crystal is not None and self.crystal['layer'] is not None

    def axis(self):
        """The lattice vector the planes are perpendicular to: the layer's vacuum, else c."""
        return self.crystal['layer'] if self.isLayer() else 2

    def is3D(self):
        return self.crystal is not None and not self.isLayer() and self.viewComboBox.currentIndex() == 0

    @Slot()
    def updateControls(self, *args):
        bulk = self.crystal is not None and not self.isLayer()
        for widget in (self.viewLabel, self.viewComboBox):
            widget.setVisible(bulk)
        plane = bulk and self.viewComboBox.currentIndex() == 1
        for widget in (self.planeLabel, self.planeSpinBox):
            widget.setVisible(plane)
        for widget in (self.thresholdLabel, self.thresholdSpinBox, self.opacityLabel, self.opacitySpinBox):
            widget.setVisible(bulk and not plane)
        # At Γ the electron and the hole are at the same k-points: nothing to choose
        gamma = self.atGamma()
        self.particleComboBox.setEnabled(not gamma)
        self.particleComboBox.setToolTip('At Γ, the electron and the hole are at the same k-points' if gamma else
                                         'Whose k-points: the electron\'s (k), the hole\'s (k−Q), or their average')
        self.stack.setCurrentIndex(1 if self.is3D() else 0)

    def updateInfo(self):
        c = self.composition
        if c is None:
            self.infoLabel.setText('Select an exciton in a spectrum.')
            return
        states = c['states']
        if len(states) > 1:
            group = f'states {states[0]}–{states[-1]}' if states == list(range(states[0], states[-1] + 1)) \
                else 'states ' + ', '.join(map(str, states))
            summed = f', with the degenerate {group}'
        else:
            summed = ''
        q = np.asarray(c['red_qpoint'], dtype=float)
        atGamma = np.allclose(q - np.round(q), 0.0, atol=1e-6)
        where = 'Γ' if atGamma else '(' + ', '.join(fraction(x) for x in q) + ')'
        self.infoLabel.setText(f'Exciton {c["excIndex"]} at Q{c["qIndex"] + 1} = {where}, {c["energy"]:.4f} eV{summed}.'
                               + ('' if atGamma else ' The hole is at k−Q, the electron at k.'))

    def atGamma(self):
        c = self.composition
        if c is None:
            return False
        q = np.asarray(c['red_qpoint'], dtype=float)
        return bool(np.allclose(q - np.round(q), 0.0, atol=1e-6))

    def particleName(self):
        return 'Electron and hole' if self.atGamma() else self.particleComboBox.currentText()

    def weights(self):
        """The weights shown, per k-point of the grid."""
        c = self.composition
        particle = self.particleComboBox.currentIndex()
        if particle == 0:
            return np.asarray(c['electron'], dtype=float)
        if particle == 1:
            return np.asarray(c['hole'], dtype=float)
        return 0.5 * (np.asarray(c['electron'], dtype=float) + np.asarray(c['hole'], dtype=float))

    def colors(self, values):
        """RGBA (0-255) of `values` (relative to the largest) on the scale chosen, and the color bar's range."""
        colormap = makeColormap(self.colormapComboBox.currentText())
        if self.scaleComboBox.currentIndex() == 1:
            scaled = (np.log10(np.clip(values, LOG_FLOOR, 1.0)) - np.log10(LOG_FLOOR)) / -np.log10(LOG_FLOOR)
            barRange, label = (np.log10(LOG_FLOOR), 0.0), 'log₁₀ weight (relative to the largest)'
        else:
            scaled, barRange, label = np.clip(values, 0.0, 1.0), (0.0, 1.0), 'Weight (relative to the largest)'
        return colormap.map(scaled, mode='byte'), colormap, barRange, label

    @Slot()
    def redraw(self, *args):
        self.updateControls()
        for label in self.specialLabels:
            self.mapPlot.removeItem(label)
        self.specialLabels = []
        self.view3D.clearItems()
        if self.composition is None or self.crystal is None:
            self.tiles.setData([], [], [])
            for item in (self.outline, self.pathItem):
                item.setData([], [])
            self.specialItem.setData([], [])
            self.kspaceNote.setText('')
            return
        values = self.weights()
        top = float(values.max()) or 1.0
        if self.is3D():
            self.draw3D(values / top)
        else:
            self.drawPlane(values / top)

    def drawPlane(self, values):
        k = self.crystal
        axis = self.axis()
        plane = None if self.isLayer() or self.planeSpinBox.value() < self.planeSpinBox.minimum() + 1 \
            else self.planeSpinBox.value()
        data = planeMap(k['red'], values, k['lat'], k['rlat'], k['grid'], axis, plane)
        shown = data['values'] / (data['values'].max() or 1.0)
        rgba, colormap, barRange, label = self.colors(shown)
        self.tiles.setData(data['points'], data['tile'], rgba, clip=data['outline'])
        outline = np.vstack([data['outline'], data['outline'][:1]]) if len(data['outline']) else np.empty((0, 2))
        foreground = PLOT_COLORS[self.dark]['foreground']
        self.outline.setData(outline[:, 0], outline[:, 1], pen=pg.mkPen(foreground, width=1.5))
        self.colorBar.setColorMap(colormap)
        self.colorBar.setLevels(barRange)
        self.colorBar.getAxis('left').setLabel(label)

        normal, e1, e2 = planeBasis(k['lat'], axis)
        # Overlays on the plane shown; when the planes are summed (or for a layer), the plane through Γ
        offset = 0.0 if plane is None else plane / k['grid'][axis] / np.linalg.norm(k['lat'][axis])
        spacing = 0.5 / max(k['grid'][axis], 2) / np.linalg.norm(k['lat'][axis])

        def onPlane(car):
            return abs(car @ normal - offset) < spacing

        # Special points on that plane, in the zone
        positions, names = [], []
        for name, red in k['special'].items():
            car = np.asarray(red, dtype=float) @ k['rlat']
            if onPlane(car):
                positions.append([car @ e1 * TO_INVERSE_ANGSTROM, car @ e2 * TO_INVERSE_ANGSTROM])
                names.append(name)
        if positions and len(data['outline']):
            from matplotlib.path import Path as Polygon
            inside = Polygon(data['outline']).contains_points(positions, radius=1e-6 * np.abs(data['outline']).max())
            positions = [p for p, i in zip(positions, inside) if i]
            names = [n for n, i in zip(names, inside) if i]
        self.specialItem.setData([p[0] for p in positions], [p[1] for p in positions],
                                 brush=pg.mkBrush(foreground), pen=None)
        for (x, y), text in zip(positions, tickLabels(names)):
            label = pg.TextItem(text, color=foreground, anchor=(-0.15, 1.1))
            label.setPos(x, y)
            self.mapPlot.addItem(label, ignoreBounds=True)
            self.specialLabels.append(label)

        path = k['path']
        if self.qPathCheckBox.isChecked() and path is not None and len(path):
            on = np.array([onPlane(p) for p in path])
            xy = np.column_stack([path @ e1, path @ e2]) * TO_INVERSE_ANGSTROM
            xy[~on] = np.nan
            self.pathItem.setData(xy[:, 0], xy[:, 1], pen=pg.mkPen(foreground, width=1.5, style=Qt.PenStyle.DashLine))
            hidden = not on.all()
        else:
            self.pathItem.setData([], [])
            hidden = False
        what = 'all the planes summed (with the special points and Q-path of the plane through Γ)' \
            if plane is None and not self.isLayer() else \
            ('the plane through Γ' if plane in (None, 0) else f'the plane k{"₁₂₃"[axis]} = {plane}/{k["grid"][axis]}')
        self.kspaceNote.setText(f'{self.particleName()}, {what}' +
                                (' (the parts of the Q-path off it are not drawn)' if hidden else '') + '.')
        # The zone in view (the tiles outside it are clipped)
        if len(data['outline']):
            low, high = data['outline'].min(axis=0), data['outline'].max(axis=0)
            self.mapPlot.setRange(xRange=(low[0], high[0]), yRange=(low[1], high[1]), padding=0.06)
        else:
            self.mapPlot.getPlotItem().enableAutoRange()

    def draw3D(self, values):
        k = self.crystal
        points, pointValues, zone = zonePoints(k['red'], values, k['rlat'])
        foreground = PLOT_COLORS[self.dark]['foreground']
        color = pg.mkColor(foreground).getRgbF()

        edges = zone['vertices'][np.asarray(zone['edges']).ravel()]
        lines = gl.GLLinePlotItem(pos=edges, mode='lines', color=color, width=1.5, antialias=True)
        lines.setGLOptions(OPAQUE_GL_OPTIONS)
        lines.setDepthValue(OPAQUE_STAGE)
        self.view3D.addItem3D(lines)

        # The k-points as lit spheres, translucent, drawn back to front (as the
        # wave function's surfaces) so that those behind show through
        threshold = self.thresholdSpinBox.value() / 100
        shown = pointValues >= max(threshold, 1e-12)
        rgba, _, _, _ = self.colors(pointValues[shown])
        colors = rgba / 255.0
        colors[:, 3] = self.opacitySpinBox.value()
        step = min(np.linalg.norm(k['rlat'][i] / k['grid'][i]) for i in range(3)) * TO_INVERSE_ANGSTROM
        radii = step * (0.18 + 0.32 * pointValues[shown])
        self.spheresShown = int(shown.sum())
        if shown.any():
            spheres = SortedMeshItem(meshdata=spheresMeshData(points[shown], radii, colors, rows=12, cols=16),
                                     shader=headlightShader, smooth=True)
            spheres.setGLOptions(TRANSLUCENT_GL_OPTIONS)
            spheres.setDepthValue(TRANSLUCENT_STAGE)
            self.view3D.addItem3D(spheres)

        for name, text in zip(k['special'], tickLabels(list(k['special']))):
            car = np.asarray(k['special'][name], dtype=float) @ k['rlat'] * TO_INVERSE_ANGSTROM
            label = gl.GLTextItem(pos=car, text=text, color=pg.mkColor(foreground))
            label.setDepthValue(LABEL_STAGE)
            self.view3D.addItem3D(label)
        if self.qPathCheckBox.isChecked() and k['path'] is not None and len(k['path']):
            path = gl.GLLinePlotItem(pos=k['path'] * TO_INVERSE_ANGSTROM, color=color, width=2, antialias=True)
            path.setGLOptions(OPAQUE_GL_OPTIONS)
            path.setDepthValue(OPAQUE_STAGE)
            self.view3D.addItem3D(path)
        self.kspaceNote.setText(f'{self.particleName()}: {int(shown.sum())} of {len(shown)} k-points '
                                f'of the zone drawn (those of {self.thresholdSpinBox.value():g} % of the largest '
                                'weight or more), sized and colored by their weight.')

    def fitView3D(self):
        if self.crystal is None:
            return
        extent = float(np.max(np.linalg.norm(self.crystal['rlat'], axis=1))) * TO_INVERSE_ANGSTROM
        self.view3D.setCameraPosition(pos=pg.Vector(0, 0, 0), distance=2.5 * extent)
        self.cameraSet = True
        self.gizmo.setLatticeVectors(self.crystal['lat'])
        self.gizmo.sync()

    def fillTables(self):
        c = self.composition
        if c is None:
            for widget in (self.pairsTable, self.bandsTable, self.kpointsTable):
                widget.setRowCount(0)
            return
        pairs = c['pairs']
        # The largest, down to 0.05 %; the others together
        shown = [p for p in pairs[:TOP_ROWS] if p[2] >= 5e-4] or pairs[:1]
        rows = [(v, cb, percent(w)) for v, cb, w in shown]
        rest = pairs[len(shown):]
        if rest:
            rows.append(('Others', f'({len(rest)} pairs)', percent(sum(w for _, _, w in rest))))
        fill(self.pairsTable, rows)
        bands = [(b, 'Hole (valence)', percent(w)) for b, w in sorted(c['valence'].items(), key=lambda x: -x[1])
                 if w >= 5e-4]
        bands += [(b, 'Electron (conduction)', percent(w)) for b, w in sorted(c['conduction'].items(), key=lambda x: -x[1])
                  if w >= 5e-4]
        fill(self.bandsTable, bands)
        rows = []
        if self.crystal is not None:
            red, special, rlat = self.crystal['red'], self.crystal['special'], self.crystal['rlat']
            q = np.asarray(c['red_qpoint'], dtype=float)
            atGamma = np.allclose(q - np.round(q), 0.0, atol=1e-6)
            particles = [('Electron and hole', 'electron')] if atGamma else [('Electron', 'electron'), ('Hole', 'hole')]
            for name, key in particles:
                weights = np.asarray(c[key], dtype=float)
                for i in np.argsort(-weights)[:TOP_ROWS]:
                    if weights[i] <= 0:
                        break
                    folded = (red[i] + 0.5) % 1.0 - 0.5
                    near = nearestSpecialPoint(red[i], special, rlat)
                    rows.append((name, '(' + ', '.join(fraction(x) for x in folded) + ')',
                                 tickLabels([near])[0] if near else '', percent(weights[i])))
        fill(self.kpointsTable, rows)

    # Theme

    def setDarkTheme(self, dark):
        self.dark = dark
        colors = PLOT_COLORS[dark]
        self.mapPlot.setBackground(colors['background'])
        for name in ('left', 'bottom'):
            axis = self.mapPlot.getAxis(name)
            axis.setPen(colors['foreground'])
            axis.setTextPen(colors['foreground'])
        for axis in (self.colorBar.axis, self.colorBar.getAxis('left')):
            axis.setPen(colors['foreground'])
            axis.setTextPen(colors['foreground'])
        self.view3D.setBackgroundColor(colors['background'])
        self.gizmo.setDarkTheme(dark)
        self.redraw()
