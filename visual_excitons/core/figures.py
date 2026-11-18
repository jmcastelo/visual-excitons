"""
Publication figures of the excitonic dispersion, absorption spectra and band
structure, with Matplotlib.

This module is self-contained on purpose: it only needs NumPy and Matplotlib.
Visual Excitons uses it to draw and save figures, and copies it whole into the
Python scripts it exports, which recreate a figure from a data file (.npz):
edit those scripts freely to adapt the figure.

Data (`data`, a dict; lengths of the Q-path in its own units, energies in eV):

- 'dispersion': {'points': (curves, path points, 2), 'xInter': (n,),
  'yInter': (curves, n), 'ticks': [...], 'labels': [...]}
  (styles[panel]['lines'], default True: the lines of the curves; without
  interpolated curves, the dispersion's points joined)
- 'absorption': [{'q', 'energy', 'absorption', 'brightEnergy', 'brightAbsorption',
  'brightIndices', 'brightIntensities', 'darkEnergy'}, ...]
- 'bands': {'k': (n,), 'bands': (bands, n), 'weights': (bands, n), 'ticks', 'labels'}
- 'selected': {'dispersion': [(x, y), ...], 'absorption': [(energy, absorption), ...]}
- 'kspace': the weights of an exciton's k-points on a plane of the Brillouin
  zone (lengths in 1/Å): {'zones': [{'points': (m, 2), 'values': (m,) relative
  to the largest, 'outline': (o, 2)}, ...] (the zone first, then its
  replicas), 'tile': (t, 2) (the shape of a k-point's tile), 'labels':
  [(x, y, text)], 'path': (n, 2) with NaN gaps or None, 'scale': 'linear' or
  'log', 'colormap': (256, 3) RGB (0-255), 'title'}
- 'kspace3d': the same in the zone in 3D: {'edges': (n, 2, 3), 'points': (m, 3),
  'values': (m,), 'sizes': (m,) 0-1, 'labels': [(x, y, z, text)], 'path':
  (n, 3) or None, 'scale', 'colormap', 'opacity', 'view': (elevation, azimuth)}
- 'planeCut': a plane cut of the wave function's density: {'values': (t, s),
  'extent': [s0, s1, t0, t1] (Å), 'levels': [low, high], 'atoms': [{'x', 'y',
  'radius', 'color', 'alpha', 'symbol'}], 'particle' (the fixed particle at the
  origin), 'particleLabel', 'colormap'}
- 'distance': the distance of the other particle from the fixed one: {'r' (Å),
  'probability' (1/Å), 'cumulative', 'mean', 'r90', 'particle', 'other'}

Styles (`styles`, a dict per plot): {'curves': [{'color', 'width', 'dash',
'marker', 'markerSize'}, ...]}, and for 'bands' also 'fill' (color).

Options (`options`, see DEFAULT_OPTIONS): panels, arrangement, size, fonts...
"""

import re

import matplotlib
from matplotlib.figure import Figure

import numpy as np

DEFAULT_OPTIONS = {
    'panels': ['dispersion', 'absorption'],   # in order; any of PANELS
    'arrangement': 'row',                     # 'row' or 'column'
    'shareEnergy': False,       # dispersion and absorption on one energy axis (absorption rotated)
    'width': 8.6,               # cm (8.6: one column of a two-column journal; 17.8: two columns)
    'height': 6.0,              # cm
    'font': 'DejaVu Sans',      # see FONTS
    'fontSize': 8.0,            # points
    'dpi': 300,                 # for raster formats
    'panelLabels': True,        # (a), (b)...
    'legend': True,
    'excitonBars': True,        # bright and dark excitons below the absorption
    'labelExcitons': False,     # index of the bright excitons
    'highlight': True,          # the selected exciton
    'gamma': True,              # Q-path labels typeset: Γ for G, Greek letters, subscripts, primes
    'titles': False,
}

# Font choices: rc parameters of each
FONTS = {
    'DejaVu Sans': {'font.family': 'sans-serif', 'font.sans-serif': ['DejaVu Sans'], 'mathtext.fontset': 'dejavusans'},
    'DejaVu Serif': {'font.family': 'serif', 'font.serif': ['DejaVu Serif'], 'mathtext.fontset': 'dejavuserif'},
    'STIX (Times-like)': {'font.family': 'serif', 'font.serif': ['STIXGeneral'], 'mathtext.fontset': 'stix'},
    'Computer Modern (LaTeX-like)': {'font.family': 'serif', 'font.serif': ['cmr10'], 'mathtext.fontset': 'cm',
                                     'axes.formatter.use_mathtext': True},
}

