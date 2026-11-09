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
- 'absorption': [{'q', 'energy', 'absorption', 'brightEnergy', 'brightAbsorption',
  'brightIndices', 'brightIntensities', 'darkEnergy'}, ...]
- 'bands': {'k': (n,), 'bands': (bands, n), 'weights': (bands, n), 'ticks', 'labels'}
- 'selected': {'dispersion': [(x, y), ...], 'absorption': [(energy, absorption), ...]}

Styles (`styles`, a dict per plot): {'curves': [{'color', 'width', 'dash',
'marker', 'markerSize'}, ...]}, and for 'bands' also 'fill' (color).

Options (`options`, see DEFAULT_OPTIONS): panels, arrangement, size, fonts...
"""

import matplotlib
from matplotlib.figure import Figure
import numpy as np

DEFAULT_OPTIONS = {
    'panels': ['dispersion', 'absorption'],   # in order; any of 'dispersion', 'absorption', 'bands'
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
    'gamma': True,              # write the label G of the Q-path as Γ
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
          'bands': 'Excitonic band structure'}

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


def pathLabels(labels, gamma):
    """Labels of the high-symmetry points; G as Γ if `gamma` (as math text: every font has it)."""
    return [r'$\Gamma$' if gamma and label in ('G', 'Gamma', 'GAMMA') else label for label in labels]


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
        if len(xInter) and i < len(yInter):
            ax.plot(xInter, yInter[i], color=style['color'], linewidth=style['width'], linestyle=style['dash'],
                    zorder=2)
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
        ax.plot(*xy(spectrum['energy'], spectrum['absorption']), color=style['color'], linewidth=style['width'],
                linestyle=style['dash'], label=f"Q-point {int(spectrum['q']) + 1}", zorder=2)
        if len(spectrum['brightEnergy']):
            ax.plot(*xy(spectrum['brightEnergy'], spectrum['brightAbsorption']), linestyle='none',
                    marker=style['marker'], markersize=style['markerSize'], markerfacecolor=style['color'],
                    markeredgecolor='k', markeredgewidth=0.3, zorder=3)
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
    return panels


def buildFigure(data, styles, options=None):
    """The figure: a Matplotlib Figure (not attached to any window), drawn with the rc parameters of `options`."""
    options = {**DEFAULT_OPTIONS, **(options or {})}
    panels = [panel for panel in options['panels'] if panel in availablePanels(data)]
    if not panels:
        raise ValueError('Nothing to draw: compute a dispersion, absorption spectra or a band structure first')

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
            else:
                drawBands(ax, data['bands'], styles.get('bands', {}), options)
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
        if isinstance(value, (list, tuple)) and value and not isinstance(value[0], (str, int, float)):
            return [store(item, f'{name}.{i}') for i, item in enumerate(value)]
        if isinstance(value, np.ndarray):
            arrays[name] = value
            return f'array:{name}'
        if isinstance(value, np.generic):
            return value.item()
        return list(value) if isinstance(value, tuple) else value

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
