# Composition of an exciton

[← Documentation](../README.md#documentation)

The **Composition** panel shows where the selected exciton lives in reciprocal space and what it is made of. It follows the exciton selected in any spectrum (dispersion or absorption), at any computed Q-point; `Show its composition`, in the `Selected exciton` section of the Spectra controls, opens it. It is computed while the panel is shown, from the BSE database of the exciton's Q-point, in the background; another exciton of the same Q-point is shown at once.

An exciton is a sum of transitions from a valence band v to a conduction band c, each with a weight |A|² (they add up to 1). At a finite momentum Q, a transition takes the hole from k−Q to the electron at k: the electron's weights are at k, the hole's at k−Q, and the two maps are shifted by Q. At Γ they coincide.

- The states degenerate with the exciton (within 10 meV) are summed with it when `Sum degenerate states` is on, in the [Selected exciton](spectra.md) section of the Spectra controls (the setting of its wave function and band structure too): a single state of a degenerate group is an arbitrary mixture of them, and its map would not have the symmetry of the crystal. The states summed are named at the top of the panel.
- `Export data…` saves the weight of every k-point (reduced and Cartesian coordinates, the electron's and the hole's) and the composition by band pairs and bands as a CSV file.

## k-space

The weight of each k-point of the grid, relative to the largest, in the first Brillouin zone (its Wigner–Seitz cell, for any lattice), with its special points labelled (K′, the time-reversed partner of K, included).

- `Particle`: the electron's weights (at k), the hole's (at k−Q), or their average. At Γ they are the same, and the choice is disabled.
- `Scale`: linear, or logarithmic, which brings out contributions down to 0.1 % of the largest.
- `Colormap`: the colors of the weights.
- `Q-path`: the path of the dispersion, where it lies in what is shown.

For a **layer** (a 2D material, with vacuum along one lattice vector), the map is the plane of its k-points: each k-point is a tile (the cell of the grid around it: hexagons for a hexagonal grid), clipped to the zone.

For a **bulk crystal**, `View` chooses:

- `3D`: the Brillouin zone as a wireframe, with the k-points as lit spheres sized and colored by their weight, translucent (`Opacity`, 0.6 by default) so that those behind show through. `Hide below` leaves out those weighing less than a share of the largest (5 % by default). Drag to rotate, as the 3D view of the wave function; the axes gizmo shows the Cartesian axes and the reciprocal lattice vectors.
- `Plane`: the k-points of one plane of the grid perpendicular to c (`0` goes through Γ), on the section of the zone by that plane; or `Sum`, all the planes added up (with the special points and Q-path of the plane through Γ).

`Export image…` saves what the tab shows as an image.

## Transitions

- **Band pairs**: the valence–conduction pairs, largest first, down to 0.05 % (the others together), with bands numbered as in yambo.
- **Bands**: the weight of each valence band (the hole's) and of each conduction band (the electron's).
- **k-points**: those weighing most, for the electron and for the hole (one list at Γ), in reduced coordinates, with the special point they are at or near.

## Symmetry and spin

`Analyse` finds, for the selected exciton, from the wave functions (in the background):

- **Its symmetry**: the irreducible representation of the little group of its Q-point (the symmetries of the crystal that leave Q unchanged, found with spglib) that its degenerate group transforms as, e.g. `Au` of S₆ for the lowest exciton of BiI3 at Γ, or `A` of C₁ at a Q-point no symmetry leaves unchanged. States within 1 meV make the group here (not the 10 meV of `Sum degenerate states`, which lumps nearby states into groups that are not irreducible); when the states found are not a closed group (an accidental near-degeneracy), it says so instead of giving a label. It follows the group theory of M. Nalabothula et al., Phys. Rev. B 113, 205130 (2026).
- **Its spin** along the `Spin axis` (z, x, y, or the third lattice vector: the normal of a layer along c), for each state of its group in the basis where it is definite, with the electron's and the hole's parts (they add up to it), in units of ħ (A. R. Kshirsagar et al., Phys. Rev. B 112, 12 (2025)). It needs spinor wave functions (a calculation with spin–orbit coupling); without them, a note says so. For example, in a WSe₂ monolayer the spin-forbidden dark excitons have a spin close to ±1 along z, the bright ones close to 0.

It loads the wave functions of the bands of the BSE, as a wave function does (and reuses them if already loaded). The first time for a dataset it also computes the representation matrices of the electronic states under each symmetry needed: about 0.02 s per k-point and symmetry, e.g. a minute for BiI3 8×8×8 at Γ, about 19 minutes for WSe₂ 72×72 at Γ; the tab estimates it before you start. They are kept for the session and on disk (in the program's cache folder, never next to the data), so the next Q-points, and the next sessions, are fast. A note warns when the BSE kernel is not the one recommended for the Q-point (`Lbar` at Γ, `Lfull` at a finite Q), and when the Q-point is not supported (a BSE with coupling, or non-symmorphic symmetries giving projective representations at a boundary Q-point).

Once analysed, the symmetry and the spin also appear in one line in the `Selected exciton` section of the Spectra controls.

The composition, the symmetry and spin, and the panel's settings are part of [sessions](sessions.md): a session opens with them shown, without computing them again.