TITLES = {'dispersion': 'Excitonic dispersion', 'absorption': 'Excitonic absorption',
          'bands': 'Excitonic band structure', 'kspace': 'Exciton in k-space',
          'kspace3d': 'Exciton in the Brillouin zone', 'planeCut': 'Plane cut of the wave function',
          'distance': 'Electron-hole distance'}
PANELS = list(TITLES)

# Smallest weight shown on a logarithmic scale (relative to the largest)
LOG_FLOOR = 1e-3

ENERGY_LABEL = 'Energy (eV)'
ABSORPTION_LABEL = 'Absorption (arb. units)'

# The ring around the selected exciton
HIGHLIGHT_COLOR = '#ff8c00'


def rcParameters(options):
    """Matplotlib rc parameters for the options (fonts, sizes)."""
    size = float(options['fontSize'])
    parameters = {
        'font.size': size, 'axes.labelsize': size, 'axes.titlesize': size, 'legend.fontsize': 0.85 * size,
        'xtick.labelsize': 0.9 * size, 'ytick.labelsize': 0.9 * size,
        'axes.linewidth': 0.6, 'xtick.major.width': 0.6, 'ytick.major.width': 0.6,
        'xtick.direction': 'in', 'ytick.direction': 'in', 'xtick.top': True, 'ytick.right': True,
        'savefig.bbox': 'standard', 'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
        # A true minus sign (−), as typeset; Computer Modern draws it as math text
        'axes.unicode_minus': True,
    }
    parameters.update(FONTS.get(options['font'], FONTS['DejaVu Sans']))
    return parameters


# Labels of special points, as yambopy writes them (yambopy.bz.labels): a capital
# letter or a capitalised Greek name, then a subscript and primes, e.g. G (Γ),
# Sigma1 (Σ₁), K' (K′); a jump between path sections joins two of them with
# ' — ' (or '|'). Parsed here too: exported scripts do not need yambopy.
GREEK_LABELS = ('Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon', 'Phi', 'Psi', 'Omega')
LABEL_PATTERN = re.compile(r"(%s|[A-Z])([0-9]*)('*)" % '|'.join(sorted(GREEK_LABELS, key=len, reverse=True)))
MERGED_LABEL = re.compile(r'\s*(?:—|\|)\s*')


def mathLabel(label):
    """A special-point label as math text (upright, e.g. $\\Sigma_{1}$), or None if it is not one."""
    match = LABEL_PATTERN.fullmatch(label.strip())
    if match is None:
        return None
    base, subscript, primes = match.groups()
    base = '\\Gamma' if base in ('G', 'Gamma') else '\\' + base if base in GREEK_LABELS else '\\mathrm{%s}' % base
    return base + ('_{%s}' % subscript if subscript else '') + ('^{%s}' % ('\\prime' * len(primes)) if primes else '')


def pathLabels(labels, typeset):
    """
    Labels of the high-symmetry points: typeset if `typeset` (Γ for G, Greek
    letters, subscripts, primes; as math text, which every font has), merged
    ones as A|B. Labels that are plain letters stay plain text, in the font of
    the figure.
    """
    shown = []
    for label in labels:
        parts = MERGED_LABEL.split(str(label))
        if not typeset:
            shown.append('|'.join(parts))
            continue
        maths = [mathLabel(part) for part in parts]
        if any(math is None for math in maths):
            shown.append(str(label))            # not a special-point label: as it is
        elif all(math.startswith('\\mathrm') and '_' not in math and '^' not in math for math in maths):
            shown.append('|'.join(parts))       # plain letters
        else:
            shown.append('$' + '|'.join(maths) + '$')
    return shown


def curveStyle(styles, i):
    curves = styles.get('curves') or [{}]
    style = dict(curves[i % len(curves)])
    style.setdefault('color', f'C{i}')
    style.setdefault('width', 1.0)
    style.setdefault('dash', '-')
    style.setdefault('marker', 'o')
    style.setdefault('markerSize', 3.0)
    # Dash patterns (offset, [on, off...]) come back from JSON as lists
    if isinstance(style['dash'], list):
        style['dash'] = (style['dash'][0], tuple(style['dash'][1]))
    return style


