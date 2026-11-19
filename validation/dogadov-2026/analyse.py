"""
The numbers behind docs/validation-dogadov-2026.md: Visual Excitons' own
calculations (core.calculations) on the WSe2 72x72x1 dataset, for the claims
of Dogadov et al., J. Phys.: Condens. Matter 38, 265701 (2026).

    python validation/dogadov-2026/analyse.py [dataset folder]

The dataset folder (data/WSe2_72x72x1 by default) holds save/, diagos_sel/
and gw/. Writes results.json next to this script and prints a summary. Reads
the BSE and QP databases only (no wave functions): a few seconds, < 2 GB.
"""

import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from yambopy import YamboLatticeDB, YamboExcitonDB, YamboElectronsDB                # noqa: E402
from visual_excitons.core.calculations import computeComposition                     # noqa: E402
from visual_excitons.yambopy_ext.dbs.qp_energies import qp_energies                  # noqa: E402
from visual_excitons.yambopy_ext.bse.exciton_bands import band_energies_ibz          # noqa: E402

DATASET = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'data' / 'WSe2_72x72x1'
SAVE, DIAGO, QP = DATASET / 'save', DATASET / 'diagos_sel', DATASET / 'gw' / 'ndb_WSe2_72x72.QP'

# The computed Q-points on the edge of the irreducible wedge (1-based file numbers), see the doc
GAMMA_M = list(range(1, 38))
GAMMA_K = [1, 38, 73, 107, 139, 170, 199, 227, 253, 278, 301, 323, 343, 362, 379, 395, 409, 422, 433, 443, 451, 458,
           463, 467, 469]
M_K = [37, 106, 169, 226, 277, 322, 361, 394, 421, 442, 457, 466, 469]


class Context:
    """The task context of core.calculations, doing nothing (no progress to show)."""
    def stage(self, *args, **kwargs):
        pass

    def advance(self, *args, **kwargs):
        pass


