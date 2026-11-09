"""
Export of a figure as a standalone Python script, with its data.

The script is the figures module itself (self-contained: NumPy and
Matplotlib only) followed by a short main part that loads the data file and
saves the figure. Users can edit the options, or anything else, and run it
anywhere: it does not need Visual Excitons.
"""

import inspect
import pprint
from pathlib import Path

from . import figures


def writeFigureScript(scriptPath, data, styles, options, figureFormat='pdf', programVersion=''):
    """
    Write `scriptPath` (.py) and its data file next to it (same name, .npz).
    Running the script saves the figure next to it (same name, `figureFormat`).
    """
    scriptPath = Path(scriptPath)
    dataPath = scriptPath.with_suffix('.npz')
    options = {**figures.DEFAULT_OPTIONS, **options}
    figures.saveData(dataPath, data, styles, options)

    module = inspect.getsource(figures)
    header = f'''#!/usr/bin/env python3
"""
Figure exported by Visual Excitons{f" {programVersion}" if programVersion else ""}.

Run it to save the figure as {scriptPath.stem}.{figureFormat}, next to this script:

    python {scriptPath.name}

It needs NumPy and Matplotlib, and its data file, {dataPath.name}. Edit the
options at the end (size in cm, fonts, panels...) or anything else; the code
below is the module Visual Excitons draws its figures with.
"""
'''
    main = f'''

if __name__ == '__main__':
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    data, styles, savedOptions = loadData(os.path.join(here, {dataPath.name!r}))

    # Options as exported; change them here
    options = {pprint.pformat(options, indent=4, sort_dicts=False)}

    figure = buildFigure(data, styles, options)
    output = os.path.join(here, {f"{scriptPath.stem}.{figureFormat}"!r})
    saveFigure(figure, output, options)
    print('Saved', output)
'''
    # The module whole, docstring included: it documents the data and the options
    scriptPath.write_text(header + '\n' + module + main)
    return scriptPath, dataPath