def pathAxis(ax, ticks, labels, options):
    """Q-path (or k-path) axis: the high-symmetry points as ticks, with vertical lines."""
    if len(ticks):
        ax.set_xticks(list(ticks))
        ax.set_xticklabels(pathLabels(labels, options['gamma']))
        ax.set_xlim(min(ticks), max(ticks))
        for tick in ticks[1:-1]:
            ax.axvline(tick, color='0.6', linewidth=0.5, zorder=0)
    ax.tick_params(axis='x', which='both', top=False, length=0)


def drawDispersion(ax, dispersion, styles, selected, options):
    points = np.asarray(dispersion['points'], dtype=float)
    xInter = np.asarray(dispersion.get('xInter', []), dtype=float)
    yInter = np.asarray(dispersion.get('yInter', []), dtype=float)
    for i in range(len(points)):
        style = curveStyle(styles, i)
        lines = styles.get('lines', True)
        if lines and len(xInter) and i < len(yInter):
            ax.plot(xInter, yInter[i], color=style['color'], linewidth=style['width'], linestyle=style['dash'],
                    zorder=2)
        elif lines and not len(xInter) and points.shape[1] > 1:
            # Not interpolated (only some Q-points computed): the points joined in path order
            order = np.argsort(points[i, :, 0], kind='stable')
            ax.plot(points[i, order, 0], points[i, order, 1], color=style['color'], linewidth=style['width'],
                    linestyle=style['dash'], zorder=2)
        ax.plot(points[i, :, 0], points[i, :, 1], linestyle='none', marker=style['marker'],
                markersize=style['markerSize'], markerfacecolor=style['color'], markeredgecolor='none', zorder=3)
    if options['highlight'] and selected:
        x, y = np.asarray(selected, dtype=float).T
        ax.plot(x, y, linestyle='none', marker='o', markersize=9, markerfacecolor='none',
                markeredgecolor=HIGHLIGHT_COLOR, markeredgewidth=1.2, zorder=4)
    pathAxis(ax, dispersion.get('ticks', []), dispersion.get('labels', []), options)
    ax.set_ylabel(ENERGY_LABEL)


def drawAbsorption(ax, spectra, styles, selected, options, rotated=False, barsAx=None):
    """Spectra; `rotated`: energy along y (to share it with the dispersion)."""
    def xy(energy, value):
        return (value, energy) if rotated else (energy, value)

    for i, spectrum in enumerate(spectra):
        style = curveStyle(styles, i)
        label = f"Q-point {int(spectrum['q']) + 1}"
        lines = styles.get('lines', True)
        if lines:
            ax.plot(*xy(spectrum['energy'], spectrum['absorption']), color=style['color'], linewidth=style['width'],
                    linestyle=style['dash'], label=label, zorder=2)
        if len(spectrum['brightEnergy']):
            # Without lines, the points carry the label of the spectrum in the legend
            ax.plot(*xy(spectrum['brightEnergy'], spectrum['brightAbsorption']), linestyle='none',
                    marker=style['marker'], markersize=style['markerSize'], markerfacecolor=style['color'],
                    markeredgecolor='k', markeredgewidth=0.3, zorder=3, label=None if lines else label)
        if options['labelExcitons']:
            for energy, value, index in zip(spectrum['brightEnergy'], spectrum['brightAbsorption'],
                                            spectrum['brightIndices']):
                ax.annotate(str(int(index)), xy(energy, value), textcoords='offset points',
                            xytext=(3, 0) if rotated else (0, 3), ha='left' if rotated else 'center',
                            va='center' if rotated else 'bottom', fontsize='x-small')

        if barsAx is not None:
            # Dark excitons thin and grey (there can be many), bright ones bold and on top
            for energies, color, width, order in ((spectrum['darkEnergy'], '0.6', 0.35, 1),
                                                  (spectrum['brightEnergy'], style['color'], 1.0, 2)):
                for energy in energies:
                    barsAx.axvline(energy, ymin=1 - (i + 1) / len(spectra), ymax=1 - i / len(spectra),
                                   color=color, linewidth=width, zorder=order)

    if options['highlight'] and selected:
        energy, value = np.asarray(selected, dtype=float).T
        ax.plot(*xy(energy, value), linestyle='none', marker='o', markersize=9, markerfacecolor='none',
                markeredgecolor=HIGHLIGHT_COLOR, markeredgewidth=1.2, zorder=4)

    if rotated:
        ax.set_xlabel(ABSORPTION_LABEL)
        ax.set_xlim(left=0)
        ax.set_xticks([])
    else:
        ax.set_ylabel(ABSORPTION_LABEL)
        ax.set_ylim(bottom=0)
        ax.set_yticks([])
        energies = np.concatenate([s['energy'] for s in spectra]) if spectra else np.array([0.0, 1.0])
        ax.set_xlim(energies.min(), energies.max())
        if barsAx is not None:
            barsAx.set_xlim(ax.get_xlim())
            barsAx.set_yticks([])
            barsAx.tick_params(axis='x', labelbottom=True)
            barsAx.set_xlabel(ENERGY_LABEL)
            ax.tick_params(axis='x', labelbottom=False)
        else:
            ax.set_xlabel(ENERGY_LABEL)
    if options['legend'] and len(spectra) > 0:
        ax.legend(frameon=False, loc='upper right', handlelength=1.5)


