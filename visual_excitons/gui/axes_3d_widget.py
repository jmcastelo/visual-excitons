from PySide6.QtCore import Qt
import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl


class AxisGizmo(gl.GLViewWidget):
    """Small always-on-top widget: shows a 3D axis triad and mirrors
    the orientation of `target` (a GLViewWidget). Purely a display --
    it does not accept its own mouse input."""

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

        # Fixed framing -- only rotation is ever synced.
        self.opts['center'] = pg.Vector(0, 0, 0)
        self.opts['distance'] = 400
        self.opts['fov'] = 1

        nRows = 20
        nCols = 20
        radius = [0.25, 0.0]
        length = 3

        xMeshData = gl.MeshData.cylinder(nRows, nCols, radius, length)
        xFaceColors = np.full(shape=(xMeshData.faceCount(), 4), fill_value=[1.0, 0.0, 0.0, 1.0], dtype=np.float32)
        xMeshData.setFaceColors(xFaceColors)
        xMeshItem = gl.GLMeshItem(meshdata=xMeshData, smooth=True, shader='shaded', drawEdges=False)
        xMeshItem.rotate(90, 0, 1, 0)
        self.addItem(xMeshItem)

        yMeshData = gl.MeshData.cylinder(nRows, nCols, radius, length)
        yFaceColors = np.full(shape=(yMeshData.faceCount(), 4), fill_value=[0.0, 1.0, 0.0, 1.0], dtype=np.float32)
        yMeshData.setFaceColors(yFaceColors)
        yMeshItem = gl.GLMeshItem(meshdata=yMeshData, smooth=True, shader='shaded', drawEdges=False)
        yMeshItem.rotate(-90, 1, 0, 0)
        self.addItem(yMeshItem)

        zMeshData = gl.MeshData.cylinder(nRows, nCols, radius, length)
        zFaceColors = np.full(shape=(zMeshData.faceCount(), 4), fill_value=[0.0, 0.0, 1.0, 1.0], dtype=np.float32)
        zMeshData.setFaceColors(zFaceColors)
        zMeshItem = gl.GLMeshItem(meshdata=zMeshData, smooth=True, shader='shaded', drawEdges=False)
        self.addItem(zMeshItem)

        centerMeshData = gl.MeshData.sphere(20, 20, 0.5)
        centerMeshItem = gl.GLMeshItem(meshdata=centerMeshData, smooth=True, shader='shaded', drawEdges=False)
        self.addItem(centerMeshItem)

        self.baseLatticeItems = []

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

    def clearBaseLatticeItems(self):
        if len(self.baseLatticeItems) > 0:
            for item in self.baseLatticeItems:
                self.removeItem(item)
            self.baseLatticeItems.clear()

    def plotBaseLatticeVectors(self, baseVectors):
        self.clearBaseLatticeItems()

        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[0]], color=(1.0, 0.0, 0.0, 1.0), width=5.0, antialias=True, mode='lines'))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[1]], color=(0.0, 1.0, 0.0, 1.0), width=5.0, antialias=True, mode='lines'))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[2]], color=(0.0, 0.0, 1.0, 1.0), width=5.0, antialias=True, mode='lines'))

        self.addItem(self.baseLatticeItems[0])
        self.addItem(self.baseLatticeItems[1])
        self.addItem(self.baseLatticeItems[2])