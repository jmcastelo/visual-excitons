"""
The hole and electron densities of the excitons of the claims (A at Γ, the
lowest at q in the Q valley and at q = M) on the WSe2 72x72x1 dataset, with
Visual Excitons' own calculation (core.calculations.computeParticleDensity),
and what they say about the states shared: see docs/validation-dogadov-2026.md.

    python validation/dogadov-2026/densities.py [dataset folder] [cutoff (Ry)]

Loads the wave functions (about 1.5 GB, 3.6 GB at the peak): run it alone, under
a memory cap (e.g. ulimit -v 10000000). Writes densities.json next to it.
"""

import contextlib
import io
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from yambopy import YamboLatticeDB                                                    # noqa: E402
from visual_excitons.core.calculations import computeParticleDensity                  # noqa: E402
from visual_excitons.core.atomic_data import BOHR_TO_ANGSTROM, chemical_symbols       # noqa: E402

DATASET = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'data' / 'WSe2_72x72x1'
CUTOFF = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
SAVE, DIAGO = DATASET / 'save', DATASET / 'diagos_sel'

# (name, Q-point file number, exciton): degenerate states summed, as the program does by default
EXCITONS = [('A (Γ)', 1, 3), ('lowest, q in the Q valley', 323, 1), ('lowest, q = M', 37, 1)]
# Around each W, the shell where its d orbitals are read (Å)
SHELL = (0.3, 1.3)


class Context:
    def stage(self, *args, **kwargs):
        pass

    def advance(self, *args, **kwargs):
        pass


def gridGeometry(shape, cell, atoms):
    """For each grid point: the nearest atom (periodic) and the Cartesian vector from it (Bohr)."""
    axes = [np.arange(n) / n for n in shape]
    red = np.stack(np.meshgrid(*axes, indexing='ij'), axis=-1).reshape(-1, 3)
    redAtoms = np.asarray(atoms, dtype=float) @ np.linalg.inv(cell)
    best, owner, vector = None, None, None
    for a, position in enumerate(redAtoms):
        d = red - position
        d -= np.rint(d)
        car = d @ cell
        length = np.linalg.norm(car, axis=1)
        if best is None:
            best, owner, vector = length, np.zeros(len(red), dtype=int), car
        else:
            closer = length < best
            best = np.where(closer, length, best)
            owner = np.where(closer, a, owner)
            vector = np.where(closer[:, None], car, vector)
    return owner, vector, best


def describe(density, geometry, numbers, layerAxis):
    owner, vector, distance = geometry
    rho = np.asarray(density, dtype=float).ravel()
    total = rho.sum()
    species = {}
    for a, z in enumerate(numbers):
        symbol = chemical_symbols[int(z)]
        species[symbol] = species.get(symbol, 0.0) + float(rho[owner == a].sum() / total)
    # Out-of-plane character around W: density-weighted <z^2/r^2> in the shell (1/3 if isotropic;
    # higher for d_z2, lower for d_xy and d_x2-y2)
    metal = [a for a, z in enumerate(numbers) if chemical_symbols[int(z)] == 'W']
    r = distance * BOHR_TO_ANGSTROM
    inShell = np.isin(owner, metal) & (r >= SHELL[0]) & (r <= SHELL[1])
    z2 = (vector[inShell] @ layerAxis) ** 2 / distance[inShell] ** 2
    return {'shares': {k: round(v, 4) for k, v in species.items()},
            'W shell <z²/r²>': round(float(np.sum(rho[inShell] * z2) / np.sum(rho[inShell])), 4)}


def overlap(a, b):
    """Normalised overlap of two densities (1: the same shape)."""
    a, b = np.asarray(a, dtype=float).ravel(), np.asarray(b, dtype=float).ravel()
    return round(float(a @ b / np.sqrt((a @ a) * (b @ b))), 4)


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        lattice = YamboLatticeDB.from_db_file(str(SAVE / 'ns.db1'))
    cell = np.asarray(lattice.lat, dtype=float)
    numbers = np.asarray(lattice.atomic_numbers, dtype=int)
    atoms = np.asarray(lattice.car_atomic_positions, dtype=float)
    layerAxis = cell[2] / np.linalg.norm(cell[2])
    cache, densities, results = {}, {}, {'cutoff (Ry)': CUTOFF, 'excitons': {}}
    geometry = None
    for name, q, exciton in EXCITONS:
        for particle in ('h', 'e'):
            start = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                d = computeParticleDensity(Context(), lattice, str(SAVE), str(DIAGO), f'ndb.BS_diago_Q{q}', q - 1,
                                           exciton, particle, CUTOFF, degenerate=True, cache=cache)
            density = d['density']
            if geometry is None:
                geometry = gridGeometry(density.shape, cell, atoms)
                results['grid'] = list(density.shape)
            densities[name, particle] = density
            entry = results['excitons'].setdefault(name, {'Q': q, 'exciton': exciton, 'states': d['states']})
            entry['hole' if particle == 'h' else 'electron'] = dict(describe(density, geometry, numbers, layerAxis),
                                                                    weightKept=round(d['weightKept'], 4),
                                                                    seconds=round(time.time() - start, 1))
            print(name, particle, entry['hole' if particle == 'h' else 'electron'], flush=True)
    names = [name for name, _, _ in EXCITONS]
    results['overlap'] = {f'{particle}: {a} / {b}': overlap(densities[a, particle], densities[b, particle])
                          for particle in ('h', 'e') for i, a in enumerate(names) for b in names[i + 1:]}
    out = Path(__file__).with_name('densities.json')
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(json.dumps(results['overlap'], indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
