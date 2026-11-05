from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QQuaternion, QVector3D
import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl

from .gl_style import headlightShader, enableMultisampling


BOHR_TO_ANGSTROM = 0.529177210544


def arrowMeshData(length, shaftRadius, headRadius, headLength, segments=24):
    """
    Closed 3D arrow along +z from the origin: a cylindrical shaft and a conical
    head, with caps. Each part has its own vertices so smooth shading does not
    blur the edges between them.
    """
    headLength = min(headLength, 0.5 * length)
    shaftLength = length - headLength

    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    ring = np.column_stack([np.cos(angles), np.sin(angles), np.zeros(segments)])

    def atHeight(points, z):
        points = points.copy()
        points[:, 2] = z
        return points

    parts = [
        atHeight(ring * shaftRadius, 0.0),          # 0: shaft bottom
        atHeight(ring * shaftRadius, shaftLength),  # 1: shaft top
        atHeight(ring * headRadius, shaftLength),   # 2: cone base (side)
        atHeight(ring * headRadius, shaftLength),   # 3: cone base (cap)
        atHeight(ring * shaftRadius, 0.0),          # 4: shaft bottom (cap)
    ]
    vertices = np.vstack(parts + [[[0.0, 0.0, length], [0.0, 0.0, shaftLength], [0.0, 0.0, 0.0]]])
    tip, headCenter, bottomCenter = 5 * segments, 5 * segments + 1, 5 * segments + 2

    i = np.arange(segments)
    j = (i + 1) % segments
    offset = lambda part, k: part * segments + k
    faces = np.vstack([
        np.column_stack([offset(0, i), offset(0, j), offset(1, j)]),        # shaft side
        np.column_stack([offset(0, i), offset(1, j), offset(1, i)]),
        np.column_stack([offset(2, i), offset(2, j), np.full(segments, tip)]),  # cone side
        np.column_stack([np.full(segments, headCenter), offset(3, j), offset(3, i)]),    # cone base cap
        np.column_stack([np.full(segments, bottomCenter), offset(4, j), offset(4, i)]),  # shaft bottom cap
    ])

    return gl.MeshData(vertexes=vertices.astype(np.float32), faces=faces.astype(np.uint32))


def cellParameters(lattice):
    """
    Lengths (in the units of `lattice`) and angles (degrees) of the cell whose
    rows are the lattice vectors a, b, c.
    """
    a, b, c = np.asarray(lattice, dtype=float)

    def angle(u, v):
        return np.degrees(np.arccos(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1.0, 1.0)))

    return {
        'a': np.linalg.norm(a), 'b': np.linalg.norm(b), 'c': np.linalg.norm(c),
        'alpha': angle(b, c), 'beta': angle(a, c), 'gamma': angle(a, b)
    }


def reciprocalLattice(lattice):
    """Rows a*, b*, c* with a_i . a*_j = 2 pi delta_ij."""
    return 2.0 * np.pi * np.linalg.inv(np.asarray(lattice, dtype=float)).T


def cellInfoHtml(latticeBohr, showReciprocal=False):
    """Cell parameters in Å and degrees (and reciprocal ones in Å⁻¹) as rich text."""
    lattice = np.asarray(latticeBohr, dtype=float) * BOHR_TO_ANGSTROM
    p = cellParameters(lattice)
    lines = [
        f"a = {p['a']:.4f} Å &nbsp; b = {p['b']:.4f} Å &nbsp; c = {p['c']:.4f} Å",
        f"α = {p['alpha']:.3f}° &nbsp; β = {p['beta']:.3f}° &nbsp; γ = {p['gamma']:.3f}°",
    ]
    if showReciprocal:
        r = cellParameters(reciprocalLattice(lattice))
        lines += [
            f"a* = {r['a']:.4f} Å⁻¹ &nbsp; b* = {r['b']:.4f} Å⁻¹ &nbsp; c* = {r['c']:.4f} Å⁻¹",
            f"α* = {r['alpha']:.3f}° &nbsp; β* = {r['beta']:.3f}° &nbsp; γ* = {r['gamma']:.3f}°",
        ]
    return '<br>'.join(lines)


