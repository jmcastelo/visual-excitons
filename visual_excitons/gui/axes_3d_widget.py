from PySide6.QtCore import Qt
import pyqtgraph as pg
import pyqtgraph.opengl as gl


class AxisGizmo(gl.GLViewWidget):
    """Small always-on-top widget: shows a 3D axis triad and mirrors
    the orientation of `target` (a GLViewWidget). Purely a display --
    it does not accept its own mouse input."""

    def __init__(self, target, size=110, parent=None):
        super().__init__(parent=parent)
        self.target = target
        self.margin = 8

        self.setFixedSize(size, size)

        # Let clicks/drags fall through to the widget behind the gizmo.
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # Attempt a transparent background. On some platforms/drivers
        # QOpenGLWidget transparency isn't honored -- if so you'll just
        # see a plain-colored square, which is a harmless fallback.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        fmt = self.format()
        fmt.setAlphaBufferSize(8)
        self.setFormat(fmt)

        # Fixed framing -- only rotation is ever synced.
        self.opts['center'] = pg.Vector(0, 0, 0)
        self.opts['distance'] = 6
        self.opts['fov'] = 30

        axis = gl.GLAxisItem()
        axis.setSize(3, 3, 3)  # GLAxisItem is red/green/blue = X/Y/Z by default
        self.addItem(axis)

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