def sharedEnergyRange(dispersion, spectra, margin=0.15):
    """
    Energy range of a shared axis: the dispersion and the bright excitons,
    plus `margin` of their span on both sides (not the whole computed range
    of the spectra, mostly tails, which would squash the dispersion).
    """
    energies = [np.asarray(dispersion['points'], dtype=float)[..., 1].ravel()]
    energies += [np.asarray(s['brightEnergy'], dtype=float) for s in spectra if len(s['brightEnergy'])]
    energies = np.concatenate(energies)
    low, high = energies.min(), energies.max()
    pad = max(margin * (high - low), 0.02)
    return low - pad, high + pad


def drawBands(ax, bands, styles, options):
    k = np.asarray(bands['k'], dtype=float)
    fill = styles.get('fill', '#ffa500')
    for i, (band, weight) in enumerate(zip(np.asarray(bands['bands'], dtype=float),
                                           np.asarray(bands['weights'], dtype=float))):
        style = curveStyle(styles, i)
        ax.fill_between(k, band - weight, band + weight, color=fill, alpha=0.6, linewidth=0, zorder=1)
        if styles.get('lines', True):
            ax.plot(k, band, color=style['color'], linewidth=0.6 * style['width'], linestyle=style['dash'], zorder=2)
    pathAxis(ax, bands.get('ticks', []), bands.get('labels', []), options)
    ax.set_ylabel(ENERGY_LABEL)


def availablePanels(data):
    """The panels with data."""
    panels = []
    if data.get('dispersion') and len(data['dispersion'].get('points', [])):
        panels.append('dispersion')
    if data.get('absorption'):
        panels.append('absorption')
    if data.get('bands') and len(data['bands'].get('k', [])):
        panels.append('bands')
    for panel in ('kspace', 'kspace3d', 'planeCut', 'distance'):
        if data.get(panel):
            panels.append(panel)
    return panels


def colormapOf(lookup):
    """A Matplotlib colormap from a table of RGB colors (0-255)."""
    from matplotlib.colors import ListedColormap
    if lookup is None or not len(lookup):
        return matplotlib.colormaps['viridis']
    return ListedColormap(np.asarray(lookup, dtype=float) / 255.0)


def scaledWeights(values, scale):
    """Weights relative to the largest, as colors take them: linear, or logarithmic down to LOG_FLOOR."""
    values = np.asarray(values, dtype=float)
    if scale == 'log':
        return (np.log10(np.clip(values, LOG_FLOOR, 1.0)) - np.log10(LOG_FLOOR)) / -np.log10(LOG_FLOOR)
    return np.clip(values, 0.0, 1.0)


def colorbar(figure, ax, mappable, label, shrink=1.0):
    """
    A colorbar beside `ax`, as a child of it (it follows the axes, so that a
    panel of fixed aspect stays centred in its place; a colorbar of the
    figure's own would pull it to the side of the colorbar).
    """
    cax = ax.inset_axes([1.04, (1 - shrink) / 2, 0.045, shrink])
    return figure.colorbar(mappable, cax=cax, label=label)


