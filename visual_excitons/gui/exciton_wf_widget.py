from PySide6.QtCore import Qt, Slot

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

        self.glOptions = 'opaque'
        # self.glOptions = 'additive'
        # self.glOptions = 'translucent'
        self.isoGlOptions = {
            GL.GL_DEPTH_TEST: False,
            GL.GL_CULL_FACE: False,
            GL.GL_BLEND: True,
            # 'glBlendFuncSeparate': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA),
            # 'glBlendFuncSeparate': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
            'glBlendFunc': (GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA),
            # 'glBlendEquationSeparate': (GL.GL_FUNC_ADD, GL.GL_FUNC_ADD)
        }

        self.setCameraPosition(distance=50)
        self.setBackgroundColor('w')
        self.setUpdatesEnabled(True)

        self.wfIsoVertices = None
        self.wfIsoFaces = None

        self.wfIsoVerticesSet = np.empty((0, 3), dtype=float)
        self.wfIsoFacesSet = np.empty((0, 3), dtype=int)
        self.wfIsoColorsSet = np.empty((0, 4), dtype=np.float32)

        self.wfMeshItem = None
        self.wfMeshItemSet = None
        self.wfVolItem = None

        self.baseLatticeItems = []
        self.latticeBoundaryItems = []
        self.latticeItems = []
        self.atomNameItems = []
        self.fixedParticleItem = None

        self.plotFixedParticle()

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
    def plotWfIso(self, wf, level, transform):
        self.wfIsoVertices, self.wfIsoFaces = pg.isosurface(wf, level)

        color = self.colormap.mapToQColor(level)
        # colors = np.full(shape=(len(verts), 4), fill_value=[color.redF(), color.greenF(), color.blueF(), opacity], dtype=np.float32)

        # meshdata = gl.MeshData(vertexes=verts, faces=faces, vertexColors=colors)
        meshdata = gl.MeshData(vertexes=self.wfIsoVertices, faces=self.wfIsoFaces)

        self.clearWfMeshItem()

        # self.wfMeshItem = gl.GLMeshItem(meshdata=meshdata, smooth=True, computeNormals=True, shader=self.shader, glOptions=self.glOptions)
        self.wfMeshItem = gl.GLMeshItem(meshdata=meshdata, smooth=True, shader='balloon', glOptions=self.isoGlOptions, drawEdges=False)
        self.wfMeshItem.setColor((color.redF(), color.greenF(), color.blueF(), 0.5))

        self.wfMeshItem.setTransform(pg.Transform3D(transform))

        self.addItem(self.wfMeshItem)

        self.onCameraChanged()

    @Slot(list, int, list)
    def plotWfIsoSet(self, wf, numLevels, transform):
        self.clearWfMeshItemSet()

        tr = pg.Transform3D(transform)

        for level in np.linspace(0.01, 0.99, numLevels):
            verts, faces = pg.isosurface(wf, level)

            self.wfIsoFacesSet = np.concatenate((self.wfIsoFacesSet, faces + self.wfIsoVerticesSet.shape[0]), axis=0)
            self.wfIsoVerticesSet = np.concatenate((self.wfIsoVerticesSet, verts), axis=0)

            color = self.colormap.mapToQColor(level)
            color.setAlphaF(0.5)
            colors = np.full(shape=(len(verts), 4), fill_value=[color.redF(), color.greenF(), color.blueF(), color.alphaF()], dtype=np.float32)
            self.wfIsoColorsSet = np.concatenate((self.wfIsoColorsSet, colors), axis=0)

        meshdata = gl.MeshData(vertexes=self.wfIsoVerticesSet, faces=self.wfIsoFacesSet, vertexColors=self.wfIsoColorsSet)

        self.wfMeshItemSet = gl.GLMeshItem(meshdata=meshdata, shader=None, glOptions=self.isoGlOptions, smooth=True, computeNormals=True)
        # meshItem.setColor((color.redF(), color.greenF(), color.blueF(), color.alphaF()))
        self.wfMeshItemSet.setTransform(tr)

        # self.wfMeshItemSet.append(meshItem)
        # self.wfIsoColorsSet.append(color)

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

        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[0]], color=(1.0, 0.0, 0.0, 1.0), width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[1]], color=(0.0, 1.0, 0.0, 1.0), width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        self.baseLatticeItems.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[2]], color=(0.0, 0.0, 1.0, 1.0), width=1.0, antialias=True, mode='lines', glOptions='opaque'))

        self.addItem(self.baseLatticeItems[0])
        self.addItem(self.baseLatticeItems[1])
        self.addItem(self.baseLatticeItems[2])



    def plotUnitCellBoundaries(self, baseVectors, offset):
        color = (0.5, 0.5, 0.5, 1.0)

        ucellBoundaries = []
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[0]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[1]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[[0.0, 0.0, 0.0], baseVectors[2]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))

        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0], baseVectors[0] + baseVectors[1]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0], baseVectors[0] + baseVectors[2]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1], baseVectors[1] + baseVectors[0]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1], baseVectors[1] + baseVectors[2]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2], baseVectors[2] + baseVectors[0]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2], baseVectors[2] + baseVectors[1]], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))

        apex = baseVectors[0] + baseVectors[1] + baseVectors[2]

        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0] + baseVectors[1], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[0] + baseVectors[2], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1] + baseVectors[0], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[1] + baseVectors[2], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2] + baseVectors[0], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))
        ucellBoundaries.append(gl.GLLinePlotItem(pos=[baseVectors[2] + baseVectors[1], apex], color=color, width=1.0, antialias=True, mode='lines', glOptions='opaque'))

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

            meshItem = gl.GLMeshItem(meshdata=meshData, smooth=True, shader=self.shader, glOptions='opaque', drawEdges=False)
            meshItem.translate(position[0], position[1], position[2])

            self.latticeItems.append(meshItem)
            self.addItem(meshItem)

            textItem = gl.GLTextItem(pos=position, color=(255, 255, 255, 255), text=chemical_symbols[atomicNumbers[i]], alignment=Qt.AlignmentFlag.AlignCenter)
            self.atomNameItems.append(textItem)
            self.addItem(textItem)


    def plotSupercellAtoms(self, atomicPositions):
        numAtoms = len(atomicPositions)

        for i in range(numAtoms):
            meshData = gl.MeshData.sphere(10, 10, 2)
            meshItem = gl.GLMeshItem(meshdata=meshData, smooth=True, shader=self.shader, glOptions='opaque', drawEdges=False)
            meshItem.translate(atomicPositions[i][0], atomicPositions[i][1], atomicPositions[i][2])

            self.addItem(meshItem)

    def plotFixedParticle(self):
        meshData = gl.MeshData.sphere(8, 8, 0.3)
        faceColors = np.full(shape=(meshData.faceCount(), 4), fill_value=[1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        meshData.setFaceColors(faceColors)

        self.fixedParticleItem = gl.GLMeshItem(meshdata=meshData, smooth=True, shader=self.shader, glOptions='opaque', drawEdges=False)
        self.addItem(self.fixedParticleItem)

    def translateFixedParticle(self, position):
        self.fixedParticleItem.resetTransform()
        self.fixedParticleItem.translate(position[0], position[1], position[2])

    def sortFacesByCamera(self, vertices, faces, cameraPos):
        centroids = vertices[faces].mean(axis=1)
        dists = np.linalg.norm(centroids - cameraPos, axis=1)
        order = np.argsort(dists)[::-1]
        return faces[order]

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        self.onCameraChanged()

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self.onCameraChanged()

    def wheelEvent(self, ev):
        super().wheelEvent(ev)
        self.onCameraChanged()

    def onCameraChanged(self):
        cam = self.cameraPosition()

        if self.wfMeshItem is not None and self.wfMeshItem.visible():
            newFaces = self.sortFacesByCamera(self.wfIsoVertices, self.wfIsoFaces, np.array([cam.x(), cam.y(), cam.z()]))
            self.wfMeshItem.setMeshData(meshdata=gl.MeshData(vertexes=self.wfIsoVertices, faces=newFaces), smooth=True)

        if self.wfMeshItemSet is not None and self.wfMeshItemSet.visible():
            newFaces = self.sortFacesByCamera(self.wfIsoVerticesSet, self.wfIsoFacesSet, np.array([cam.x(), cam.y(), cam.z()]))
            # self.wfMeshItemSet.setMeshData(meshdata=gl.MeshData(vertexes=self.wfIsoVerticesSet, faces=newFaces, vertexColors=self.wfIsoColorsSet), smooth=True)
            # self.wfMeshItemSet.meshDataChanged()
            self.wfMeshItemSet.setMeshData(vertexes=self.wfIsoVerticesSet, faces=newFaces, vertexColors=self.wfIsoColorsSet)

        # for i in range(len(self.wfMeshItemSet)):
        #     if self.wfMeshItemSet[i].visible():
        #         self.wfMeshItemSet[i].setMeshData(meshdata=self.sortedMeshData(self.wfIsoVerticesSet[i], self.wfIsoFacesSet[i], cam), smooth=True)

        self.update()

    def sortedMeshData(self, vertices, faces, cam):
        newFaces = self.sortFacesByCamera(vertices, faces, np.array([cam.x(), cam.y(), cam.z()]))
        return gl.MeshData(vertexes=vertices, faces=newFaces)

    @Slot(float)
    def setOpacity(self, opacity: float):
        if self.wfMeshItemSet is not None and self.wfMeshItemSet.visible():
            self.wfIsoColorsSet[:,3] = opacity
            self.wfMeshItemSet.setMeshData(vertexes=self.wfIsoVerticesSet, faces=self.wfIsoFacesSet, vertexColors=self.wfIsoColorsSet)
            self.update()