def quietly(call, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return call(*args, **kwargs)


def bse(q):
    return f'ndb.BS_diago_Q{q}'


# Valleys: each k-point of the full grid goes to the nearest special point of the hexagonal zone
# (with its periodic images): Γ, the corners K and K' (alternating), the midpoints Q and Q' of Γ-K
# and Γ-K', and the edge centres M

def specialPoints(rlat):
    b1, b2 = np.asarray(rlat, dtype=float)[0, :2], np.asarray(rlat, dtype=float)[1, :2]
    b = np.linalg.norm(b1)
    angle = np.arctan2(b1[1], b1[0])
    points = [('Γ', np.zeros(2))]
    for n in range(6):
        corner = b / np.sqrt(3) * np.array([np.cos(angle + np.pi / 6 + n * np.pi / 3),
                                            np.sin(angle + np.pi / 6 + n * np.pi / 3)])
        valley = 'K' if n % 2 == 0 else "K'"
        points += [(valley, corner), ('Q' if valley == 'K' else "Q'", corner / 2)]
        points.append(('M', b / 2 * np.array([np.cos(angle + n * np.pi / 3), np.sin(angle + n * np.pi / 3)])))
    return points, b1, b2


def valleyOf(lattice):
    """The valley of each k-point of lattice.red_kpoints."""
    points, b1, b2 = specialPoints(lattice.rlat)
    labels = [label for label, _ in points]
    centres = np.array([p for _, p in points])
    red = np.asarray(lattice.red_kpoints, dtype=float)[:, :2] % 1.0
    best = np.full(len(red), np.inf)
    valley = np.empty(len(red), dtype=object)
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            car = (red[:, :1] + i) * b1 + (red[:, 1:2] + j) * b2
            distance = np.linalg.norm(car[:, None, :] - centres[None, :, :], axis=2)
            nearest, d = distance.argmin(axis=1), distance.min(axis=1)
            closer = d < best
            best[closer] = d[closer]
            valley[closer] = np.array(labels, dtype=object)[nearest[closer]]
    return valley


def valleyShares(weights, valley):
    total = float(np.sum(weights))
    return {label: round(float(np.sum(weights[valley == label])) / total, 4)
            for label in ('Γ', 'K', "K'", 'Q', "Q'", 'M')}


def composition(lattice, valley, q, exciton, **stateSum):
    c = quietly(computeComposition, Context(), lattice, str(SAVE), str(DIAGO), bse(q), q - 1, exciton,
                stateSum.pop('degenerate', True), **stateSum)
    return {'Q': q, 'exciton': exciton, 'energy': round(c['energy'], 4), 'states': c['states'],
            'shares': [round(x, 4) for x in c['shares']], 'weighting': c['weightingUsed'],
            'electron': valleyShares(c['electron'], valley), 'hole': valleyShares(c['hole'], valley),
            'pairs': [[int(v), int(cb), round(float(w), 4)] for v, cb, w in c['pairs'][:4]],
            'valence': {int(b): round(float(w), 4) for b, w in c['valence'].items()},
            'conduction': {int(b): round(float(w), 4) for b, w in c['conduction'].items()}}


def main():
    lattice = quietly(YamboLatticeDB.from_db_file, str(SAVE / 'ns.db1'))
    valley = valleyOf(lattice)
    results = {'dataset': str(DATASET.relative_to(ROOT) if DATASET.is_relative_to(ROOT) else DATASET)}

    # Energies and intensities of every computed Q-point (10 states each)
    states = {}
    for q in sorted(set(GAMMA_M + GAMMA_K + M_K)):
        db = quietly(YamboExcitonDB.from_db_file, lattice, filename=bse(q), folder=str(DIAGO), Load_WF=False)
        intensity = np.abs(db.l_residual * db.r_residual)
        states[q] = (np.real(db.eigenvalues), intensity)
    gammaE, gammaI = states[1]
    results['gamma'] = [{'exciton': i + 1, 'energy': round(float(e), 4), 'intensity': round(float(x / gammaI.max()), 4)}
                        for i, (e, x) in enumerate(zip(gammaE, gammaI))]
    results['header'] = {'states per Q-point': len(gammaE), 'highest energy (eV)':
                         round(float(max(e.max() for e, _ in states.values())), 4)}
    results['dispersion'] = {name: [[q, round(float(states[q][0][0]), 4)] for q in path]
                             for name, path in (('Γ-M', GAMMA_M), ('Γ-K', GAMMA_K), ('M-K', M_K))}
    lowest = sorted((float(e[0]), q) for q, (e, _) in states.items())
    results['lowest'] = [[q, round(e, 4)] for e, q in lowest[:6]]
    gk = [(states[q][0][0], q) for q in GAMMA_K[1:-1]]
    results['minima'] = {'Γ': [1, round(float(gammaE[0]), 4)], 'M': [37, round(float(states[37][0][0]), 4)],
                         'Q valley (along Γ-K)': [min(gk)[1], round(float(min(gk)[0]), 4)],
                         'Q = K/2': [343, round(float(states[343][0][0]), 4)],
                         'K': [469, round(float(states[469][0][0]), 4)]}

    # Compositions: A at Γ (the bright doublet, 3-4), the lowest excitons at q = Q and q = M, and at K
    results['composition'] = {
        'A (Γ)': composition(lattice, valley, 1, 3),
        'lowest dark (Γ)': composition(lattice, valley, 1, 1),
        'lowest, q in the Q valley': composition(lattice, valley, min(gk)[1], 1),
        'lowest, q = Q = K/2': composition(lattice, valley, 343, 1),
        'lowest, q = M': composition(lattice, valley, 37, 1),
        'lowest, near M on M-K': composition(lattice, valley, 106, 1),
        'lowest, q = K': composition(lattice, valley, 469, 1),
        # The energy window: around A, ±25 meV by oscillator strength (the paper's window for C)
        'A (Γ), ±25 meV window': composition(lattice, valley, 1, 3, window=0.025, weighting='oscillator'),
    }

    # Band edges: valence top (band 62) and conduction bottom (band 63), DFT and QP, by valley
    electrons = quietly(YamboElectronsDB.from_db_file, folder=str(SAVE))
    qp = qp_energies(str(QP))
    full = np.asarray(lattice.kpoints_indexes)
    edges = {}
    for name, energies in (('DFT', band_energies_ibz(electrons.eigenvalues_ibz[0], 62, 63)[0]),
                           ('QP', band_energies_ibz(electrons.eigenvalues_ibz[0], 62, 63, qp)[0])):
        vb, cb = energies[full, 0], energies[full, 1]
        byValley = {label: {'VB max': round(float(vb[valley == label].max()), 4),
                            'CB min': round(float(cb[valley == label].min()), 4)}
                    for label in ('Γ', 'K', 'Q', 'M')}
        vbm, cbm = int(np.argmax(vb)), int(np.argmin(cb))
        edges[name] = {'by valley': byValley, 'VBM valley': valley[vbm], 'CBM valley': valley[cbm],
                       'gap': round(float(cb[cbm] - vb[vbm]), 4),
                       'direct gap at K': round(float(byValley['K']['CB min'] - byValley['K']['VB max']), 4),
                       'CB Q - CB K': round(float(byValley['Q']['CB min'] - byValley['K']['CB min']), 4)}
    results['band edges'] = edges

    out = Path(__file__).with_name('results.json')
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(json.dumps(results, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