def weightColorbar(figure, ax, cmap, scale, shrink=1.0):
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    if scale == 'log':
        norm, label = Normalize(np.log10(LOG_FLOOR), 0.0), r'$\log_{10}$ weight (relative)'
    else:
        norm, label = Normalize(0.0, 1.0), 'Weight (relative)'
    return colorbar(figure, ax, ScalarMappable(norm=norm, cmap=cmap), label, shrink)


def drawKSpace(ax, kspace, options, figure):
    """The weights of an exciton's k-points on a plane: a tile per k-point, clipped to its zone."""
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Polygon
    cmap = colormapOf(kspace.get('colormap'))
    tile = np.asarray(kspace['tile'], dtype=float)
    corners = []
    for i, zone in enumerate(kspace['zones']):
        points = np.asarray(zone['points'], dtype=float).reshape(-1, 2)
        outline = np.asarray(zone['outline'], dtype=float).reshape(-1, 2)
        if len(points):
            tiles = PolyCollection(points[:, None, :] + tile[None, :, :], cmap=cmap, edgecolors='face',
                                   linewidths=0.15, zorder=1)
            tiles.set_array(scaledWeights(zone['values'], kspace.get('scale', 'linear')))
            tiles.set_clim(0.0, 1.0)
            if len(outline) >= 3:
                tiles.set_clip_path(Polygon(outline, closed=True, transform=ax.transData))
            ax.add_collection(tiles)
        if len(outline) >= 3:
            corners.append(outline)
            closed = np.vstack([outline, outline[:1]])
            ax.plot(closed[:, 0], closed[:, 1], color='black' if i == 0 else '0.55',
                    linewidth=0.8 if i == 0 else 0.5, zorder=3)
    path = kspace.get('path')
    if path is not None and len(path):
        path = np.asarray(path, dtype=float)
        ax.plot(path[:, 0], path[:, 1], color='black', linewidth=0.8, linestyle='--', zorder=4)
    for x, y, text in kspace.get('labels', []):
        ax.plot([x], [y], 'o', color='black', markersize=2, zorder=5)
        ax.annotate(text, (x, y), xytext=(2, 2), textcoords='offset points', zorder=5)
    if corners:
        every = np.vstack(corners)
        low, high = every.min(axis=0), every.max(axis=0)
        margin = 0.04 * (high - low).max()
        ax.set_xlim(low[0] - margin, high[0] + margin)
        ax.set_ylim(low[1] - margin, high[1] + margin)
    ax.set_aspect('equal')
    ax.set_xlabel(r'$k_1$ (Å$^{-1}$)')
    ax.set_ylabel(r'$k_2$ (Å$^{-1}$)')
    weightColorbar(figure, ax, cmap, kspace.get('scale', 'linear'))


def drawKSpace3D(ax, zone, options, figure):
    """An exciton's k-points in the Brillouin zone in 3D: sized and colored by their weight."""
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    cmap = colormapOf(zone.get('colormap'))
    edges = np.asarray(zone['edges'], dtype=float)
    ax.add_collection3d(Line3DCollection(edges, colors='black', linewidths=0.6))
    points = np.asarray(zone['points'], dtype=float).reshape(-1, 3)
    if len(points):
        sizes = np.asarray(zone['sizes'], dtype=float)
        ax.scatter(points[:, 0], points[:, 1], points[:, 2], s=6 + 90 * sizes,
                   c=scaledWeights(zone['values'], zone.get('scale', 'linear')), cmap=cmap, vmin=0.0, vmax=1.0,
                   alpha=zone.get('opacity', 0.8), edgecolors='none', depthshade=True)
    path = zone.get('path')
    if path is not None and len(path):
        path = np.asarray(path, dtype=float)
        ax.plot(path[:, 0], path[:, 1], path[:, 2], color='black', linewidth=0.8, linestyle='--')
    for x, y, z, text in zone.get('labels', []):
        ax.text(x, y, z, text)
    every = edges.reshape(-1, 3)
    centre, half = every.mean(axis=0), (every.max(axis=0) - every.min(axis=0)).max() / 2
    for setter, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), centre):
        setter(c - half, c + half)
    ax.set_box_aspect((1, 1, 1))
    ax.set_axis_off()
    elevation, azimuth = zone.get('view', (20.0, -60.0))
    ax.view_init(elev=elevation, azim=azimuth)
    weightColorbar(figure, ax, cmap, zone.get('scale', 'linear'), shrink=0.7)


