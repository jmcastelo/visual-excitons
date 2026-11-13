from PySide6.QtCore import Qt, Slot
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QQuaternion, QVector3D, QMatrix4x4, QColor
from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat

from OpenGL import GL

import pyqtgraph as pg
import pyqtgraph.opengl as gl
import itertools

import numpy as np

from PySide6.QtWidgets import QLabel

from .sorted_mesh_item import SortedMeshItem
from .atom_labels_item import AtomLabelsItem
from .axes_3d_widget import cellInfoHtml
from .volume_item import volumeRGBA, FloatVolumeItem
from .gl_style import (OPAQUE_STAGE, TRANSLUCENT_STAGE, OPAQUE_GL_OPTIONS, TRANSLUCENT_GL_OPTIONS,
                       headlightShader, litEdgesShader, enableMultisampling, spheresMeshData, cylindersMeshData,
                       MSAA_SAMPLES, PrecomputedNormalsMeshData)
from .wf_geometry import isoMesh, isoSetMesh, volumeColors
from visual_excitons.core.atomic_data import covalent_radii, jmol_colors, chemical_symbols, ANGSTROM_TO_BOHR



class ExcitonWfWidget(gl.GLViewWidget):
    def __init__(self, parent = None):
        gl.GLViewWidget.__init__(self, parent, rotationMethod='quaternion')

        self.colormap = pg.colormap.get('viridis')

        # Smooth edges of atoms, lines and surfaces
        enableMultisampling(self)

        # Shader of the isosurface set (see setIsoSetStyle)
        self.isoSetShader = litEdgesShader

        self.setCameraPosition(distance=75)
        self.setBackgroundColor((255, 255, 255, 255))
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)

        self.wfIsoMeshData = None

        self.wfIsoVerticesSet = np.empty((0, 3), dtype=float)
        self.wfIsoFacesSet = np.empty((0, 3), dtype=int)
        self.wfIsoColorsSet = np.empty((0, 4), dtype=float)
        self.wfIsoMeshDataSet = None

        self.wfMeshItem = None
        self.wfMeshItemSet = None
        self.wfVolItem = None

        self.latticeBoundaryItems = []
        self.latticeItems = []
        # Atom names: labels on the atom surfaces, as one depth-tested item
        self.atomLabels = AtomLabelsItem()
        self.addItem(self.atomLabels)
        self.latticeVisible = True
        self.atomNamesVisible = True
        # Bonds: one mesh for the whole supercell
        self.bondsItem = None
        self.bondsVisible = True
        # Applied to the boundaries drawn later too (the lattice is redrawn often:
        # dataset, supercell, atom sizes...)
        self.boundariesVisible = True
        self.fixedParticleItem = None
        # Plane of the analysis cut (see setCutPlane)
        self.cutPlaneItems = []

        self.plotFixedParticle()

        self.gizmo = None

        # Cell parameters overlay (top-left corner)
        self.cellLattice = None
        self.showCellInfo = True
        self.cellInfoLabel = QLabel(self)
        self.cellInfoLabel.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.cellInfoLabel.setTextFormat(Qt.TextFormat.RichText)
        self.setDarkTheme(False)
        self.cellInfoLabel.move(10, 10)
        self.cellInfoLabel.hide()

        # Orthographic projection by default (see projectionMatrix)
        self.orthographic = True
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
        self.clearBondsItem()

    def clearBondsItem(self):
        if self.bondsItem is not None:
            self.removeItem(self.bondsItem)
            self.bondsItem = None

    def clearAtomNamesItems(self):
        self.atomLabels.clear()

    # Probability density: geometry computed by wf_geometry (possibly in the
    # worker thread), uploaded here

    def plotWfIso(self, wf, level, transform, opacity):
        self.showIsoMesh(isoMesh(wf, level), level, transform, opacity)

    def plotWfIsoSet(self, wf, numLevels, transform, opacity):
        self.showIsoSetMesh(isoSetMesh(wf, numLevels, self.colormap, opacity), transform)

    def plotWfVol(self, wf, sliceDensity, transform, opacity=0.8, contrast=1.0):
        self.showVolume(volumeColors(wf, self.colormap, opacity, contrast, sliceDensity), sliceDensity, transform)

    def showIsoMesh(self, mesh, level, transform, opacity):
        """The isosurface at `level`: `mesh` = (vertices, faces, normals) from wf_geometry.isoMesh."""
        vertices, faces, normals = mesh
        color = self.colormap.mapToQColor(level)
        self.wfIsoMeshData = PrecomputedNormalsMeshData(normals, vertexes=vertices, faces=faces)

        self.clearWfMeshItem()
        # Faces are drawn back to front for correct transparency
        self.wfMeshItem = SortedMeshItem(meshdata=self.wfIsoMeshData, shader=headlightShader, smooth=True)
        self.wfMeshItem.setColor((color.redF(), color.greenF(), color.blueF(), opacity))
        self.wfMeshItem.setGLOptions(TRANSLUCENT_GL_OPTIONS)
        self.wfMeshItem.setDepthValue(TRANSLUCENT_STAGE)
        self.wfMeshItem.setTransform(pg.Transform3D(transform))
        self.addItem(self.wfMeshItem)

    def showIsoSetMesh(self, mesh, transform):
        """The isosurface set: `mesh` = (vertices, faces, normals, colors) from wf_geometry.isoSetMesh."""
        vertices, faces, normals, colors = mesh
        self.clearWfMeshItemSet()
        self.wfIsoVerticesSet, self.wfIsoFacesSet, self.wfIsoColorsSet = vertices, faces, colors
        self.wfIsoMeshDataSet = PrecomputedNormalsMeshData(normals, vertexes=vertices, faces=faces, vertexColors=colors)

        # All levels in one mesh, so faces of different levels are sorted together
        self.wfMeshItemSet = SortedMeshItem(meshdata=self.wfIsoMeshDataSet, shader=self.isoSetShader, smooth=True)
        self.wfMeshItemSet.setGLOptions(TRANSLUCENT_GL_OPTIONS)
        self.wfMeshItemSet.setDepthValue(TRANSLUCENT_STAGE)
        self.wfMeshItemSet.setTransform(pg.Transform3D(transform))
        self.addItem(self.wfMeshItemSet)

    def showVolume(self, rgba, sliceDensity, transform):
        """The volume: `rgba` from wf_geometry.volumeColors."""
        self.clearWfVolItem()
        # Translucent like the isosurfaces: drawn after opaque items and writing no
        # depth, otherwise even its invisible slices would hide what is drawn later
        self.wfVolItem = FloatVolumeItem(data=rgba, sliceDensity=sliceDensity, glOptions=TRANSLUCENT_GL_OPTIONS)
        self.wfVolItem.setDepthValue(TRANSLUCENT_STAGE)
        self.wfVolItem.setTransform(pg.Transform3D(transform))
        self.addItem(self.wfVolItem)

    def plotBaseLatticeVectors(self, baseVectors):
        # Cartesian axes and lattice vectors are only shown in the axes gizmo
        self.cellLattice = np.asarray(baseVectors, dtype=float)
        if self.gizmo is not None:
            self.gizmo.setLatticeVectors(self.cellLattice)
        self.updateCellInfo()

    def cameraState(self):
        """The camera (rotation, distance, center), to restore it later with setCameraState."""
        rotation = self.opts['rotation']
        center = self.opts['center']
        return {'rotation': [rotation.scalar(), rotation.x(), rotation.y(), rotation.z()],
                'distance': float(self.opts['distance']), 'center': [center.x(), center.y(), center.z()]}

    def setCameraState(self, state):
        w, x, y, z = (float(v) for v in state['rotation'])
        rotation = QQuaternion(w, x, y, z)
        if rotation.length() < 1e-9:
            raise ValueError('invalid camera rotation')
        self.setCameraParams(rotation=rotation.normalized(), distance=float(state['distance']),
                             center=pg.Vector(*(float(c) for c in state['center'])))
        if self.gizmo is not None:
            self.gizmo.sync()

    def cameraAxes(self):
        """World directions towards the viewer and up on the screen."""
        camToWorld = self.opts['rotation'].conjugated()
        toViewer = camToWorld.rotatedVector(QVector3D(0.0, 0.0, 1.0))
        up = camToWorld.rotatedVector(QVector3D(0.0, 1.0, 0.0))
        return np.array([toViewer.x(), toViewer.y(), toViewer.z()]), np.array([up.x(), up.y(), up.z()])

    def setCutPlane(self, vertices):
        """Show the plane of the analysis cut: its polygon inside the supercell; None or empty to hide it."""
        for item in self.cutPlaneItems:
            self.removeItem(item)
        self.cutPlaneItems.clear()
        if vertices is None or len(vertices) < 3:
            return
        vertices = np.asarray(vertices, dtype=float)
        faces = np.array([[0, i, i + 1] for i in range(1, len(vertices) - 1)])
        surface = gl.GLMeshItem(meshdata=gl.MeshData(vertexes=vertices, faces=faces), color=(1.0, 0.55, 0.0, 0.18),
                                smooth=False, drawEdges=False, glOptions=TRANSLUCENT_GL_OPTIONS)
        surface.setDepthValue(TRANSLUCENT_STAGE)
        outline = gl.GLLinePlotItem(pos=np.vstack([vertices, vertices[:1]]), color=(1.0, 0.55, 0.0, 1.0), width=2.0,
                                    antialias=True, mode='line_strip', glOptions=OPAQUE_GL_OPTIONS)
        for item in (surface, outline):
            self.addItem(item)
            self.cutPlaneItems.append(item)

    def backgroundColor(self):
        """Background of the scene, as a QColor."""
        return QColor.fromRgbF(*self.opts['bgcolor'])

    @Slot(bool)
    def setDarkTheme(self, dark: bool):
        """Background of the scene and colors of the overlays for a dark or light theme."""
        if dark:
            self.setBackgroundColor((30, 31, 34, 255))
            style = 'background-color: rgba(43, 45, 48, 220); color: #dfe1e5; border: 1px solid #55585e;'
        else:
            self.setBackgroundColor((255, 255, 255, 255))
            style = 'background-color: rgba(255, 255, 255, 210); color: #222; border: 1px solid #bbb;'
        self.cellInfoLabel.setStyleSheet(f'QLabel {{ {style} border-radius: 4px; padding: 4px; }}')
        if self.gizmo is not None:
            self.gizmo.setDarkTheme(dark)

    def updateCellInfo(self):
        if self.cellLattice is None:
            self.cellInfoLabel.hide()
            return
        showReciprocal = self.gizmo is not None and self.gizmo.showReciprocal
        self.cellInfoLabel.setText(cellInfoHtml(self.cellLattice, showReciprocal))
        self.cellInfoLabel.adjustSize()
        self.cellInfoLabel.setVisible(self.showCellInfo)

    @Slot(bool)
    def setShowCellInfo(self, show: bool):
        self.showCellInfo = show
        self.updateCellInfo()

    @Slot(bool)
    def setShowReciprocalVectors(self, show: bool):
        if self.gizmo is not None:
            self.gizmo.setShowReciprocal(show)
        self.updateCellInfo()

    @Slot(int)
    def setIsoSetStyle(self, index: int):
        """0: lit surfaces with emphasized edges, 1: edges only (x-ray look)."""
        self.isoSetShader = litEdgesShader if index == 0 else 'balloon'
        if self.wfMeshItemSet is not None:
            self.wfMeshItemSet.setShader(self.isoSetShader)

    def plotUnitCellBoundaries(self, baseVectors, offset):
        a, b, c = (np.asarray(v, dtype=float) for v in baseVectors[:3])
        corners = {(i, j, k): i * a + j * b + k * c for i in (0, 1) for j in (0, 1) for k in (0, 1)}
        # The 12 edges of the cell: pairs of corners differing in one index
        edges = [(p, q) for p in corners for q in corners if p < q and sum(x != y for x, y in zip(p, q)) == 1]
        segments = np.array([[corners[p], corners[q]] for p, q in edges]).reshape(-1, 3)

        item = gl.GLLinePlotItem(pos=segments, color=(0.5, 0.5, 0.5, 1.0), width=1.0, antialias=True, mode='lines',
                                 glOptions=OPAQUE_GL_OPTIONS)
        item.translate(offset[0], offset[1], offset[2])
        item.setVisible(self.boundariesVisible)
        self.latticeBoundaryItems.append(item)
        self.addItem(item)

    def plotUnitCellAtoms(self, atomicNumbers, atomicPositions, offset, radiusScale=0.5):
        numAtoms = len(atomicNumbers)
        centers = offset + np.asarray(atomicPositions, dtype=float)[:numAtoms]
        # Covalent radii (angstrom) in scene units (Bohr), scaled for a ball-and-stick look
        radii = covalent_radii[np.asarray(atomicNumbers, dtype=int)] * ANGSTROM_TO_BOHR * radiusScale

        # All atoms of the cell as a single mesh
        colors = [list(jmol_colors[z]) + [1.0] for z in atomicNumbers]
        meshItem = gl.GLMeshItem(meshdata=spheresMeshData(centers, radii, colors), smooth=True,
                                 shader=headlightShader, glOptions=OPAQUE_GL_OPTIONS, drawEdges=False)
        meshItem.setDepthValue(OPAQUE_STAGE)
        meshItem.setVisible(self.latticeVisible)
        self.latticeItems.append(meshItem)
        self.addItem(meshItem)

        self.atomLabels.addLabels(centers, radii, [chemical_symbols[z] for z in atomicNumbers])

    def plotBonds(self, starts, ends, atomicNumbers, radius, uniformColor=None):
        """
        Bonds as half-bond cylinders (see core.bonds.halfBonds): from `starts`
        to `ends`, radius in Bohr, each half in the color of the atom of atomic
        number `atomicNumbers` it belongs to, or all in `uniformColor` (RGB).
        """
        self.clearBondsItem()
        if len(starts) == 0:
            return

        if uniformColor is None:
            colors = np.column_stack([jmol_colors[np.asarray(atomicNumbers, dtype=int)], np.ones(len(starts))])
        else:
            colors = np.tile(list(uniformColor) + [1.0], (len(starts), 1))

        self.bondsItem = gl.GLMeshItem(meshdata=cylindersMeshData(starts, ends, radius, colors), smooth=True,
                                       shader=headlightShader, glOptions=OPAQUE_GL_OPTIONS, drawEdges=False)
        self.bondsItem.setDepthValue(OPAQUE_STAGE)
        self.bondsItem.setVisible(self.latticeVisible and self.bondsVisible)
        self.addItem(self.bondsItem)

    def plotFixedParticle(self):
        meshData = spheresMeshData([[0.0, 0.0, 0.0]], [0.3], [[1.0, 1.0, 1.0, 1.0]])
        self.fixedParticleItem = gl.GLMeshItem(meshdata=meshData, smooth=True, shader=headlightShader,
                                               glOptions=OPAQUE_GL_OPTIONS, drawEdges=False)
        self.addItem(self.fixedParticleItem)

    def translateFixedParticle(self, position):
        self.fixedParticleItem.resetTransform()
        self.fixedParticleItem.translate(position[0], position[1], position[2])

    def projectionMatrix(self, region, viewport):
        """
        True orthographic projection when enabled, perspective otherwise.

        The orthographic view shows the same area as a perspective view with the
        current fov and distance would at the view center, so zooming (which
        changes the distance), panning and pixelSize() keep working unchanged.
        Its depth is linear, so the depth buffer stays precise however far the
        camera is: a perspective frustum with a tiny fov at a large distance
        resolves depth very poorly, making nearby surfaces z-fight.
        """
        if not self.orthographic:
            return super().projectionMatrix(region, viewport)

        x0, y0, w, h = viewport
        dist = self.opts['distance']
        r = dist * np.tan(0.5 * np.radians(self.opts['fov']))
        t = r * h / w
        left = r * ((region[0] - x0) * (2.0 / w) - 1)
        right = r * ((region[0] + region[2] - x0) * (2.0 / w) - 1)
        bottom = t * ((region[1] - y0) * (2.0 / h) - 1)
        top = t * ((region[1] + region[3] - y0) * (2.0 / h) - 1)

        # Depth range around the view center, in world units (Bohr)
        depthRange = 1.0e4 + dist
        tr = QMatrix4x4()
        tr.ortho(left, right, bottom, top, dist - depthRange, dist + depthRange)
        return tr

    def renderImage(self, width, height, transparent=False):
        """
        The scene rendered off screen at `width` x `height` pixels, antialiased,
        with a transparent background if `transparent`. Lines, whose width is
        in pixels, are widened in proportion to the size of the image.
        """
        self.makeCurrent()
        maximum = int(GL.glGetIntegerv(GL.GL_MAX_RENDERBUFFER_SIZE))
        if max(width, height) > maximum:
            raise ValueError(f'The image cannot be larger than {maximum} pixels on this graphics card')

        fboFormat = QOpenGLFramebufferObjectFormat()
        fboFormat.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        fboFormat.setSamples(MSAA_SAMPLES)
        fboFormat.setInternalTextureFormat(GL.GL_RGBA8)
        fbo = QOpenGLFramebufferObject(width, height, fboFormat)

        background = self.opts['bgcolor']
        scale = height / max(self.deviceHeight(), 1)
        lineWidths = [(item, item.width) for item in self.latticeBoundaryItems]
        try:
            if transparent:
                # Transparent black: the image is read as premultiplied, where a
                # color brighter than its alpha would overflow when composited
                self.opts['bgcolor'] = (0.0, 0.0, 0.0, 0.0)
            for item, lineWidth in lineWidths:
                item.setData(width=lineWidth * scale)
            fbo.bind()
            GL.glViewport(0, 0, width, height)
            self.paint(region=(0, 0, width, height), viewport=(0, 0, width, height))
            image = fbo.toImage()
        finally:
            fbo.release()
            self.opts['bgcolor'] = background
            for item, lineWidth in lineWidths:
                item.setData(width=lineWidth)
            self.update()
        return image

    def paint(self, **kwargs):
        # glClear() respects the depth write mask. Translucent items turn depth
        # writes off and are drawn last, so without this the next frame would not
        # clear the depth buffer: opaque items (atoms, lines...) redrawn at the same
        # depth would fail the depth test and vanish into the background.
        GL.glDepthMask(GL.GL_TRUE)
        super().paint(**kwargs)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reposition_gizmo()

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if self.gizmo is not None:
            self.gizmo.sync()

    def wheelEvent(self, ev):
        super().wheelEvent(ev)
        if self.gizmo is not None:
            self.gizmo.sync()

    @Slot(float, float)
    def setIsoOpacity(self, opacity: float, level: float):
        if self.wfMeshItem is not None:
            color = self.colormap.mapToQColor(level)
            self.wfMeshItem.setColor((color.redF(), color.greenF(), color.blueF(), opacity))

    @Slot(float)
    def setIsoSetOpacity(self, opacity: float):
        if self.wfMeshItemSet is not None:
            self.wfIsoColorsSet[:, 3] = opacity
            self.wfIsoMeshDataSet.setVertexColors(self.wfIsoColorsSet)
            self.wfMeshItemSet.setMeshData(meshdata=self.wfIsoMeshDataSet)

    @Slot()
    def sceneBounds(self):
        """
        The box (lowest and highest corner) of what is visible: atoms, cell
        boundaries, bonds, the isosurfaces and the volume; None if nothing is.
        """
        boxes = []

        def add(item, low, high):
            transform = item.transform()
            for corner in itertools.product(*zip(low, high)):
                mapped = transform.map(QVector3D(*map(float, corner)))
                boxes.append((mapped.x(), mapped.y(), mapped.z()))

        meshes = self.latticeItems + [self.bondsItem, self.wfMeshItem, self.wfMeshItemSet]
        for item in meshes:
            if item is None or not item.visible():
                continue
            vertices = item.opts['meshdata'].vertexes() if item.opts.get('meshdata') is not None else None
            if vertices is not None and len(vertices):
                add(item, vertices.min(axis=0), vertices.max(axis=0))
        for item in self.latticeBoundaryItems:
            if item.visible() and item.pos is not None and len(item.pos):
                points = np.asarray(item.pos)
                add(item, points.min(axis=0), points.max(axis=0))
        if self.wfVolItem is not None and self.wfVolItem.visible():
            shape = np.asarray(self.wfVolItem.data.shape[:3], dtype=float)
            add(self.wfVolItem, np.zeros(3), shape)
        if not boxes:
            return None
        points = np.array(boxes)
        return points.min(axis=0), points.max(axis=0)

    def centerView(self):
        """Center the view on what is visible (the middle of its box), keeping the zoom and direction."""
        bounds = self.sceneBounds()
        if bounds is None:
            # Nothing visible (e.g. all hidden): the cells, if drawn
            coords = [item.transform().map(QVector3D(*map(float, point))) for item in self.latticeBoundaryItems
                      for point in item.pos]
            if not coords:
                return
            bounds = (np.min([[c.x(), c.y(), c.z()] for c in coords], axis=0),
                      np.max([[c.x(), c.y(), c.z()] for c in coords], axis=0))
        low, high = bounds
        self.setCameraParams(center=pg.Vector(*((low + high) / 2)))

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

    @Slot(Qt.CheckState)
    def changeProjection(self, state):
        self.orthographic = (state == Qt.CheckState.Checked)
        if self.orthographic:
            self.opts['fov'] = 1
            self.opts['distance'] = 5000
        else:
            self.opts['fov'] = 60
            self.opts['distance'] = 75
        self.update()

    @Slot(Qt.CheckState)
    def viewLattice(self, state):
        self.latticeVisible = (state == Qt.CheckState.Checked)
        for item in self.latticeItems:
            item.setVisible(self.latticeVisible)
        self.atomLabels.setVisible(self.latticeVisible and self.atomNamesVisible)
        if self.bondsItem is not None:
            self.bondsItem.setVisible(self.latticeVisible and self.bondsVisible)

    @Slot(Qt.CheckState)
    def viewBonds(self, state):
        self.bondsVisible = (state == Qt.CheckState.Checked)
        if self.bondsItem is not None:
            self.bondsItem.setVisible(self.latticeVisible and self.bondsVisible)

    @Slot(Qt.CheckState)
    def viewAtomNames(self, state):
        self.atomNamesVisible = (state == Qt.CheckState.Checked)
        self.atomLabels.setVisible(self.latticeVisible and self.atomNamesVisible)

    @Slot(Qt.CheckState)
    def viewBoundaries(self, state):
        self.boundariesVisible = (state == Qt.CheckState.Checked)
        for item in self.latticeBoundaryItems:
            item.setVisible(self.boundariesVisible)