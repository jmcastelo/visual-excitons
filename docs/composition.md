# Composition of an exciton

[← Documentation](../README.md#documentation)

The **Composition** panel shows where the selected exciton lives in reciprocal space and what it is made of. It follows the exciton selected in any spectrum (dispersion or absorption), at any computed Q-point; `Show its composition`, in the `Selected exciton` section of the Spectra controls, opens it. It is computed while the panel is shown, from the BSE database of the exciton's Q-point, in the background; another exciton of the same Q-point is shown at once.

An exciton is a sum of transitions from a valence band v to a conduction band c, each with a weight |A|² (they add up to 1). At a finite momentum Q, a transition takes the hole from k−Q to the electron at k: the electron's weights are at k, the hole's at k−Q, and the two maps are shifted by Q. At Γ they coincide.

- `Sum degenerate states` (on by default) sums the states degenerate with the exciton (within 10 meV, as its [wave function](wavefunction.md) does): a single state of a degenerate group is an arbitrary mixture of them, and its map would not have the symmetry of the crystal. The states summed are named at the top of the panel.
- `Export data…` saves the weight of every k-point (reduced and Cartesian coordinates, the electron's and the hole's) and the composition by band pairs and bands as a CSV file.

## k-space

The weight of each k-point of the grid, relative to the largest, in the first Brillouin zone (its Wigner–Seitz cell, for any lattice), with its special points labelled (K′, the time-reversed partner of K, included).

- `Particle`: the electron's weights (at k), the hole's (at k−Q), or their average.
- `Scale`: linear, or logarithmic, which brings out contributions down to 0.1 % of the largest.
- `Colormap`: the colors of the weights.
- `Q-path`: the path of the dispersion, where it lies in what is shown.

For a **layer** (a 2D material, with vacuum along one lattice vector), the map is the plane of its k-points: each k-point is a tile (the cell of the grid around it: hexagons for a hexagonal grid), clipped to the zone.

For a **bulk crystal**, `View` chooses:

- `3D`: the Brillouin zone as a wireframe, with the k-points as spheres sized and colored by their weight. `Hide below` leaves out those weighing less than a share of the largest (5 % by default), so that those behind are seen. Drag to rotate, as the 3D view of the wave function; the axes gizmo shows the Cartesian axes and the reciprocal lattice vectors.
- `Plane`: the k-points of one plane of the grid perpendicular to c (`0` goes through Γ), on the section of the zone by that plane; or `Sum`, all the planes added up (with the special points and Q-path of the plane through Γ).

`Export image…` saves what the tab shows as an image.

## Transitions

- **Band pairs**: the valence–conduction pairs, largest first, down to 0.05 % (the others together), with bands numbered as in yambo.
- **Bands**: the weight of each valence band (the hole's) and of each conduction band (the electron's).
- **k-points**: those weighing most, for the electron and for the hole (one list at Γ), in reduced coordinates, with the special point they are at or near.

The composition and the panel's settings are part of [sessions](sessions.md): a session opens with them shown, without computing them again.