def drawPlaneCut(ax, cut, options, figure):
    """The density of the wave function on a plane, with the atoms near it and the fixed particle."""
    from matplotlib.patches import Circle
    cmap = colormapOf(cut.get('colormap'))
    low, high = cut.get('levels', (0.0, 1.0))
    image = ax.imshow(np.asarray(cut['values'], dtype=float), extent=cut['extent'], origin='lower', cmap=cmap,
                      vmin=low, vmax=high, interpolation='nearest', zorder=1)
    for atom in cut.get('atoms', []):
        color = list(atom['color'])
        ax.add_patch(Circle((atom['x'], atom['y']), atom['radius'], facecolor=color, edgecolor='black',
                            linewidth=0.4, alpha=atom.get('alpha', 1.0), zorder=3))
        ax.annotate(atom['symbol'], (atom['x'], atom['y']), ha='center', va='center', color='white',
                    fontsize=0.75 * options['fontSize'], alpha=atom.get('alpha', 1.0), zorder=4)
    if cut.get('particle'):
        ax.plot([0.0], [0.0], marker='*', color='white', markeredgecolor='black', markeredgewidth=0.5,
                markersize=8, zorder=5)
    ax.set_xlim(cut['extent'][0], cut['extent'][1])
    ax.set_ylim(cut['extent'][2], cut['extent'][3])
    ax.set_aspect('equal')
    ax.set_xlabel('along u (Å)')
    ax.set_ylabel('along v (Å)')
    colorbar(figure, ax, image, 'Density (relative)')


def drawDistance(ax, distance, options):
    """The probability of the distance between the particles, and its cumulative on a second axis."""
    r = np.asarray(distance['r'], dtype=float)
    ax.plot(r, np.asarray(distance['probability'], dtype=float), color='#4682e6', linewidth=1.2)
    for value, label, color in ((distance['mean'], 'mean', '#e6781e'), (distance['r90'], '90%', '0.5')):
        ax.axvline(value, color=color, linewidth=0.8, linestyle=':')
        ax.annotate(label, (value, 1.0), xycoords=('data', 'axes fraction'), xytext=(2, -8),
                    textcoords='offset points', color=color, fontsize=0.85 * options['fontSize'])
    ax.set_xlim(0.0, r.max() if len(r) else 1.0)
    ax.set_ylim(bottom=0.0)
    ax.set_xlabel(f'Distance from the {distance.get("particle", "fixed particle")} (Å)')
    ax.set_ylabel(r'Probability (Å$^{-1}$)')
    cumulative = ax.twinx()
    cumulative.plot(r, np.asarray(distance['cumulative'], dtype=float), color='black', linewidth=0.8, linestyle='--')
    cumulative.set_ylim(0.0, 1.02)
    cumulative.set_ylabel('Cumulative')


