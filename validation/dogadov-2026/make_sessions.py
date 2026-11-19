"""
The sessions of docs/validation-dogadov-2026.md: one per claim checked, with
its results, to open in Visual Excitons (File › Open session…) and look at it
directly. Made by driving the program itself.

    python validation/dogadov-2026/make_sessions.py [dataset folder]

The dataset folder (data/WSe2_72x72x1 by default) is the one the sessions
point to (elsewhere, the program asks to locate it). The program's settings and
kept results are those of a temporary folder: yours are not read nor changed.
Loads the wave functions for the densities (1.5 GB, 3.6 GB at the peak): run
it alone, under a memory cap (e.g. ulimit -v 12000000).
"""

import faulthandler
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
# Settings and kept results in a temporary folder, before anything reads them
TEMPORARY = tempfile.mkdtemp(prefix='visual-excitons-sessions-')
os.environ['VISUAL_EXCITONS_RESULTS_CACHE'] = str(Path(TEMPORARY) / 'results')

from PySide6.QtCore import QCoreApplication, QSettings, Qt, QElapsedTimer               # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidgetItem                           # noqa: E402

for _format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
    QSettings.setPath(_format, QSettings.Scope.UserScope, str(Path(TEMPORARY) / 'settings'))

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from visual_excitons.core.calculations import PointData                                 # noqa: E402
from visual_excitons.core.dataset import findDataset                                    # noqa: E402

DATASET = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'data' / 'WSe2_72x72x1'
OUT = Path(__file__).with_name('sessions')


class Clicked:
    """A clicked exciton: Q-point (0-based), index (1-based), energy (eV)."""
    def __init__(self, q, j, energy=0.0):
        self._data, self._energy = PointData(-1, j, q=q), energy

    def data(self):
        return self._data

    def pos(self):
        from pyqtgraph import Point
        return Point(self._energy, self._energy)


def waitIdle(window, timeout=600):
    """Process events until no calculation is running or queued."""
    app, timer = QApplication.instance(), QElapsedTimer()
    timer.start()
    while True:
        for _ in range(20):
            app.processEvents()
        if not window.calculations.isBusy():
            app.processEvents()
            if not window.calculations.isBusy():
                return
        if timer.elapsed() > timeout * 1000:
            raise TimeoutError('the calculation did not end')
        QApplication.instance().thread().msleep(50)


def energyOf(window, q, j):
    from yambopy import YamboExcitonDB
    import numpy as np
    from visual_excitons.core.tasks import databaseAccess
    with databaseAccess():                # not while a calculation reads the databases (HDF5 is not thread-safe)
        db = YamboExcitonDB.from_db_file(window.calculations.lattice, filename=window.dataset.bseFile(q),
                                         folder=window.dataset.diagoDir, Load_WF=False, neigs=j)
    return float(np.real(db.eigenvalues[j - 1]))


def select(window, q, j):
    """Select exciton j of Q-point q (0-based) and show its band structure and composition."""
    point = Clicked(q, j, energyOf(window, q, j))
    window.calculations.selectExciton([point], True)
    window.calculations.getExcitonBandStructure([point], None)
    window.panels.show('composition')
    window.updateComposition()
    waitIdle(window)


def save(window, name):
    OUT.mkdir(exist_ok=True)
    path = OUT / f'{name}.vxsession'
    window.writeSessionFile(str(path))
    print(f'{path.relative_to(ROOT)}: {path.stat().st_size / 2 ** 20:.1f} MB', flush=True)


def main():
    faulthandler.enable()
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName('Visual Excitons')
    app.setOrganizationName('VisualExcitons')
    from visual_excitons.gui.main_window import MainWindow
    window = MainWindow()
    window.settings.setValue('sessionResults', True)
    window.openDataset(findDataset(DATASET))
    waitIdle(window)

    # The paper's path, M-Γ-Q-K-M, with Q = K/2 (the midpoint of Γ-K, its label in Fig. 4a)
    system = window.system
    k = window.dataset.highSymmetryPoints['K']
    row = system.hspTable.rowCount()
    system.hspTable.insertRow(row)
    for column, text in enumerate(['Q'] + [f'{x / 2:.10g}' for x in k]):
        system.hspTable.setItem(row, column, QTableWidgetItem(text))
    system.qPathLineEdit.setText('MGQKM')
    assert system.setBrillouinZone(), 'the Q-path could not be set'

    # Fig. 4a: the dispersion of the 10 excitons of each Q-point, and the absorption at Γ (Fig. 3a, A only)
    window.spectra.controls.nExcitonsSpinBox.setValue(10)
    window.calculations.getExcitonDispersion()
    waitIdle(window)
    window.calculations.showQPointAbsorption(0)
    waitIdle(window)

    # Each claim: the exciton selected, with its composition (k-space map) and band structure
    select(window, 0, 3)                 # A at Γ, the bright doublet 3-4 (Fig. 3b, 4b)
    save(window, '1-dispersion-and-A-exciton')
    select(window, 322, 1)               # lowest exciton with q in the Q valley, Q323 (Fig. 4d)
    save(window, '2-q-Q-exciton')
    select(window, 36, 1)                # lowest exciton at q = M, Q37 (Fig. 4e)
    save(window, '3-q-M-exciton')
    select(window, 105, 1)               # the lowest of all, next to M on M-K, Q106
    save(window, '4-lowest-exciton-near-M')

    # The energy window: A with ±25 meV by oscillator strength, shaded on the spectrum
    spectra = window.spectra.controls
    spectra.windowSpinBox.setValue(25)
    spectra.weightingComboBox.setCurrentIndex(0)
    spectra.windowCheckBox.setChecked(True)
    select(window, 0, 3)
    save(window, '5-energy-window-around-A')
    spectra.windowCheckBox.setChecked(False)

    # Real space: the hole and the electron of A and of the q = Q exciton (the same hole, other electrons)
    controls = window.wavefunction.controls
    controls.fullCutoffCheckBox.setChecked(False)
    controls.wfCutoffSpinBox.setValue(40.0)
    for name, q, j, particle in (('6-A-hole-density', 0, 3, 0), ('7-A-electron-density', 0, 3, 1),
                                 ('8-q-Q-hole-density', 322, 1, 0), ('9-q-Q-electron-density', 322, 1, 1)):
        select(window, q, j)
        controls.particleTypeComboBox.setCurrentIndex(particle)
        controls.computeDensityButton.click()
        waitIdle(window)
        assert controls.currentDensity() is not None, name
        save(window, name)

    window.close()


if __name__ == '__main__':
    main()
