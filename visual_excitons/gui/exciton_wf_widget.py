from PySide6.QtCore import Qt, Slot, QSize
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QQuaternion, QVector3D

from OpenGL import GL

import pyqtgraph as pg
import pyqtgraph.opengl as gl
import numpy as np

from visual_excitons.core.atomic_data import covalent_radii, jmol_colors, chemical_symbols



class ExcitonWfWidget(gl.GLViewWidget):
    def __init__(self, parent = None):
        gl.GLViewWidget.__init__(self, parent, rotationMethod='quaternion')

        self.colormap = pg.colormap.get('viridis')

        # self.shader = 'balloon'
        # self.shader = 'normalColor'
        # self.shader = 'viewNormalColor'
        self.shader = 'shaded'
        # self.shader = 'edgeHilight'
        # self.shader = 'heightColor'

        # self.glOptions = 'opaque'
        # self.glOptions = 'additive'
        # self.glOptions = 'translucent'
        self.glOptions = {
            GL.GL_DEPTH_TEST: True,
            'glDepthMask': (GL.GL_TRUE,),
            GL.GL_CULL_FACE: False,
            GL.GL_BLEND: False
        }
        self.isoGlOptions = {
            GL.GL_DEPTH_TEST: True,
            'glDepthMask': (GL.GL_FALSE,),
            GL.GL_CULL_FACE: False,
            GL.GL_BLEND: True,
            'glBlendFuncSeparate': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA),
            # 'glBlendFuncSeparate': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
            # 'glBlendFuncSeparate': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_SRC_ALPHA, GL.GL_DST_ALPHA),
            # 'glBlendFunc': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            # 'glBlendEquationSeparate': (GL.GL_FUNC_ADD, GL.GL_FUNC_ADD)
        }

        self.setCameraPosition(distance=75)
        self.setBackgroundColor((255, 255, 255, 255))
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)

        self.wfIsoVertices = None
        self.wfIsoFaces = None
        self.wfIsoMeshData = None

        self.wfIsoVerticesSet = np.empty((0, 3), dtype=float)
        self.wfIsoFacesSet = np.empty((0, 3), dtype=int)
        self.wfIsoColorsSet = np.empty((0, 4), dtype=float)
        self.wfIsoMeshDataSet = None

        self.wfMeshItem = None
        self.wfMeshItemSet = None
        self.wfVolItem = None

        self.baseLatticeItems = []
        self.latticeBoundaryItems = []
        self.latticeItems = []
        self.atomNameItems = []
        self.fixedParticleItem = None

        self.plotFixedParticle()

        self.axisItem = gl.GLAxisItem()
        self.axisItem.setSize(5, 5, 5)
        self.addItem(self.axisItem)

        self.gizmo = None

        self.opts['fov'] = 1
        self.opts['distance'] = 5000

    def attach_gizmo(self, gizmo, margin=8):
        self.gizmo = gizmo
        gizmo.margin = margin
        gizmo.setParent(self)
        self._reposition_gizmo()
        gizmo.show()
        gizmo.raise_()

    def _reposition_gizmo(self):
        if self.gizmo is None:
            return
        m = self.gizmo.margin
        y = self.height() - self.gizmo.height() - m
        x = m
        self.gizmo.move(x, y)

    def itemExists(self, index: int):
        if index == 0:
            return self.wfMeshItem is not None
        elif index == 1:
            return self.wfMeshItemSet is not None
            # return len(self.wfMeshItemSet) > 0
        elif index == 2:
            return self.wfVolItem is not None
        else:
            return False

    @Slot(int)
    def showItem(self, index: int):
        if self.wfMeshItem is not None:
            self.wfMeshItem.setVisible(index == 0)

        # if len(self.wfMeshItemSet) > 0:
        #     for item in self.wfMeshItemSet:
        #         item.setVisible(index == 1)

        if self.wfMeshItemSet is not None:
            self.wfMeshItemSet.setVisible(index == 1)

        if self.wfVolItem is not None:
            self.wfVolItem.setVisible(index == 2)

    def clearWfItems(self):
        self.clearWfVolItem()
        self.clearWfMeshItem()
        self.clearWfMeshItemSet()

    def clearWfVolItem(self):
        if self.wfVolItem is not None:
            self.removeItem(self.wfVolItem)
            self.wfVolItem = None

    def clearWfMeshItem(self):
        if self.wfMeshItem is not None:
            self.removeItem(self.wfMeshItem)
            self.wfMeshItem = None

    def clearWfMeshItemSet(self):
        if self.wfMeshItemSet is not None:
            self.removeItem(self.wfMeshItemSet)
            self.wfMeshItemSet = None

            self.wfIsoVerticesSet = np.empty((0, 3), dtype=float)
            self.wfIsoFacesSet = np.empty((0, 3), dtype=int)
            self.wfIsoColorsSet = np.empty((0, 4), dtype=float)

    # def clearWfMeshItemSet(self):
    #     if len(self.wfMeshItemSet) > 0:
    #         for item in self.wfMeshItemSet:
    #             self.removeItem(item)
    #         self.wfMeshItemSet.clear()
    #         self.wfIsoVerticesSet.clear()
    #         self.wfIsoFacesSet.clear()
    #         self.wfIsoColorsSet.clear()

    def clearBaseLatticeItems(self):
        if len(self.baseLatticeItems) > 0:
            for item in self.baseLatticeItems:
                self.removeItem(item)
            self.baseLatticeItems.clear()
        self.gizmo.clearBaseLatticeItems()

    def clearLatticeBoundaryItems(self):
        if len(self.latticeBoundaryItems) > 0:
            for item in self.latticeBoundaryItems:
                self.removeItem(item)
            self.latticeBoundaryItems.clear()

    def clearLatticeItems(self):
        if len(self.latticeItems) > 0:
            for item in self.latticeItems:
                self.removeItem(item)
            self.latticeItems.clear()

    def clearAtomNamesItems(self):
        if len(self.atomNameItems) > 0:
            for item in self.atomNameItems:
                self.removeItem(item)
            self.atomNameItems.clear()

    @Slot(list, float, list)
    def plotWfIso(self, wf, level, transform, opacity):
        self.wfIsoVertices, self.wfIsoFaces = pg.isosurface(wf, level)

        color = self.colormap.mapToQColor(level)

        self.wfIsoMeshData = gl.MeshData(vertexes=self.wfIsoVertices, faces=self.wfIsoFaces)

        self.clearWfMeshItem()

        self.wfMeshItem = gl.GLMeshItem(meshdata=self.wfIsoMeshData, shader='shaded', smooth=True, computeNormals=True)
        self.wfMeshItem.setColor((color.redF(), color.greenF(), color.blueF(), opacity))
        self.wfMeshItem.setGLOptions(self.isoGlOptions)
        self.wfMeshItem.setDepthValue(1)
        self.wfMeshItem.setTransform(pg.Transform3D(transform))

        self.addItem(self.wfMeshItem)

        self.onCameraChanged()

    @Slot(list, int, list)
    def plotWfIsoSet(self, wf, numLevels, transform, opacity):
        self.clearWfMeshItemSet()

        for level in np.linspace(0.01, 0.99, numLevels):
            verts, faces = pg.isosurface(wf, level)

            self.wfIsoFacesSet = np.concatenate((self.wfIsoFacesSet, faces + self.wfIsoVerticesSet.shape[0]), axis=0)
            self.wfIsoVerticesSet = np.concatenate((self.wfIsoVerticesSet, verts), axis=0)

            color = self.colormap.mapToQColor(level)
            color.setAlphaF(opacity)
            colors = np.full(shape=(len(verts), 4), fill_value=[color.redF(), color.greenF(), color.blueF(), color.alphaF()], dtype=np.float32)
            self.wfIsoColorsSet = np.concatenate((self.wfIsoColorsSet, colors), axis=0)

        self.wfIsoMeshDataSet = gl.MeshData(vertexes=self.wfIsoVerticesSet, faces=self.wfIsoFacesSet, vertexColors=self.wfIsoColorsSet)

        self.wfMeshItemSet = gl.GLMeshItem(meshdata=self.wfIsoMeshDataSet, shader='balloon', smooth=True, computeNormals=True)
        self.wfMeshItemSet.setGLOptions(self.isoGlOptions)
        self.wfMeshItemSet.setDepthValue(1)
        self.wfMeshItemSet.setTransform(pg.Transform3D(transform))

        self.addItem(self.wfMeshItemSet)

        self.onCameraChanged()

    @Slot(list, int, list)
    def plotWfVol(self, wf, sliceDensity, transform):
        # RGBA bytes for every voxel in one vectorized call; alpha scaled by density
        data = self.colormap.mapToByte(wf).astype(np.ubyte, copy=False)
        data[..., 3] = (data[..., 3] * wf).astype(np.ubyte)

        self.clearWfVolItem()

        self.wfVolItem = gl.GLVolumeItem(data=data, sliceDensity=sliceDensity)
        self.wfVolItem.setTransform(pg.Transform3D(transform))
        self.addItem(self.wfVolItem)

    def plotBaseLatticeVectors(self, baseVectors):
        self.clearBaseLatticeItems()

        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[0]], color=(1.0, 0.0, 0.0, 1.0), width=5.0, antialias=True, mode='lines', glOptions=self.glOptions))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[1]], color=(0.0, 1.0, 0.0, 1.0), width=5.0, antialias=True, mode='lines', glOptions=self.glOptions))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[2]], color=(0.0, 0.0, 1.0, 1.0), width=5.0, antialias=True, mode='lines', glOptions=self.glOptions))

        self.addItem(self.baseLatticeItems[0])
        self.addItem(self.baseLatticeItems[1])
        self.addItem(self.baseLatticeItems[2])

        self.gizmo.plotBaseLatticeVectors(baseVectors)

    def plotUnitCellBoundaries(self, baseVectors, offset):
        color = (0.5, 0.5, 0.5, 1.0)

        ucellBoundaries = []
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[0]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[1]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[2]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))

        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0], baseVectors[0] + baseVectors[1]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0], baseVectors[0] + baseVectors[2]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1], baseVectors[1] + baseVectors[0]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1], baseVectors[1] + baseVectors[2]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2], baseVectors[2] + baseVectors[0]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2], baseVectors[2] + baseVectors[1]], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))

        apex = baseVectors[0] + baseVectors[1] + baseVectors[2]

        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0] + baseVectors[1], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0] + baseVectors[2], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1] + baseVectors[0], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1] + baseVectors[2], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2] + baseVectors[0], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2] + baseVectors[1], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))

        for item in ucellBoundaries:
            self.latticeBoundaryItems.append(item)
            item.translate(offset[0], offset[1], offset[2])
            self.addItem(item)

    def plotUnitCellAtoms(self, atomicNumbers, atomicPositions, offset):
        numAtoms = len(atomicNumbers)

        for i in range(numAtoms):
            meshData = gl.MeshData.sphere(8, 8, covalent_radii[atomicNumbers[i]])
            faceColors = np.full(shape=(meshData.faceCount(), 4), fill_value=list(jmol_colors[atomicNumbers[i]]) + [1.0], dtype=np.float32)
            meshData.setFaceColors(faceColors)

            position = offset + atomicPositions[i]

            meshItem = gl.GLMeshItem(meshdata=meshData, smooth=True, shader=self.shader, glOptions=self.glOptions, drawEdges=False)
            meshItem.translate(position[0], position[1], position[2])

            self.latticeItems.append(meshItem)
            self.addItem(meshItem)

            textItem = gl.GLTextItem(pos=position, color=(255, 255, 255, 255), text=chemical_symbols[atomicNumbers[i]], alignment=Qt.AlignmentFlag.AlignCenter)
            self.atomNameItems.append(textItem)
            self.addItem(textItem)

    def plotFixedParticle(self):
        meshData = gl.MeshData.sphere(8, 8, 0.3)
        faceColors = np.full(shape=(meshData.faceCount(), 4), fill_value=[1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        meshData.setFaceColors(faceColors)

        self.fixedParticleItem = gl.GLMeshItem(meshdata=meshData, smooth=True, shader=self.shader, glOptions=self.glOptions, drawEdges=False)
        self.addItem(self.fixedParticleItem)

    def translateFixedParticle(self, position):
        self.fixedParticleItem.resetTransform()
        self.fixedParticleItem.translate(position[0], position[1], position[2])

    def sortFacesByCameraBak1(self, vertices, faces, viewMatrix):
        centroids3 = vertices[faces].mean(axis=1)
        centroids4 = np.hstack((centroids3, np.ones((centroids3.shape[0], 1), dtype=centroids3.dtype)))
        # camCentroids4 = (viewMatrix @ centroids4.T).T
        # camCentroids4 = centroids4 @ viewMatrix.T
        camCentroids4 = viewMatrix @ centroids4.T
        w = camCentroids4[:, 3:4]
        camCentroids3 = camCentroids4[:, :3] / np.where(np.abs(w) > 0, w, 1.0)
        order = np.argsort(camCentroids3[:,2])
        return faces[order]

    def sortFacesByCameraBak2(self, vertices, faces, cameraPosition):
        centroids = vertices[faces].mean(axis=1)
        distances = np.linalg.norm(centroids - cameraPosition, axis=1)
        order = np.argsort(distances)[:-1]
        return faces[order]

    def sortFacesByCamera(self, vertices, faces, cameraPosition):
        minDistances = np.min(np.linalg.norm(vertices[faces] - cameraPosition, axis=2), axis=1)
        order = np.argsort(minDistances)[:-1]
        return faces[order]

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reposition_gizmo()

    def mouseMoveEvent(self, ev):
        # self.onCameraChanged()
        super().mouseMoveEvent(ev)
        if self.gizmo is not None:
            self.gizmo.sync()

    # def mouseReleaseEvent(self, ev):
    #     super().mouseReleaseEvent(ev)
    #     self.onCameraChanged()

    def wheelEvent(self, ev):
        # self.onCameraChanged()
        super().wheelEvent(ev)
        if self.gizmo is not None:
            self.gizmo.sync()

    def onCameraChanged(self):
        # viewMatrix = np.array(list(self.viewMatrix().data()), dtype=np.float64).reshape((4, 4), order='C')
        cameraPosition = self.trueCameraPosition()

        if self.wfMeshItem is not None and self.wfMeshItem.visible():
            self.wfIsoFaces = self.sortFacesByCamera(self.wfIsoVertices, self.wfIsoFaces, cameraPosition)
            self.wfIsoMeshData.setFaces(self.wfIsoFaces)
            self.wfMeshItem.setMeshData(meshdata=self.wfIsoMeshData)
            # print(self.wfMeshData.faceNormals())

        if self.wfMeshItemSet is not None and self.wfMeshItemSet.visible():
            self.wfIsoFacesSet = self.sortFacesByCamera(self.wfIsoVerticesSet, self.wfIsoFacesSet, cameraPosition)
            self.wfIsoMeshDataSet.setFaces(self.wfIsoFacesSet)
            self.wfMeshItemSet.setMeshData(meshdata=self.wfIsoMeshDataSet)
            # self.wfMeshItemSet.update()

        # self.update()

        # rotCam = viewMatrix[:3, :3]
        # U, s, Vt = np.linalg.svd(rotCam.T)

        # rotMatrix = np.eye(4, 4, dtype=np.float64)
        # rotMatrix[:3, :3] = U @ Vt
        # rotMatrix[:3, :3] = invViewMatrix

        # transMatrix = np.eye(4, 4, dtype=np.float64)
        # transMatrix[:3, 3] = np.array([0.8, -0.8, -0.9])

        # projMatrix = np.array(list(self.projectionMatrix(self.getViewport(), self.getViewport()).data()), dtype=np.float64).reshape((4, 4), order='F')

        # self.axisItem.resetTransform()
        # self.axisItem.setTransform(self.axisItem.viewTransform().inverted()[0])

        self.removeItem(self.axisItem)
        self.addItem(self.axisItem)

    @Slot(float, float)
    def setOpacity(self, opacity: float, level: float):
        if self.wfMeshItemSet is not None:
            self.wfIsoColorsSet[:,3] = opacity
            self.wfIsoMeshDataSet.setVertexColors(self.wfIsoColorsSet)
            self.wfMeshItemSet.setMeshData(meshdata=self.wfIsoMeshDataSet)
            # self.update()
        if self.wfMeshItem is not None:
            color = self.colormap.mapToQColor(level)
            self.wfMeshItem.setColor((color.redF(), color.greenF(), color.blueF(), opacity))

    @Slot()
    def centerView(self):
        coords = []
        for item in self.latticeBoundaryItems:
            for coord in item.pos:
                local_pos = coord
                transform = item.transform()
                transform_matrix = transform.matrix()
                local_homogeneous = np.append(local_pos, 1)
                world_coords = transform_matrix @ local_homogeneous
                coords.append(world_coords[:3])
        center = pg.Vector(np.mean(coords, axis=0))
        self.setCameraParams(center=center)

    def viewRotation(self, lookDir, up=None):
        """
        World-to-camera rotation (the convention of opts['rotation']) for a camera
        looking along `lookDir` (from the viewer into the screen), with `up`
        projected onto the screen as the vertical direction. If `up` is not given
        or is parallel to `lookDir`, the world z-axis is used, or the y-axis when
        looking along z.
        """
        toCamera = -np.asarray(lookDir, dtype=float)
        toCamera = toCamera / np.linalg.norm(toCamera)

        candidates = [] if up is None else [np.asarray(up, dtype=float)]
        candidates += [np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])]
        for upVector in candidates:
            if np.linalg.norm(np.cross(toCamera, upVector)) > 1e-6 * np.linalg.norm(upVector):
                break

        # fromDirection maps the camera axes (+z = towards the viewer, +y = up)
        # to world space, i.e. camera-to-world: conjugate it for world-to-camera
        camToWorld = QQuaternion.fromDirection(QVector3D(*toCamera), QVector3D(*upVector))
        return camToWorld.conjugated()

    def setViewDirection(self, lookDir, up=None):
        """
        Point the camera along `lookDir` (Cartesian, from the viewer into the
        screen; VESTA's "direction of projection") with `up` vertical on screen.
        In 'euler' mode the screen-up is always world z (no roll), so `up` only
        has an effect there when looking along z.
        """
        if self.opts['rotationMethod'] == 'quaternion':
            self.setCameraPosition(rotation=self.viewRotation(lookDir, up))
        else:
            # pyqtgraph's own rotation -> (elevation, azimuth) conversion is unreliable,
            # so compute the spherical angles of the camera position directly
            n = -np.asarray(lookDir, dtype=float)
            n = n / np.linalg.norm(n)
            elevation = np.degrees(np.arcsin(np.clip(n[2], -1.0, 1.0)))
            if np.hypot(n[0], n[1]) < 1e-6:
                # Looking along z: azimuth is free, choose it to match the up vector
                rotation = self.viewRotation(lookDir, up)
                screenUp = rotation.conjugated().rotatedVector(QVector3D(0.0, 1.0, 0.0))
                azimuth = np.degrees(np.arctan2(screenUp.y(), screenUp.x())) - 180.0 * (n[2] > 0)
            else:
                azimuth = np.degrees(np.arctan2(n[1], n[0]))
            self.setCameraPosition(elevation=elevation, azimuth=azimuth)

        if self.gizmo is not None:
            self.gizmo.sync()

    def trueCameraPosition(self):
        """
        Camera position in world coordinates from the view matrix. Unlike
        GLViewWidget.cameraPosition(), this is also right in 'quaternion' mode.
        """
        inverted, _ = self.viewMatrix().inverted()
        p = inverted.map(QVector3D(0.0, 0.0, 0.0))
        return np.array([p.x(), p.y(), p.z()])

    @Slot(Qt.CheckState)
    def changeProjection(self, state):
        if state == Qt.CheckState.Checked:
            self.opts['fov'] = 1
            self.opts['distance'] = 5000
        else:
            self.opts['fov'] = 60
            self.opts['distance'] = 75
        self.update()

    @Slot(Qt.CheckState)
    def viewLattice(self, state):
        visible = (state == Qt.CheckState.Checked)
        for item in self.baseLatticeItems:
            item.setVisible(visible)
        for item in self.latticeItems:
            item.setVisible(visible)
        for item in self.atomNameItems:
            item.setVisible(visible)

    @Slot(Qt.CheckState)
    def viewAtomNames(self, state):
        visible = (state == Qt.CheckState.Checked)
        for item in self.atomNameItems:
            item.setVisible(visible)

    @Slot(Qt.CheckState)
    def viewBoundaries(self, state):
        visible = (state == Qt.CheckState.Checked)
        for item in self.latticeBoundaryItems:
            item.setVisible(visible)