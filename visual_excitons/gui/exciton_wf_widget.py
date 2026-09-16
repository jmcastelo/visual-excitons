from PySide6.QtCore import Qt, Slot
from PySide6.QtOpenGLWidgets import QOpenGLWidget

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

        self.axisItem = None

        self.plotFixedParticle()
        self.plotAxes()

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
        data = np.zeros(wf.shape + (4,), np.ubyte)
        for i in range(wf.shape[0]):
            for j in range(wf.shape[1]):
                for k in range(wf.shape[2]):
                    c = self.colormap.mapToByte(wf[i, j, k])
                    c[3] *= wf[i, j, k]
                    data[i, j, k] = c

        self.clearWfVolItem()

        self.wfVolItem = gl.GLVolumeItem(data=data, sliceDensity=sliceDensity)
        self.wfVolItem.setTransform(pg.Transform3D(transform))
        self.addItem(self.wfVolItem)

    def plotBaseLatticeVectors(self, baseVectors):
        self.clearBaseLatticeItems()

        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[0]], color=(1.0, 0.0, 0.0, 1.0), width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[1]], color=(0.0, 1.0, 0.0, 1.0), width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[2]], color=(0.0, 0.0, 1.0, 1.0), width=1.0, antialias=True, mode='lines', glOptions=self.glOptions))

        self.addItem(self.baseLatticeItems[0])
        self.addItem(self.baseLatticeItems[1])
        self.addItem(self.baseLatticeItems[2])

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

    def plotAxes(self):
        self.axisItem = gl.GLAxisItem(glOptions=self.glOptions)
        self.axisItem.setDepthValue(2)
        self.addItem(self.axisItem)
        self.onCameraChanged()

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

    def mouseMoveEvent(self, ev):
        # self.onCameraChanged()
        super().mouseMoveEvent(ev)
        self.update()

    # def mouseReleaseEvent(self, ev):
    #     super().mouseReleaseEvent(ev)
    #     self.onCameraChanged()

    def wheelEvent(self, ev):
        # self.onCameraChanged()
        super().wheelEvent(ev)
        self.update()

    def onCameraChanged(self):
        # viewMatrix = np.array(list(self.viewMatrix().data()), dtype=np.float64).reshape((4, 4), order='C')
        cameraPosition = np.array([self.cameraPosition().x(), self.cameraPosition().y(), self.cameraPosition().z()])

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
        for item in self.items:
            if isinstance(item, gl.GLLinePlotItem):
                for coord in item.pos:
                    local_pos = coord
                    transform = item.transform()
                    transform_matrix = transform.matrix()
                    local_homogeneous = np.append(local_pos, 1)
                    world_coords = transform_matrix @ local_homogeneous
                    coords.append(world_coords[:3])
            elif isinstance(item, gl.GLMeshItem):
                for coord in item.vertexes:
                    local_pos = coord
                    transform = item.transform()
                    transform_matrix = transform.matrix()
                    local_homogeneous = np.append(local_pos, 1)
                    world_coords = transform_matrix @ local_homogeneous
                    coords.append(world_coords[:3])
        center = pg.Vector(np.mean(coords, axis=0))
        self.setCameraParams(center=center)

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
    def viewBoundaries(self, state):
        visible = (state == Qt.CheckState.Checked)
        for item in self.latticeBoundaryItems:
            item.setVisible(visible)