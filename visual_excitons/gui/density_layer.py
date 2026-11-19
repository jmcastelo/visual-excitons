"""
One density drawn in the 3D view (the wave function's, or a particle's own,
see WavefunctionView.layers): its items for the three plot types (isosurface,
isosurface set, volume), its colormap, and whether it is shown. The geometry
comes from wf_geometry, prepared by WavefunctionPanels (DensityDisplay).
"""

import numpy as np
import pyqtgraph as pg

from .sorted_mesh_item import SortedMeshItem
from .volume_item import FloatVolumeItem
from .gl_style import TRANSLUCENT_STAGE, TRANSLUCENT_GL_OPTIONS, headlightShader, litEdgesShader, \
    PrecomputedNormalsMeshData

ISOSURFACE, ISOSURFACE_SET, VOLUME = range(3)


class DensityLayer:
    """The items of one density in `view` (a GLViewWidget)."""

    def __init__(self, view):
        self.view = view
        self.colormap = pg.colormap.get('viridis')
        # Shader of the isosurface set (see setIsoSetStyle)
        self.isoSetShader = litEdgesShader
        self.mesh = self.meshSet = self.volume = None
        self.meshData = self.meshDataSet = None
        self.setColors = np.empty((0, 4), dtype=float)
        self.shown = True
        self.plotType = ISOSURFACE

    def items(self):
        return [self.mesh, self.meshSet, self.volume]

    def itemExists(self, index):
        return 0 <= index < 3 and self.items()[index] is not None

    def showItem(self, index):
        """Show the plot of type `index` (hidden all, if the density is switched off)."""
        self.plotType = index
        for i, item in enumerate(self.items()):
            if item is not None:
                item.setVisible(self.shown and i == index)

    def setShown(self, shown):
        self.shown = bool(shown)
        self.showItem(self.plotType)

    def clear(self):
        self.clearMesh()
        self.clearMeshSet()
        self.clearVolume()

    def _remove(self, item):
        if item is not None:
            self.view.removeItem(item)

    def clearMesh(self):
        self._remove(self.mesh)
        self.mesh = None

    def clearMeshSet(self):
        self._remove(self.meshSet)
        self.meshSet = None
        self.setColors = np.empty((0, 4), dtype=float)

    def clearVolume(self):
        self._remove(self.volume)
        self.volume = None

    def showIsoMesh(self, mesh, level, transform, opacity):
        """The isosurface at `level`: `mesh` = (vertices, faces, normals) from wf_geometry.isoMesh."""
        vertices, faces, normals = mesh
        color = self.colormap.mapToQColor(level)
        self.meshData = PrecomputedNormalsMeshData(normals, vertexes=vertices, faces=faces)
        self.clearMesh()
        # Faces are drawn back to front for correct transparency
        self.mesh = SortedMeshItem(meshdata=self.meshData, shader=headlightShader, smooth=True)
        self.mesh.setColor((color.redF(), color.greenF(), color.blueF(), opacity))
        self.mesh.setGLOptions(TRANSLUCENT_GL_OPTIONS)
        self.mesh.setDepthValue(TRANSLUCENT_STAGE)
        self.mesh.setTransform(pg.Transform3D(transform))
        self.view.addItem(self.mesh)

    def showIsoSetMesh(self, mesh, transform):
        """The isosurface set: `mesh` = (vertices, faces, normals, colors) from wf_geometry.isoSetMesh."""
        vertices, faces, normals, colors = mesh
        self.clearMeshSet()
        self.setColors = colors
        self.meshDataSet = PrecomputedNormalsMeshData(normals, vertexes=vertices, faces=faces, vertexColors=colors)
        # All levels in one mesh, so faces of different levels are sorted together
        self.meshSet = SortedMeshItem(meshdata=self.meshDataSet, shader=self.isoSetShader, smooth=True)
        self.meshSet.setGLOptions(TRANSLUCENT_GL_OPTIONS)
        self.meshSet.setDepthValue(TRANSLUCENT_STAGE)
        self.meshSet.setTransform(pg.Transform3D(transform))
        self.view.addItem(self.meshSet)

    def showVolume(self, rgba, sliceDensity, transform):
        """The volume: `rgba` from wf_geometry.volumeColors."""
        self.clearVolume()
        # Translucent like the isosurfaces: drawn after opaque items and writing no
        # depth, otherwise even its invisible slices would hide what is drawn later
        self.volume = FloatVolumeItem(data=rgba, sliceDensity=sliceDensity, glOptions=TRANSLUCENT_GL_OPTIONS)
        self.volume.setDepthValue(TRANSLUCENT_STAGE)
        self.volume.setTransform(pg.Transform3D(transform))
        self.view.addItem(self.volume)

    def setIsoOpacity(self, opacity, level):
        if self.mesh is not None:
            color = self.colormap.mapToQColor(level)
            self.mesh.setColor((color.redF(), color.greenF(), color.blueF(), opacity))

    def setIsoSetOpacity(self, opacity):
        if self.meshSet is not None:
            self.setColors[:, 3] = opacity
            self.meshDataSet.setVertexColors(self.setColors)
            self.meshSet.setMeshData(meshdata=self.meshDataSet)

    def setIsoSetStyle(self, index):
        """0: lit surfaces with emphasized edges, 1: edges only (x-ray look)."""
        self.isoSetShader = litEdgesShader if index == 0 else 'balloon'
        if self.meshSet is not None:
            self.meshSet.setShader(self.isoSetShader)
