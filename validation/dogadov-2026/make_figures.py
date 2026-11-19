"""
The figures of docs/validation-dogadov-2026.md, drawn by Visual Excitons'
own figure export (core.figures) from the sessions of make_sessions.py.

    python validation/dogadov-2026/make_figures.py

Writes PNG files to docs/images/validation-dogadov-2026/. The program's
settings and kept results are those of a temporary folder.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
TEMPORARY = tempfile.mkdtemp(prefix='visual-excitons-figures-')
os.environ['VISUAL_EXCITONS_RESULTS_CACHE'] = str(Path(TEMPORARY) / 'results')

from PySide6.QtCore import QCoreApplication, QSettings, Qt                             # noqa: E402
from PySide6.QtWidgets import QApplication                                             # noqa: E402

for _format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
    QSettings.setPath(_format, QSettings.Scope.UserScope, str(Path(TEMPORARY) / 'settings'))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SESSIONS = Path(__file__).with_name('sessions')
OUT = ROOT / 'docs' / 'images' / 'validation-dogadov-2026'

# (session, figure file, panels, options). At finite Q, the k-space maps of the electron and of the hole
# alone: the electron's Q valley is a rotated copy of the path's (not equivalent by translation), so the
# band structure along the path shows only the hole
FIGURES = [
    ('1-dispersion-and-A-exciton', 'dispersion-absorption', ['dispersion', 'absorption'],
     {'width': 17.8, 'height': 7.5, 'shareEnergy': True}),
    ('1-dispersion-and-A-exciton', 'A-exciton', ['kspace', 'bands'], {'width': 17.8, 'height': 7.0}),
    ('2-q-Q-exciton', 'q-Q-exciton', ['kspace'], {'width': 8.6, 'height': 7.0}),
    ('3-q-M-exciton', 'q-M-exciton', ['kspace'], {'width': 8.6, 'height': 7.0}),
    ('4-lowest-exciton-near-M', 'lowest-exciton-near-M', ['kspace'], {'width': 8.6, 'height': 7.0}),
]


def figure(window, name, panels, options):
    from visual_excitons.core.figures import buildFigure, saveFigure
    from visual_excitons.gui.figure_export import figureData, figureStyles
    data = figureData(window.calculations, window.compositionPanel.figureData(),
                      window.wavefunction.analysis.figureData())
    styles = figureStyles(window.dispersionStyle, window.absorptionStyle, window.bandStructureStyle)
    options = dict(options, panels=panels, gamma=True, highlight=True, panelLabels=True, dpi=160)
    path = OUT / f'{name}.png'
    saveFigure(buildFigure(data, styles, options), str(path), options)
    print(path.relative_to(ROOT), flush=True)


def main():
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName('Visual Excitons')
    app.setOrganizationName('VisualExcitons')
    from visual_excitons.gui.main_window import MainWindow
    OUT.mkdir(parents=True, exist_ok=True)
    window = MainWindow()
    window.panels.show('composition')
    for session, name, panels, options in FIGURES:
        window.openSession(str(SESSIONS / f'{session}.vxsession'))
        for _ in range(50):
            app.processEvents()
        if 'kspace' in panels:
            # The electron's and the hole's maps (the same at Γ)
            combo = window.compositionPanel.particleComboBox
            particles = ['Electron', 'Hole'] if combo.isEnabled() else [None]
            for particle in particles:
                if particle is not None:
                    combo.setCurrentText(particle)
                    app.processEvents()
                suffix = '' if particle is None else '-' + particle.lower()
                figure(window, name + suffix, panels, options)
        else:
            figure(window, name, panels, options)
    window.close()


if __name__ == '__main__':
    main()
