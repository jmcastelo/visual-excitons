# Where the particles of an exciton are

[← Documentation](../README.md#documentation)

This page explains the physics and the numerics behind [placing the fixed particle](wavefunction.md#placing-the-fixed-particle) of the wave function: what the 3D view shows, what the **hole density** and the **electron density** are, why a common choice of the fixed position (on an atom) can be poor, how the densities are computed cheaply with natural transition orbitals, and how all of it was checked against YamboPy's own wave functions, on BiI3 and WSe2.

Contents:

1. [The exciton wave function](#1-the-exciton-wave-function)
2. [What the 3D view shows](#2-what-the-3d-view-shows)
3. [The density of each particle](#3-the-density-of-each-particle)
4. [Why the fixed position matters](#4-why-the-fixed-position-matters)
5. [Nodes on the atoms](#5-nodes-on-the-atoms)
6. [Natural transition orbitals](#6-natural-transition-orbitals)
7. [Cutoff and grid](#7-cutoff-and-grid)
8. [Finding the maxima](#8-finding-the-maxima)
9. [Numerical checks](#9-numerical-checks)
10. [In the program](#10-in-the-program)
11. [Approximations and limits](#11-approximations-and-limits)

---

## 1. The exciton wave function

Yambo solves the Bethe–Salpeter equation (BSE) in a basis of transitions from valence bands $`v`$ to conduction bands $`c`$. In the Tamm–Dancoff approximation, an exciton $`\lambda`$ of momentum $`\mathbf{Q}`$ is a set of coefficients $`A^\lambda_{\mathbf{k}cv}`$, and its wave function, as YamboPy computes it (`ex_wf2Real` in `yambopy/bse/realSpace_excitonwf.py`), is

```math
\Psi_\lambda(\mathbf{r}_e, \mathbf{r}_h) = \sum_{\mathbf{k}, c, v} A^\lambda_{\mathbf{k}cv}\, \psi_{c\mathbf{k}}(\mathbf{r}_e)\, \psi^*_{v,\mathbf{k}-\mathbf{Q}}(\mathbf{r}_h)
```

with $`\psi_{n\mathbf{k}}`$ the Bloch functions of the bands: the electron is in the conduction band at $`\mathbf{k}`$, the hole in the valence band at $`\mathbf{k}-\mathbf{Q}`$ (Yambo's table of transitions is $`(\mathbf{k}, v, c)`$, $`\mathbf{k}`$ being the electron's).

Two things to keep in mind:

- **One sum over $`\mathbf{k}`$, not two.** The exciton has a definite momentum, so the hole's wave vector is fixed by the electron's: the coefficients are $`A_{\mathbf{k}cv}`$, a three-index table, the one the [Composition panel](composition.md) reads.
- **A sum of products, not a product.** Each term is a product of a function of $`\mathbf{r}_e`$ and one of $`\mathbf{r}_h`$, but the sum is not: the two particles are correlated. Each Bloch function spreads over the whole crystal; it is the sum over $`\mathbf{k}`$ that keeps the electron near the hole. There is in general no "wave function of the hole" on its own, $`\Psi \neq F_e(\mathbf{r}_e)\,F_h(\mathbf{r}_h)`$.

With spinors (spin–orbit coupling), $`\psi`$ has two components and $`\Psi`$ four, $`\Psi_{\sigma_e \sigma_h}`$; the densities below sum over them. With collinear spin, there is a sum over the spin index $`s`$ of the coefficients, $`A_{s\mathbf{k}cv}`$. Beyond the Tamm–Dancoff approximation, an anti-resonant part adds terms with the roles of $`c`$ and $`v`$ swapped; the program supports only the Tamm–Dancoff part (section 11).

Coefficients are normalised, $`\sum_{\mathbf{k}cv} |A^\lambda_{\mathbf{k}cv}|^2 = 1`$. A group of degenerate excitons is treated by summing the densities of its states (with `Sum degenerate states`), which makes the result independent of the basis chosen within the group.

## 2. What the 3D view shows

$`|\Psi(\mathbf{r}_e, \mathbf{r}_h)|^2`$ depends on six coordinates. What is computed and drawn is a slice of it: one particle fixed at $`\mathbf{r}_0`$, the density of the other one. With the hole fixed,

```math
n_e(\mathbf{r}_e;\, \mathbf{r}_0) = |\Psi(\mathbf{r}_e, \mathbf{r}_0)|^2 ,
```

the probability density of finding the **electron** at $`\mathbf{r}_e`$ given that the hole is at $`\mathbf{r}_0`$, and the other way round with the electron fixed. The caption of the 3D view says which: "Electron density of exciton 1 at Q1, hole fixed at (…)". The program shows it relative to its own maximum, so the plot looks the same whatever its absolute size.

## 3. The density of each particle

The density of the hole wherever the electron is, the **hole density**, is the integral over the electron:

```math
\rho_h(\mathbf{r}_h) = \int |\Psi(\mathbf{r}_e, \mathbf{r}_h)|^2 \, d\mathbf{r}_e .
```

Writing out $`|\Psi|^2`$ as a double sum, the integral over $`\mathbf{r}_e`$ only involves the conduction Bloch functions, which are orthonormal (over the Born–von Kármán supercell, the crystal of $`N_\mathbf{k}`$ cells that the $`\mathbf{k}`$-grid describes):

```math
\int \psi^*_{c\mathbf{k}}(\mathbf{r}_e)\, \psi_{c'\mathbf{k}'}(\mathbf{r}_e)\, d\mathbf{r}_e = \delta_{cc'}\, \delta_{\mathbf{k}\mathbf{k}'} ,
```

so the double sum collapses to

```math
\boxed{\;\rho_h(\mathbf{r}) = \sum_{\mathbf{k}} \sum_{c} \Big|\sum_{v} A_{\mathbf{k}cv}\, \psi^*_{v,\mathbf{k}-\mathbf{Q}}(\mathbf{r})\Big|^2\;}
```

and, with the roles swapped (the valence functions orthonormal), the **electron density**

```math
\boxed{\;\rho_e(\mathbf{r}) = \sum_{\mathbf{k}} \sum_{v} \Big|\sum_{c} A_{\mathbf{k}cv}\, \psi_{c\mathbf{k}}(\mathbf{r})\Big|^2\;}
```

(summed over the spinor components, and over the states of a degenerate group).

Properties:

- **Exact.** No approximation beyond the orthonormality of the Bloch functions, which holds for the eigenstates of the Kohn–Sham Hamiltonian.
- **Periodic with the lattice.** For a lattice vector $`\mathbf{R}`$, $`\psi_{n\mathbf{k}}(\mathbf{r}+\mathbf{R}) = e^{i\mathbf{k}\cdot\mathbf{R}}\psi_{n\mathbf{k}}(\mathbf{r})`$: all the terms of the inner sum have the same $`\mathbf{k}`$, so they pick up the same phase, which the modulus removes. One unit cell holds all of $`\rho_h`$, unlike the wave function, which needs a supercell.
- **Normalised.** With the Bloch functions normalised over one unit cell, the integral of $`\rho_h`$ over the cell is $`\sum_{\mathbf{k}cv}|A_{\mathbf{k}cv}|^2 = 1`$ per state (the cross terms between different $`v`$ at the same $`\mathbf{k}`$ vanish by orthonormality). The program's maps are in units where their average over the cell is the number of states.

## 4. Why the fixed position matters

Integrating the conditional density of section 2 over the electron gives, by the definition of section 3,

```math
\int n_e(\mathbf{r}_e;\, \mathbf{r}_0)\, d\mathbf{r}_e = \int |\Psi(\mathbf{r}_e, \mathbf{r}_0)|^2\, d\mathbf{r}_e = \rho_h(\mathbf{r}_0) .
```

The **total weight of the electron density computed with the hole at $`\mathbf{r}_0`$ is the hole density at $`\mathbf{r}_0`$** (exactly, with the Bloch functions normalised over the Born–von Kármán supercell; with another normalisation, up to a factor that does not depend on $`\mathbf{r}_0`$). Where $`\rho_h`$ is small:

- the electron density is weak, and made up mostly of what the calculation leaves out or gets approximately (plane waves beyond the cutoff, the finite supercell, numerical noise), so it is **noisy**;
- shown relative to its own maximum, it **looks as strong as any other**: nothing on screen tells.

A good fixed position is therefore where the fixed particle's own density is large: its maximum, or a local maximum near an atom of interest. Each particle goes to the maximum of **its own** density: the hole where $`\rho_h`$ is largest, the electron where $`\rho_e`$ is. (The density shown, the free particle's, is not the right guide: its maximum is a likely position of the other particle.)

## 5. Nodes on the atoms

Near a nucleus at $`\boldsymbol{\tau}`$, a band function can be expanded in spherical harmonics around it,

```math
\psi(\mathbf{r}) \approx \sum_{lm} f_{lm}(|\mathbf{r}-\boldsymbol{\tau}|)\, Y_{lm}(\widehat{\mathbf{r}-\boldsymbol{\tau}}), \qquad f_{lm}(x) \propto x^{l} \text{ as } x \to 0 ,
```

so at the nucleus itself only the $`l = 0`$ (s) part survives. For bands of p or d character, $`\rho_h`$ or $`\rho_e`$ **vanishes on the atoms**, whatever the pseudopotential (the argument is one of symmetry). Fixing the hole on an atom, a common choice, can put it on a node: the worst place, by section 4.

Measured (full cutoff, section 9):

| | Density on the nucleus (of its largest) | Largest |
|---|---|---|
| BiI3, hole (valence band mostly I 5p) | I: $`10^{-4}`$; Bi: 0.33 (Bi 6s admixture) | 0.82 Å from I, in lobes |
| BiI3, electron (conduction band mostly Bi 6p), 10 Ry | Bi: 0.008; I: 0.010 | 1.1 Å from Bi |
| WSe2, hole (W 5d, in plane), 10 Ry | W: 0.012; Se: below $`10^{-4}`$ | 0.74 Å from W, in the W plane |
| WSe2, electron (W 5d$`_{z^2}`$), 10 Ry | W: 0.10 | 0.49 Å from W, straight out of the plane |

The largest values sit in lobes: around an iodine atom of BiI3, at 0.8 Å from it, the hole density averages 0.63 of the largest over directions and reaches 0.94 along the best one. At a finite $`\mathbf{Q}`$ the equivalent atoms are no longer equivalent: the density only has the symmetry of the little group of $`\mathbf{Q}`$, and at Q5 the maxima near the six iodines of BiI3 are 1.00, 0.94 and 0.88 of the largest, in pairs.

## 6. Natural transition orbitals

Computing $`\rho_h`$ directly means, for each $`\mathbf{k}`$, transforming every valence band to real space (an FFT each) and combining them: $`n_v`$ functions per $`\mathbf{k}`$ (per spinor component). The combinations can be made in reciprocal space first, and fewer of them suffice.

At each $`\mathbf{k}`$, let $`\mathbf{h}`$ be the vector of the hole's band functions $`h_v = \psi^*_{v,\mathbf{k}-\mathbf{Q}}`$ and $`A_\mathbf{k}`$ the $`n_c \times n_v`$ matrix of coefficients. The inner sums of $`\rho_h`$ are

```math
\sum_c \big|(A_\mathbf{k}\mathbf{h})_c\big|^2 = \mathbf{h}^\dagger A_\mathbf{k}^\dagger A_\mathbf{k}\, \mathbf{h} .
```

Diagonalising the Hermitian $`n_v \times n_v`$ matrix $`M_\mathbf{k} = A_\mathbf{k}^\dagger A_\mathbf{k} = W_\mathbf{k} \Lambda_\mathbf{k} W_\mathbf{k}^\dagger`$,

```math
\rho_h(\mathbf{r}) = \sum_\mathbf{k} \sum_j \lambda_{\mathbf{k}j}\, \Big|\sum_v W^*_{\mathbf{k},vj}\, \psi^*_{v,\mathbf{k}-\mathbf{Q}}(\mathbf{r})\Big|^2 .
```

The functions $`\sum_v W^*_{vj}\,\psi^*_v`$ are the **natural transition orbitals** (NTOs) of the hole at $`\mathbf{k}`$, of weights $`\lambda_{\mathbf{k}j} \ge 0`$; they are the right singular vectors of $`A_\mathbf{k} = U S V^\dagger`$, with $`\lambda = s^2`$ (the NTOs used in molecular exciton analysis, here per $`\mathbf{k}`$-point). For the electron, $`M_\mathbf{k} = A_\mathbf{k}^* A_\mathbf{k}^{T}`$ ($`n_c \times n_c`$) and the conduction functions $`\psi_{c\mathbf{k}}`$.

- **Fewer functions.** $`A_\mathbf{k}`$ has rank at most $`\min(n_c, n_v)`$, so at most that many weights are non-zero: for BiI3 (4 conduction, 10 valence bands), 4 orbitals per $`\mathbf{k}`$ instead of 10 bands. The density is the same, exactly.
- **Degenerate groups.** Summing the densities of states $`n`$ sums the matrices, $`M_\mathbf{k} = \sum_n A_\mathbf{k}^{(n)\dagger} A_\mathbf{k}^{(n)}`$: one diagonalisation for the whole group, exact.
- **Truncation with a known error.** The weights add up to the number of states ($`\sum_j \lambda_{\mathbf{k}j} = \mathrm{tr}\,M_\mathbf{k}`$). The orbitals are orthonormal combinations of orthonormal functions, so dropping a set $`D`$ of them drops a density that integrates to exactly $`\sum_{j \in D} \lambda_{\mathbf{k}j}`$: a positive density of known total. The program keeps 99.9% of the weight.

How concentrated the weight is (BiI3, 512 $`\mathbf{k}`$-points, 20480 transitions):

| Exciton | $`\mathbf{k}`$-points for 99% | Transitions $`(\mathbf{k}, c, v)`$ for 99% | NTOs for 99% (of 2048) |
|---|---|---|---|
| Q1, exciton 1 | 435 | 6727 | 1070 |
| Q1, exciton 3 | 356 | 3928 | 540 |
| Q1, exciton 10 | 217 | 2098 | 446 |
| Q5, exciton 1 | 461 | 8863 | 1249 |

The weight is spread over most $`\mathbf{k}`$-points, as expected for an exciton small in real space, and single transitions need a third of the table or more; grouped into NTOs it concentrates, roughly one dominant pair per $`\mathbf{k}`$ (pairs, the bands of BiI3 being doubly degenerate). For WSe2's lowest excitons, the NTOs kept lie at about half of its 5184 $`\mathbf{k}`$-points, those near K and K′.

## 7. Cutoff and grid

`ex_wf2Real` does not use all the plane waves: at a cutoff $`E_\text{cut}`$ (Ry) it keeps those with $`|\mathbf{k}+\mathbf{G}| \lt  \sqrt{E_\text{cut}}`$ (Bohr⁻¹, with $`2\pi`$), and builds a real-space grid of $`N_i`$ points per lattice vector (the span of the $`\mathbf{G}`$-vectors kept, plus 3). It then moves the fixed particle to the nearest grid point, $`\mathbf{r}_0 \to \mathrm{round}(N_i r_{0,i})/N_i`$.

The densities are computed **on that same grid, with the same plane waves**:

- their grid points are fixed positions `ex_wf2Real` uses as they are: placing the particle at a maximum of the density does not move it;
- they are the densities that apply to that wave function: the identity of section 4 holds within the truncated basis (section 9), and the cutoff changes the details of $`\rho`$, not just its sharpness. For the BiI3 hole, the density near bismuth peaks on the nucleus at 10 Ry (0.65 of the largest), but is a shell 0.31 Å around it at full cutoff (0.70), where the nucleus has 0.33; the iodine maximum is 0.90 Å from the atom at 10 Ry and 0.82 Å at full cutoff (within one grid spacing of 0.47 Å and 0.18 Å).

On a coarse grid, the grid point nearest a nucleus can be far from it: at 10 Ry in BiI3, the point nearest an iodine nucleus is about 0.4 Å away, in a lobe, with 0.57 of the largest hole density, against 0.001 on the nucleus itself. Whether "on an atom" lands on a node or a lobe depends on the grid: another reason to read the density at the position.

With truncated plane waves, the band functions lose a little of their norm: the average of $`\rho`$ over the cell is then slightly below the number of states (0.96–0.99 at 10 Ry for BiI3), and they are slightly non-orthonormal (section 9). Neither changes the ratios that matter.

## 8. Finding the maxima

On the grid, the local maxima are found by comparing each point with its 26 neighbours, across the faces of the cell (the density is periodic); those of at least 10% of the largest are kept.

Each NTO is a finite sum of plane waves, $`h(\mathbf{r}) = \sum_\mathbf{G} c_\mathbf{G}\, e^{i(\mathbf{k}+\mathbf{G})\cdot\mathbf{r}}`$, so $`\rho`$, its gradient and its Hessian are known exactly anywhere ($`\nabla h = \sum_\mathbf{G} i(\mathbf{k}+\mathbf{G})\, c_\mathbf{G}\, e^{i(\mathbf{k}+\mathbf{G})\cdot\mathbf{r}}`$). Newton's method on them was tried, from the maxima of a coarse map: it converged in 6 evaluations and placed the BiI3 hole maximum 0.05 Å from the best grid point (half a grid spacing), with a value 0.4% higher. It was dropped: about 50 s, slower than the whole grid at full cutoff, and its precision is lost anyway, since `ex_wf2Real` moves the fixed particle to the grid.

## 9. Numerical checks

The datasets: BiI3 bulk (8×8×8 $`\mathbf{k}`$-points, 4 conduction and 10 valence bands, spinors), exciton 1 at Q1 (Γ, 2.090 eV) and at Q5 (2.184 eV), and states 2–5 at Γ (a degenerate group); WSe2 monolayer (72×72×1, 4 + 4 bands, spinors), states 1 and 2 at Γ (1.638 and 1.643 eV, summed as degenerate within 10 meV).

**The identity of section 4, against `ex_wf2Real`.** The wave function was computed with YamboPy with a particle fixed at grid points of the density, over the Born–von Kármán supercell, and its $`|\Psi|^2`$ summed; the ratios between positions compared with those of $`\rho`$.

`ex_wf2Real` turns even supercells into odd ones (8×8×8 becomes 9×9×9, see [YamboPy issue 20](yambopy-issues.md)), one slab more than a period of $`\Psi`$. Over that, the ratios agree within about 1% (BiI3 hole, 5 Ry):

| Hole at | Q1: $`\sum\lvert\Psi\rvert^2`$ | Q1: $`\rho_h`$ | Q5: $`\sum\lvert\Psi\rvert^2`$ | Q5: $`\rho_h`$ |
|---|---|---|---|---|
| on I (reference) | 1 | 1 | 1 | 1 |
| on Bi | 0.2495 | 0.2513 | 0.3382 | 0.3419 |
| I + 0.8 Å along z | 2.466 | 2.474 | 3.445 | 3.461 |
| (½, ½, ½) | 0.0186 | 0.0183 | 0.0968 | 0.0974 |

Summed over exactly one period (an 8×8×8 window of the result), they agree to about $`10^{-4}`$, for both particles (10 Ry; "20%": a grid point where $`\rho`$ is 20% of its largest):

| Case | Point | $`\sum\lvert\Psi\rvert^2`$ (one period) | $`\rho`$ |
|---|---|---|---|
| BiI3 Q1, electron | Bi nucleus / 20% | 0.00736 / 0.20041 | 0.00736 / 0.20039 |
| BiI3 Q5, electron | Bi nucleus / 20% | 0.00923 / 0.20005 | 0.00923 / 0.20003 |
| BiI3 Q1, hole | grid point by I / 20% | 0.57424 / 0.20166 | 0.57425 / 0.20165 |
| WSe2, hole | W nucleus / 20% | 0.01164 / 0.20577 | 0.01165 / 0.20577 |
| WSe2, electron | W nucleus / 20% | 0.10072 / 0.16236 | 0.10072 / 0.16236 |

(ratios to the value at the maximum). Positions taken from the density's grid were used by `ex_wf2Real` unmoved.

**Orthonormality within the cutoff.** At 5 Ry the truncated conduction functions are not quite orthonormal: computing $`\rho_h`$ with their actual overlaps changes it by about 7%, but by the same factor everywhere (the ratios change by 0.03%).

**Exactness of the NTO form and of the truncation** (BiI3 Q1 hole, full cutoff, 46³ grid):

| NTOs kept | NTOs | Error (of the largest) | Density lost (predicted) |
|---|---|---|---|
| all | 2048 | $`1.5\times10^{-7}`$ (float32) | $`6\times10^{-8}`$ (0) |
| 99.9% of the weight | 1853 | $`1.1\times10^{-3}`$ | $`9.96\times10^{-4}`$ ($`9.96\times10^{-4}`$) |
| 99% | 1070 | $`8.7\times10^{-3}`$ | $`9.99\times10^{-3}`$ ($`9.99\times10^{-3}`$) |

The maximum did not move on the grid in any of them. The NTOs of a degenerate group reproduce the sum of each state's density to $`4`$–$`5\times10^{-8}`$ (BiI3 states 2–5, WSe2 states 1–2), and the average of the full-cutoff density over the cell is 1.0000 per state.

**Synthetic tests** (`tests/yambopy_ext/test_exciton_particle_density.py`): a small fake crystal with orthonormal bands, at Γ and at a finite $`\mathbf{Q}`$, for both particles: the density matches the definition of section 3 evaluated directly, its average is the number of states, a group equals the sum of its states, and a truncation loses exactly the weight dropped.

**Timings** (after the wave functions are loaded, which takes about 1 s for BiI3 and 13 s for WSe2, once per dataset):

| Case | Grid | Time |
|---|---|---|
| BiI3, per band (no NTOs), full cutoff | 46³ | 60 s |
| BiI3, NTOs (all / 99.9% / 99%), full cutoff | 46³ | 15 / 14 / 9 s |
| BiI3, NTOs 99.9%, 10 Ry | 18³ | 0.6–1.1 s |
| WSe2, NTOs 99.9%, 10 Ry | 9×9×47 | 1.6–1.7 s |
| Newton on the exact sums (section 8) | – | ≈ 50 s |

## 10. In the program

- `visual_excitons/yambopy_ext/bse/exciton_particle_density.py`: `particle_nto` (the NTOs of section 6), `wavefunction_grid` (the plane waves and grid of section 7), `exciton_particle_density` (the density on that grid), `density_maxima` (section 8). Written in YamboPy's conventions, to be contributed to it ([YamboPy issue 21](yambopy-issues.md)).
- `Calculations.computeParticleDensity` runs it in the background for the exciton, cutoff and degenerate setting of the wave function; the [Placing the fixed particle](wavefunction.md#placing-the-fixed-particle) section of the Wave function controls shows the density at the fixed position, as a share of its largest, and lists its distinct maxima to place the particle at; with `Fix the particle at its density maximum` (on by default), each new exciton is computed with the particle at its largest maximum. The maxima are grouped in `core/placement.py` (`distinctMaxima`).
- The developer's view: [Placing the fixed particle: particle densities](architecture.md#placing-the-fixed-particle-particle-densities) in the architecture guide. The checks of section 9 are in `tests/test_particle_density.py` (the identity against `ex_wf2Real` over one period, both particles) and the synthetic tests above.

## 11. Approximations and limits

- **Tamm–Dancoff only.** The anti-resonant part of non-TDA calculations is not included (YamboPy's `ex_wf2Real` includes it; the densities would need its terms too). The program says so rather than computing a partial density.
- **0.1% of the NTO weight left out**, a positive density of that total: the values are at most about 0.1% of the largest below the exact ones.
- **The cutoff** of the wave function applies to the densities too, deliberately (section 7); at low cutoffs both are smoother near the nuclei than the true ones.
- **Orthonormality** of the Bloch functions is assumed; within a cutoff it holds up to a nearly constant factor (section 9), irrelevant to the shares and maxima used.
- **Spin.** Spinor components and collinear spins are summed: the densities are those of the particle, whatever its spin.
- **A finite supercell** for the wave function: the identity of section 4 is over one period of the $`\mathbf{k}`$-grid. A wave function computed on a smaller supercell shows part of that weight; when the exciton does not fit in it (the Analysis panel warns), the share of $`\rho`$ still tells how good the position is, but not how much of the exciton the supercell holds.