class AxisGizmo(gl.GLViewWidget):
    """
    Small always-on-top widget mirroring the orientation of `target` (a
    GLViewWidget) and showing, as 3D arrows: the Cartesian axes, the lattice
    vectors a, b, c and, optionally, the reciprocal vectors a*, b*, c*.
    Purely a display: it does not accept mouse input.

    The gizmo has a fixed size, so each set of arrows is scaled separately: the
    Cartesian unit vectors and the longest vector of each lattice set all have
    the same length, while directions, angles and length ratios within a set
    are preserved.
    """

    arrowLength = 2.4
    labelOffset = 0.45

    cartesianStyle = dict(colors=[(0.55, 0.55, 0.55, 1.0)] * 3, labels=['x', 'y', 'z'],
                          shaftRadius=0.05, headRadius=0.14, headLength=0.4, labelColor=(110, 110, 110, 255))
    latticeStyle = dict(colors=[(0.9, 0.0, 0.0, 1.0), (0.0, 0.75, 0.0, 1.0), (0.0, 0.2, 1.0, 1.0)], labels=['a', 'b', 'c'],
                        shaftRadius=0.1, headRadius=0.25, headLength=0.6)
    reciprocalStyle = dict(colors=[(1.0, 0.55, 0.55, 1.0), (0.55, 0.9, 0.55, 1.0), (0.55, 0.7, 1.0, 1.0)], labels=['a*', 'b*', 'c*'],
                           shaftRadius=0.07, headRadius=0.19, headLength=0.5)

    def __init__(self, target, size=200, parent=None):
        super().__init__(parent=parent)
        self.target = target
        self.margin = 8

        self.setFixedSize(size, size)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop)

        self.setBackgroundColor(1, 1, 1, 0)
        fmt = self.format()
        fmt.setAlphaBufferSize(8)
        self.setFormat(fmt)
        enableMultisampling(self)

        # Fixed framing -- only rotation is ever synced.
        self.opts['center'] = pg.Vector(0, 0, 0)
        self.opts['distance'] = 400
        self.opts['fov'] = 1

        centerMeshItem = gl.GLMeshItem(meshdata=gl.MeshData.sphere(16, 16, 0.18), color=(0.4, 0.4, 0.4, 1.0),
                                       smooth=True, shader=headlightShader, drawEdges=False)
        self.addItem(centerMeshItem)

        self.lattice = None
        self.showCartesian = True
        self.showLattice = True
        self.showReciprocal = False
        self.showLabels = True

        self.arrowItems = []
        self.labelItems = []
        self.rebuild()

        self.sync()

    def sync(self):
        """Copy the target widget's current orientation into this one."""
        t = self.target
        if t.opts.get('rotationMethod', 'euler') == 'quaternion':
            self.opts['rotationMethod'] = 'quaternion'
            self.opts['rotation'] = t.opts['rotation']
        else:
            self.opts['azimuth'] = t.opts['azimuth']
            self.opts['elevation'] = t.opts['elevation']
        self.update()

    def setLatticeVectors(self, lattice):
        """Lattice vectors as rows (Cartesian components, any length unit)."""
        self.lattice = np.asarray(lattice, dtype=float)
        self.rebuild()

    def setShowCartesian(self, show: bool):
        self.showCartesian = show
        self.rebuild()

    def setShowLattice(self, show: bool):
        self.showLattice = show
        self.rebuild()

    def setShowReciprocal(self, show: bool):
        self.showReciprocal = show
        self.rebuild()

    def setShowLabels(self, show: bool):
        self.showLabels = show
        for item in self.labelItems:
            item.setVisible(show)

    def clearArrows(self):
        for item in self.arrowItems + self.labelItems:
            self.removeItem(item)
        self.arrowItems.clear()
        self.labelItems.clear()

    def rebuild(self):
        self.clearArrows()

        if self.showCartesian:
            self.addArrowSet(np.eye(3), self.cartesianStyle)

        if self.lattice is not None:
            if self.showLattice:
                self.addArrowSet(self.lattice, self.latticeStyle)
            if self.showReciprocal:
                self.addArrowSet(reciprocalLattice(self.lattice), self.reciprocalStyle)

        self.update()

    def addArrowSet(self, vectors, style):
        """Arrows for the rows of `vectors`, scaled so that the longest has length arrowLength."""
        vectors = np.asarray(vectors, dtype=float)
        scale = self.arrowLength / np.linalg.norm(vectors, axis=1).max()

        for vector, color, label in zip(vectors * scale, style['colors'], style['labels']):
            length = np.linalg.norm(vector)
            direction = vector / length

            meshData = arrowMeshData(length, style['shaftRadius'], style['headRadius'], style['headLength'])
            arrow = gl.GLMeshItem(meshdata=meshData, color=color, smooth=True, shader=headlightShader, drawEdges=False)
            transform = pg.Transform3D()
            transform.rotate(QQuaternion.rotationTo(QVector3D(0.0, 0.0, 1.0), QVector3D(*direction)))
            arrow.setTransform(transform)
            self.addItem(arrow)
            self.arrowItems.append(arrow)

            labelColor = style.get('labelColor', tuple(int(255 * 0.75 * c) for c in color[:3]) + (255,))
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            text = gl.GLTextItem(pos=vector + self.labelOffset * direction, text=label, color=labelColor,
                                 font=font, alignment=Qt.AlignmentFlag.AlignCenter)
            text.setVisible(self.showLabels)
            # Text is painted with QPainter and does not write depth: draw it after
            # all arrows so that none can paint over it
            text.setDepthValue(10)
            self.addItem(text)
            self.labelItems.append(text)
