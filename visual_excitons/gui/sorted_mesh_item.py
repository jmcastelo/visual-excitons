import time

import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtCore import QTimer
from pyqtgraph.opengl.items.GLMeshItem import DirtyFlag


class SortedMeshItem(gl.GLMeshItem):
    """
    GLMeshItem for translucent meshes, drawing its triangles back to front.

    Alpha blending without depth writes is only correct when farther triangles
    are drawn first. Right before painting, if the camera has moved relative to
    the item since the last sort (rotation, pan or zoom), the faces are
    reordered by the distance from the camera to their centroids (farthest
    first). Since this happens in paint(), every camera change is covered:
    mouse, wheel, view presets, centering, projection changes...

    Only the triangle index buffer is reordered and re-uploaded to the GPU:
    vertices, normals and colors are left untouched, so nothing is recomputed.

    Distances are measured in view space, with the item's own transform
    included. With perspective projection, faces are ordered by their distance
    to the eye, which changes with panning and zooming. With orthographic
    projection, where every point is viewed along the same direction, they are
    ordered by depth along the viewing axis, which is exact.

    Requires indexed drawing: smooth=True and mesh data without face-indexed
    arrays, as produced by MeshData(vertexes=..., faces=..., vertexColors=...).
    """

    # Large meshes (in faces) are re-sorted at most every SORT_INTERVAL seconds while
    # the camera moves, and once more when it stops: sorting them takes tens of
    # milliseconds, too long for every frame
    LARGE_MESH = 200_000
    SORT_INTERVAL = 0.15

    def __init__(self, **kwds):
        self._lastSort = 0.0
        self._sortPending = False
        self._baseFaces = None   # faces in their original order
        self._centroids = None   # face centroids in item (local) coordinates
        self._sortMatrix = None  # model-view matrix used for the last sort
        super().__init__(**kwds)

    def meshDataChanged(self):
        super().meshDataChanged()
        self._baseFaces = None
        self._centroids = None
        self._sortMatrix = None

    def _sortLater(self):
        self._sortPending = False
        if self.view() is not None:
            self.update()   # repaint: sorts for the camera as it is now

    def parseMeshData(self):
        md = self.opts['meshdata']
        if self.vertexes is None and md is not None and md._faces is not None:
            # Computing normals makes MeshData cache face-indexed vertices, after
            # which GLMeshItem would switch to non-indexed drawing on any re-parse
            # (e.g. a color change), which cannot be sorted. Drop that cache:
            # it is rebuilt on demand.
            md._vertexesIndexedByFaces = None
        return super().parseMeshData()

    def paint(self):
        # Make sure mesh data is parsed and uploaded before reordering faces;
        # the parent's paint() then finds nothing left to parse
        if dirtyBits := self.parseMeshData():
            self.upload_vertex_buffers(dirtyBits)
        self.sortFaces()
        super().paint()

    def sortFaces(self):
        if self.faces is None or len(self.faces) == 0:
            return

        if self._baseFaces is None:
            self._baseFaces = self.faces.copy()
            self._centroids = self.vertexes[self._baseFaces].mean(axis=1).astype(np.float32)
            self._sortMatrix = None

        # Model-view matrix: item (local) coordinates -> view space, camera at the origin
        modelView = np.array(self.modelViewMatrix().data(), dtype=np.float32).reshape(4, 4, order='F')

        if self._sortMatrix is not None and np.array_equal(modelView, self._sortMatrix):
            return

        if len(self._baseFaces) > self.LARGE_MESH and self._sortMatrix is not None:
            elapsed = time.monotonic() - self._lastSort
            if elapsed < self.SORT_INTERVAL:
                # Keep the previous order for this frame; sort when the interval is over
                if not self._sortPending:
                    self._sortPending = True
                    QTimer.singleShot(int(1000 * (self.SORT_INTERVAL - elapsed)) + 1, self._sortLater)
                return

        self._lastSort = time.monotonic()
        self._sortMatrix = modelView

        projection = np.array(self.projectionMatrix().data(), dtype=np.float32).reshape(4, 4, order='F')
        if projection[3, 2] == 0.0:
            # Orthographic projection: farthest means most negative view-space z,
            # which needs only the third row of the matrix
            depth = self._centroids @ modelView[2, :3] + modelView[2, 3]
            order = np.argsort(depth)
        else:
            # Perspective projection: farthest from the eye, at the view-space origin
            viewCentroids = self._centroids @ modelView[:3, :3].T + modelView[:3, 3]
            order = np.argsort(-np.einsum('ij,ij->i', viewCentroids, viewCentroids))
        self.faces = np.ascontiguousarray(self._baseFaces[order])
        self.upload_vertex_buffers(DirtyFlag.FACES)
