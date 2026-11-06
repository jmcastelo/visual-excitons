"""Geometry and color helpers of the 3D views (no OpenGL context needed)."""

import numpy as np
import pyqtgraph as pg
import pytest

from visual_excitons.gui.gl_style import cylindersMeshData, spheresMeshData, unitSphere
from visual_excitons.gui.volume_item import volumeRGBA
from visual_excitons.gui.axes_3d_widget import cellParameters, reciprocalLattice, cellInfoHtml
from visual_excitons.core.atomic_data import ANGSTROM_TO_BOHR


# Meshes

def test_cylinders_geometry():
    rng = np.random.default_rng(0)
    starts = rng.normal(size=(5, 3))
    ends = starts + rng.normal(size=(5, 3))
    # One axis along a coordinate axis: the perpendicular must still be found
    ends[0] = starts[0] + [0.0, 0.0, 2.0]
    radius, sides = 0.3, 12
    md = cylindersMeshData(starts, ends, radius, np.tile([1, 0, 0, 1], (5, 1)), sides=sides)

    vertices = md.vertexes().reshape(5, 2, sides, 3)
    normals = md.vertexNormals().reshape(5, 2, sides, 3)
    axes = (ends - starts) / np.linalg.norm(ends - starts, axis=1, keepdims=True)

    # Rings at both ends, at the radius from the axis, normals radial and unit
    np.testing.assert_allclose(vertices.mean(axis=2), np.stack([starts, ends], axis=1), atol=1e-5)
    offsets = vertices - np.stack([starts, ends], axis=1)[:, :, None, :]
    np.testing.assert_allclose(np.linalg.norm(offsets, axis=-1), radius, atol=1e-5)
    np.testing.assert_allclose(np.einsum('cesk,ck->ces', offsets, axes), 0.0, atol=1e-5)
    np.testing.assert_allclose(normals, offsets / radius, atol=1e-5)

    faces = md.faces()
    assert faces.shape == (5 * 2 * sides, 3)
    assert faces.min() == 0 and faces.max() == 5 * 2 * sides - 1


def test_spheres_mesh():
    vertices, faces = unitSphere()
    md = spheresMeshData([[0, 0, 0], [5, 0, 0]], [1.0, 2.0], [[1, 0, 0, 1], [0, 0, 1, 1]])
    v = md.vertexes()
    assert len(v) == 2 * len(vertices) and len(md.faces()) == 2 * len(faces)
    np.testing.assert_allclose(np.linalg.norm(v[:len(vertices)], axis=1), 1.0, atol=1e-5)
    np.testing.assert_allclose(np.linalg.norm(v[len(vertices):] - [5, 0, 0], axis=1), 2.0, atol=1e-5)
    np.testing.assert_allclose(md.vertexColors()[-1], [0, 0, 1, 1])


# Volume

@pytest.mark.parametrize('opacity', [0.2, 0.8])
@pytest.mark.parametrize('sliceDensity', [1, 5])
@pytest.mark.parametrize('contrast', [0.5, 1.0, 2.0])
def test_volume_opacity_along_densest_ray(opacity, sliceDensity, contrast):
    """Compositing the slices along the densest grid row gives exactly the requested opacity."""
    x = np.linspace(-1, 1, 21)
    density = np.exp(-(x[:, None, None] ** 2 + 2 * x[None, :, None] ** 2 + 3 * x[None, None, :] ** 2) * 4)
    rgba = volumeRGBA(density / density.max(), pg.colormap.get('viridis'), opacity, contrast, sliceDensity)

    alpha = rgba[..., 3].astype(float)
    # Opacity of each grid row: every voxel is drawn as sliceDensity slices
    rowOpacity = [1 - np.prod((1 - alpha) ** sliceDensity, axis=axis) for axis in range(3)]
    assert max(r.max() for r in rowOpacity) == pytest.approx(opacity, rel=1e-4)


def test_volume_empty_and_colors():
    colormap = pg.colormap.get('viridis')
    assert not volumeRGBA(np.zeros((4, 4, 4)), colormap, 0.8, 1.0, 5)[..., 3].any()

    density = np.random.default_rng(1).random((6, 6, 6))
    rgba = volumeRGBA(density, colormap, 0.8, 1.0, 5)
    np.testing.assert_allclose(rgba[..., :3], colormap.mapToFloat(density)[..., :3], atol=1e-6)
    # More density, more opacity
    order = np.argsort(density.ravel())
    assert np.all(np.diff(rgba[..., 3].ravel()[order]) >= 0)


# Cell parameters

def test_reciprocal_lattice_duality():
    lattice = np.array([[3.0, 0, 0], [1.0, 4.0, 0], [0.5, 0.2, 5.0]])
    np.testing.assert_allclose(lattice @ reciprocalLattice(lattice).T, 2 * np.pi * np.eye(3), atol=1e-12)


def test_cell_parameters_hexagonal():
    a, c = 2.5, 6.7
    lattice = np.array([[a, 0, 0], [-a / 2, a * np.sqrt(3) / 2, 0], [0, 0, c]])
    p = cellParameters(lattice)
    assert (p['a'], p['b'], p['c']) == pytest.approx((a, a, c))
    assert (p['alpha'], p['beta'], p['gamma']) == pytest.approx((90, 90, 120))


def test_cell_info_is_in_angstrom():
    html = cellInfoHtml(np.eye(3) * 2.0 * ANGSTROM_TO_BOHR, showReciprocal=True)
    assert 'a = 2.0000 Å' in html and 'α = 90.000°' in html and 'a* = 3.1416 Å⁻¹' in html


# Colormaps of the density

def test_colormaps():
    from visual_excitons.gui.colormaps import COLORMAPS, makeColormap, colormapIcon, DEFAULT_COLORMAP
    assert DEFAULT_COLORMAP in COLORMAPS
    for label in COLORMAPS:
        colormap = makeColormap(label)
        low, high = colormap.map(np.array([0.0, 1.0]), mode='float')[:, :3]
        assert not np.allclose(low, high), label

    plain, reversed_ = makeColormap('Fire'), makeColormap('Fire', reverse=True)
    np.testing.assert_allclose(plain.map(np.array([0.0]), mode='float'), reversed_.map(np.array([1.0]), mode='float'))
    # Reversing a copy leaves PyQtGraph's shared colormap alone
    np.testing.assert_allclose(makeColormap('Fire').map(np.array([0.0]), mode='float'), plain.map(np.array([0.0]), mode='float'))
    # Unknown labels (e.g. from old settings) fall back to the default
    np.testing.assert_allclose(makeColormap('No such map').getLookupTable(nPts=8), makeColormap(DEFAULT_COLORMAP).getLookupTable(nPts=8))
    assert not colormapIcon(plain).isNull()
