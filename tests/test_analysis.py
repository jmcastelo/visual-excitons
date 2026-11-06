"""Analysis of the density: distribution of distances from the fixed particle, plane cuts."""

import numpy as np
import pytest

from visual_excitons.core.analysis import (voxelVectors, gridPositions, radialDistribution, planeAxes, planeCut,
                                           atomsNearPlane)


def gaussian(shape, voxels, center, sigma):
    r2 = np.sum((gridPositions(shape, voxels) - center) ** 2, axis=-1)
    return np.exp(-r2 / (2 * sigma ** 2))


def test_voxel_vectors():
    voxels = voxelVectors(np.diag([2.0, 3.0, 4.0]), [3, 1, 2], (12, 6, 16))
    np.testing.assert_allclose(voxels, np.diag([0.5, 0.5, 0.5]))


def test_radial_distribution_of_a_gaussian():
    """3D Gaussian of width sigma: mean distance sigma sqrt(8/pi), rms sigma sqrt(3)."""
    voxels = np.diag([0.25, 0.25, 0.25]) + np.array([[0, 0, 0], [0.05, 0, 0], [0, 0, 0]])   # slightly skewed
    shape = (80, 80, 80)
    center = gridPositions(shape, voxels)[40, 40, 40]
    sigma = 2.0
    result = radialDistribution(gaussian(shape, voxels, center, sigma), voxels, center)

    assert result['mean'] == pytest.approx(sigma * np.sqrt(8 / np.pi), rel=0.01)
    assert result['rms'] == pytest.approx(sigma * np.sqrt(3), rel=0.01)
    assert result['median'] == pytest.approx(1.538 * sigma, rel=0.02)   # chi distribution, 3 degrees of freedom
    assert result['median'] < result['r90']
    assert result['cumulative'][-1] == pytest.approx(1.0)
    np.testing.assert_allclose(np.sum(result['probability'] * np.diff(result['r'])[0]), 1.0)
    assert result['boundary'] < 1e-3


def test_truncated_density_is_flagged():
    voxels = np.diag([0.5, 0.5, 0.5])
    shape = (20, 20, 20)
    center = gridPositions(shape, voxels)[10, 10, 10]
    result = radialDistribution(gaussian(shape, voxels, center, sigma=4.0), voxels, center)
    assert result['boundary'] > 0.1


def test_radial_distribution_needs_a_density():
    with pytest.raises(ValueError):
        radialDistribution(np.zeros((4, 4, 4)), np.eye(3), [0, 0, 0])


def test_plane_axes():
    for normal in ([0, 0, 1], [1, 1, 1], [0.3, -2, 0.5]):
        u, v, n = planeAxes(normal)
        np.testing.assert_allclose([u @ u, v @ v, n @ n], 1.0)
        np.testing.assert_allclose([u @ v, u @ n, v @ n], 0.0, atol=1e-12)
        np.testing.assert_allclose(np.cross(u, v), n, atol=1e-12)   # right-handed

    # Screen up given: v is up, u is right as seen from the normal's side
    u, v, n = planeAxes([0, 0, 1], inPlane=[0, 1, 0.3])
    np.testing.assert_allclose(v, [0, 1, 0]) and np.testing.assert_allclose(u, [1, 0, 0])

    # Otherwise u along the lattice vector most nearly in the plane
    lattice = np.array([[1.0, 0.0, 0.2], [0.5, 1.0, 0.0], [0.0, 0.0, 3.0]])
    u, v, n = planeAxes([0, 0, 1], latticeVectors=lattice)
    np.testing.assert_allclose(u, np.array([0.5, 1.0, 0.0]) / np.hypot(0.5, 1.0))

    with pytest.raises(ValueError):
        planeAxes([0, 0, 0])


def test_plane_cut_interpolates_and_masks():
    """A density linear in position is interpolated exactly; outside the supercell is NaN."""
    voxels = np.array([[0.5, 0.0, 0.0], [0.1, 0.5, 0.0], [0.0, 0.0, 0.5]])
    shape = (20, 16, 12)
    positions = gridPositions(shape, voxels)
    density = 1.0 + 0.3 * positions[..., 0] - 0.2 * positions[..., 1] + 0.1 * positions[..., 2]
    point = positions[10, 8, 6]

    cut = planeCut(density, voxels, point, normal=[1, 1, 2])
    S, T = np.meshgrid(cut['s'], cut['t'])
    samples = point + S[..., None] * cut['u'] + T[..., None] * cut['v']
    expected = 1.0 + samples @ np.array([0.3, -0.2, 0.1])
    inside = ~np.isnan(cut['values'])
    assert inside.sum() > 100 and (~inside).sum() > 100          # the plane leaves the supercell
    np.testing.assert_allclose(cut['values'][inside], expected[inside], atol=1e-9)
    # The point itself is sampled
    origin = (np.argmin(np.abs(cut['t'])), np.argmin(np.abs(cut['s'])))
    assert cut['values'][origin] == pytest.approx(density[10, 8, 6], abs=0.05)


def test_atoms_near_plane():
    positions = np.array([[0, 0, 0.0], [1, 2, 0.4], [3, 1, -0.6], [0, 0, 2.0]])
    axes = planeAxes([0, 0, 1], inPlane=[0, 1, 0])
    numbers, inPlane, distance = atomsNearPlane(positions, [1, 2, 3, 4], [0, 0, 0], axes, tolerance=0.5)
    assert list(numbers) == [1, 2]
    np.testing.assert_allclose(inPlane, [[0, 0], [1, 2]])
    np.testing.assert_allclose(distance, [0.0, 0.4])


def test_plane_supercell_polygon():
    from visual_excitons.core.analysis import planeSupercellPolygon
    box = np.diag([2.0, 3.0, 4.0])
    # Plane z = 1: the 2 x 3 rectangle at that height, in order around it
    polygon = planeSupercellPolygon(box, [1, 1, 1], [0, 0, 1])
    assert len(polygon) == 4 and np.allclose(polygon[:, 2], 1.0)
    edges = np.linalg.norm(np.diff(np.vstack([polygon, polygon[:1]]), axis=0), axis=1)
    np.testing.assert_allclose(sorted(edges), [2, 2, 3, 3])
    # Through the center, normal (1 1 1) of a cube: a regular hexagon
    hexagon = planeSupercellPolygon(np.eye(3), [0.5, 0.5, 0.5], [1, 1, 1])
    assert len(hexagon) == 6
    np.testing.assert_allclose(np.linalg.norm(hexagon - 0.5, axis=1), np.sqrt(0.5))
    # Missing the supercell
    assert len(planeSupercellPolygon(np.eye(3), [0, 0, 5], [0, 0, 1])) == 0
