"""
Geometry of the probability-density plots: isosurfaces with their normals,
and the colors of the volume. Pure functions of their arguments, so they can
run in the worker thread: only the upload to the GPU happens in the GUI.

Normals are computed vectorized: pyqtgraph's MeshData computes them with a
Python loop over vertices, which takes seconds for the meshes of fine grids.
"""

import numpy as np
import pyqtgraph as pg

from .volume_item import volumeRGBA


def vertexNormals(vertices, faces):
    """Unit normals at the vertices: the sum of the normals of their faces, weighted by area."""
    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces)
    faceNormals = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]])
    normals = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], faceNormals)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    # Vertices of zero-area faces only (marching cubes produces some where the
    # surface goes through grid points) have no normal: they cover no pixels,
    # but give them a unit one, as the shader normalizes it
    normals = np.where(lengths > 1e-12, normals / np.maximum(lengths, 1e-12), np.float32([0.0, 0.0, 1.0]))
    return normals.astype(np.float32)


def isoMesh(density, level):
    """Isosurface of `density` at `level`: vertices (grid index coordinates), faces and normals."""
    vertices, faces = pg.isosurface(density, level)
    vertices = np.asarray(vertices, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.uint32)
    return vertices, faces, vertexNormals(vertices, faces) if len(faces) else np.zeros_like(vertices)


def isoSetLevels(numLevels):
    return np.linspace(0.01, 0.99, numLevels)


def isoSetMesh(density, numLevels, colormap, opacity, context=None):
    """
    Nested isosurfaces as one mesh (so their faces are sorted together), each
    in the color of its level: vertices, faces, normals and vertex colors.
    """
    levels = isoSetLevels(numLevels)
    if context is not None:
        context.stage('Isosurfaces', len(levels))
    meshes, colors = [], []
    for level in levels:
        vertices, faces, normals = isoMesh(density, level)
        meshes.append((vertices, faces, normals))
        color = colormap.map(np.array([level]), mode='float')[0]
        colors.append(np.tile(np.array([color[0], color[1], color[2], opacity], dtype=np.float32), (len(vertices), 1)))
        if context is not None:
            context.advance()

    offsets = np.cumsum([0] + [len(vertices) for vertices, faces, normals in meshes[:-1]])
    vertices = np.concatenate([m[0] for m in meshes]) if meshes else np.empty((0, 3), np.float32)
    faces = np.concatenate([m[1] + np.uint32(o) for m, o in zip(meshes, offsets)]) if meshes else np.empty((0, 3), np.uint32)
    normals = np.concatenate([m[2] for m in meshes]) if meshes else np.empty((0, 3), np.float32)
    colors = np.concatenate(colors) if colors else np.empty((0, 4), np.float32)
    return vertices, faces, normals, colors


def volumeColors(density, colormap, opacity, contrast, sliceDensity):
    return volumeRGBA(density, colormap, opacity, contrast, sliceDensity)