def buildFigure(data, styles, options=None):
    """The figure: a Matplotlib Figure (not attached to any window), drawn with the rc parameters of `options`."""
    options = {**DEFAULT_OPTIONS, **(options or {})}
    panels = [panel for panel in options['panels'] if panel in availablePanels(data)]
    if not panels:
        raise ValueError('Nothing to draw: compute a dispersion, absorption spectra, a band structure, an '
                         "exciton's composition or a wave function first")

    with matplotlib.rc_context(rcParameters(options)):
        figure = Figure(figsize=(options['width'] / 2.54, options['height'] / 2.54), dpi=100, layout='constrained')
        row = options['arrangement'] == 'row'
        share = (options['shareEnergy'] and row and 'dispersion' in panels and 'absorption' in panels)
        bars = options['excitonBars'] and 'absorption' in panels and not share

        # Absorption with its exciton bars below: one more grid row for the bars
        if row:
            grid = figure.add_gridspec(2 if bars else 1, len(panels), height_ratios=[6, 1] if bars else None,
                                       width_ratios=[0.5 if (share and p == 'absorption') else 1 for p in panels])
            # The absorption takes the first grid row, its bars the second; the
            # other panels both rows
            cells = {p: grid[0, i] for i, p in enumerate(panels)}
            barCell = grid[1, panels.index('absorption')] if bars else None
            spans = {p: grid[:, i] for i, p in enumerate(panels)}
        else:
            ratios = []
            for p in panels:
                ratios += [6, 1] if (bars and p == 'absorption') else [6]
            grid = figure.add_gridspec(len(ratios), 1, height_ratios=ratios)
            cells, index = {}, 0
            for p in panels:
                cells[p] = grid[index, 0]
                if bars and p == 'absorption':
                    barCell = grid[index + 1, 0]
                    index += 2
                else:
                    index += 1
            spans = cells

        axes = {}
        for p in panels:
            cell = cells[p] if (bars and p == 'absorption') else spans[p]
            if p == 'kspace3d':
                axes[p] = figure.add_subplot(cell, projection='3d')
                continue
            sharey = axes.get('dispersion') if (share and p == 'absorption') else None
            axes[p] = figure.add_subplot(cell, sharey=sharey)
        barsAx = figure.add_subplot(barCell, sharex=axes['absorption']) if bars else None

        selected = data.get('selected') or {}
        for p in panels:
            ax = axes[p]
            if p == 'dispersion':
                drawDispersion(ax, data['dispersion'], styles.get('dispersion', {}), selected.get('dispersion'), options)
            elif p == 'absorption':
                drawAbsorption(ax, data['absorption'], styles.get('absorption', {}), selected.get('absorption'),
                               options, rotated=share, barsAx=barsAx)
                if share:
                    ax.tick_params(axis='y', labelleft=False)
                    ax.set_ylabel('')
                    ax.set_ylim(*sharedEnergyRange(data['dispersion'], data['absorption']))
                    # The cropped spectra: scale to what is shown
                    low, high = ax.get_ylim()
                    shown = [s['absorption'][(s['energy'] >= low) & (s['energy'] <= high)] for s in data['absorption']]
                    top = max((v.max() for v in shown if len(v)), default=1.0)
                    ax.set_xlim(0, 1.08 * top)
            elif p == 'bands':
                drawBands(ax, data['bands'], styles.get('bands', {}), options)
            elif p == 'kspace':
                drawKSpace(ax, data['kspace'], options, figure)
            elif p == 'kspace3d':
                drawKSpace3D(ax, data['kspace3d'], options, figure)
            elif p == 'planeCut':
                drawPlaneCut(ax, data['planeCut'], options, figure)
            elif p == 'distance':
                drawDistance(ax, data['distance'], options)
            if options['titles'] and not (options['panelLabels'] and len(panels) > 1):
                ax.set_title(TITLES[p], loc='left', pad=3)

        if options['panelLabels'] and len(panels) > 1:
            for letter, p in zip('abcdefgh', panels):
                # Above the top-left corner, outside the axes: never over the data
                axes[p].set_title(f'({letter})' + (f' {TITLES[p]}' if options['titles'] else ''), loc='left',
                                  pad=3)
    figure.visualExcitonsOptions = options
    return figure


def saveFigure(figure, filename, options=None):
    """Save `figure` (from buildFigure), the format given by the extension of `filename`."""
    options = {**DEFAULT_OPTIONS, **(options or getattr(figure, 'visualExcitonsOptions', {}))}
    with matplotlib.rc_context(rcParameters(options)):
        figure.savefig(filename, dpi=options['dpi'])


def saveData(filename, data, styles, options):
    """Save data, styles and options for loadData: arrays as such, the rest as JSON."""
    import json
    arrays = {}

    def store(value, name):
        if isinstance(value, dict):
            return {key: store(item, f'{name}.{key}') for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [store(item, f'{name}.{i}') for i, item in enumerate(value)]
        if isinstance(value, np.ndarray):
            arrays[name] = value
            return f'array:{name}'
        if isinstance(value, np.generic):
            return value.item()
        return value

    content = {'data': store(data, 'data'), 'styles': store(styles, 'styles'), 'options': store(options, 'options')}
    np.savez_compressed(filename, content=json.dumps(content), **arrays)


def loadData(filename):
    """Data and styles saved with the figure (see the exported scripts)."""
    import json
    with np.load(filename, allow_pickle=False) as archive:
        content = json.loads(str(archive['content']))
        arrays = {name: archive[name] for name in archive.files if name != 'content'}

    def restore(value):
        if isinstance(value, dict):
            return {key: restore(item) for key, item in value.items()}
        if isinstance(value, list):
            return [restore(item) for item in value]
        if isinstance(value, str) and value.startswith('array:'):
            return arrays[value[len('array:'):]]
        return value
    return restore(content['data']), content['styles'], content['options']
