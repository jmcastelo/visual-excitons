"""
Main window: dockable panels (see docking.py) for the system, the spectra and
the wave function, arranged by preset or saved layouts (Layout menu); menus, a
status bar and persistent settings frame them.
"""

import json
import os

import numpy as np
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QSettings, QTimer, QEvent, QStandardPaths
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QLabel, QFileDialog, QMessageBox, QApplication,
                               QProgressBar, QToolButton, QInputDialog)

from visual_excitons.core.dataset import Dataset
from visual_excitons.core.parameters import SpectraParameters, WavefunctionParameters
from visual_excitons.core.calculations import Calculations, DMAT_SECONDS_PER_KPOINT
from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from visual_excitons.core.dataset import findDataset, datasetName, datasetExists
from visual_excitons.core.results_cache import (ResultsCache, CACHE_LIMIT, WAVEFUNCTION_LIMIT, folderUsage,
                                               clearFolder, moveStorage)
from .storage_dialog import StorageDialog
from .system_panel import SystemPanel
from .start_page import StartPage
from .composition_panel import CompositionPanel
from .spectra_panels import SpectraPanels
from .wavefunction_panels import WavefunctionPanels
from .docking import Panels, PRESETS, DEFAULT_PRESET, scrollable
from .theme import themeManager, THEME_MODES
from visual_excitons import __version__
from .persistence import StateRegistry, PersistentState, GLOBAL, DATASET
from .appearance import appearanceState, restoreAppearance
from .appearance_panel import AppearancePanel, appearanceIcon, GRAPHS
from .image_export import ImageExportDialog, IMAGE_FILTERS, saveImage
from .figure_export import FigureExportDialog, figureData, figureStyles
from visual_excitons.core import figures
from visual_excitons.core.session import (readSession, writeSession, datasetFingerprint, fingerprintsMatch,
                                          SessionError, SESSION_SUFFIX, SESSION_FILTER)


# Opened on the first run, when there is no recent dataset (relative to the repository)

MAX_RECENT_DATASETS = 8

# Narrowest width of the control panels
MIN_CONTROLS_WIDTH = 260


def defaultStorageFolder():
    """The cache folder of the system: where results between runs and symmetry matrices go unless set otherwise."""
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))


def resultsCacheFolder(storage):
    """
    Where the results of the datasets are kept between runs, in the storage
    folder `storage` (VISUAL_EXCITONS_RESULTS_CACHE overrides it: tests).
    """
    override = os.environ.get('VISUAL_EXCITONS_RESULTS_CACHE')
    return Path(override) if override else Path(storage) / 'results'


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings('VisualExcitons', 'VisualExcitons')
        self.theme = themeManager()

        # The dataset open and the parameters set in the controls
        self.dataset = Dataset()
        self.spectraParameters = SpectraParameters()
        self.wfParameters = WavefunctionParameters()
        self.calculations = Calculations(self.dataset, self.spectraParameters)
        # The dataset open as it is remembered (recent list, sessions): its directories, Q-path and state
        self.datasetRecord = None
        self.sessionPath = None   # session file of the current setup, if saved or opened

        self.createStyles()
        self.createPanels()
        self.createMenus()
        self.createStatusBar()

        # A new SAVE directory invalidates everything computed before; reset
        # first, then redraw the lattice
        self.dataset.databaseFound.connect(lambda found: self.calculations.resetDataset())
        self.dataset.databaseFound.connect(self.wavefunction.onDatasetChanged)
        self.dataset.databaseFound.connect(self.updateDatasetLabel)
        self.dataset.numQPointsChanged.connect(self.updateDatasetLabel)
        self.dataset.saveDirChanged.connect(self.updateDatasetLabel)

        self.calculations.busyStarted.connect(self.onTaskStarted)
        self.calculations.busyChanged.connect(self.onBusyChanged)
        self.calculations.progressChanged.connect(self.onProgress)
        self.calculations.taskCancelled.connect(self.onTaskCancelled)
        self.calculations.errorOccurred.connect(self.onError)
        self.calculations.excitonSelected.connect(self.onExcitonSelected)
        self.calculations.wfComputed.connect(lambda: self.exportDensityAction.setEnabled(True))
        self.calculations.densityExported.connect(
            lambda filename: self.statusBar().showMessage(f'Probability density saved to {filename}', 6000))
        self.dataset.databaseFound.connect(self.onDatasetForExports)
        self.dataset.qpDatabasesChanged.connect(self.onQPDatabaseChosen)
        self.dataset.gwChanged.connect(self.onGWChanged)

        self.theme.themeChanged.connect(self.spectra.setDarkTheme)
        self.theme.themeChanged.connect(self.wavefunction.setDarkTheme)
        self.theme.themeChanged.connect(self.panels.applyTheme)
        self.theme.themeChanged.connect(self.compositionPanel.setDarkTheme)
        self.setTheme(self.settings.value('theme', 'System'))

        # Parameters kept between sessions (see persistence.py): preferences now,
        # those of a dataset when it is opened
        self.state = StateRegistry()
        self.state.add('spectra', self.spectra.controls.persistence)
        self.state.add('wavefunction', self.wavefunction.controls.persistence)
        # The camera (the name dates from when it was kept with the page layout:
        # kept for the settings and sessions saved then)
        self.state.add('wavefunctionLayout', self.wavefunction.persistence)
        # The Appearance of the 2D plots (in sessions with the style of each curve)
        self.appearance = PersistentState()
        self.appearance.remember('styles', get=self.appearanceState, set=self.restoreAppearance)
        self.state.add('appearance', self.appearance)
        self.state.add('appearancePanel', self.appearancePanel.persistence)
        # The export dialogs' last choices (2D figure, 3D image): in sessions, one
        # per figure; the dialogs keep them in the settings between sessions
        self.exports = PersistentState()
        self.exports.remember('figure', get=self.figureExportState, set=self.restoreFigureExportState)
        self.exports.remember('image', get=self.imageExportState, set=self.restoreImageExportState)
        self.state.add('exports', self.exports)
        self.state.add('composition', self.compositionPanel.persistence)
        # A dataset opened for the first time starts from the defaults, not from
        # the parameters of the previous one
        self.datasetDefaults = self.state.values(DATASET)
        self.state.restore(GLOBAL, self.loadJson('state', {}))

        if not self.restoreGeometry(self.settings.value('geometry', b'')):
            self.resize(1600, 1000)
        self.restoreLayout()
        # No dataset yet: the start page, to open one or a session
        self.setStartPageShown(self.datasetRecord is None)

        # Unsaved changes of the session: what a session file would hold is
        # compared with what was saved, shortly after each input and change of
        # the results (a signature of it: cheap, and back to unmodified when a
        # change is undone)
        self.savedSignature = None
        self.modifiedTimer = QTimer(self)
        self.modifiedTimer.setSingleShot(True)
        self.modifiedTimer.setInterval(150)
        self.modifiedTimer.timeout.connect(self.updateModified)
        self.calculations.resultsChanged.connect(self.modifiedTimer.start)
        self.calculations.excitonSelected.connect(self.modifiedTimer.start)
        QApplication.instance().installEventFilter(self)

    # Construction

    def createStyles(self):
        self.dispersionStyle = DispersionStyle()
        self.absorptionStyle = AbsorptionStyle()
        self.bandStructureStyle = BandStructureStyle()

        calc = self.calculations
        self.dispersionStyle.styleChanged.connect(calc.emitExcitonDispersionReady)
        self.absorptionStyle.styleChanged.connect(calc.emitExcitonAbsorption)
        self.bandStructureStyle.styleChanged.connect(calc.emitExcitonBandStructure)

        calc.excitonDispersionNumCurvesChanged.connect(self.dispersionStyle.setNumCurves)
        calc.excitonDispersionInit.connect(self.dispersionStyle.applyDefaultStyle)
        calc.excitonAbsorptionCurveAppended.connect(self.absorptionStyle.appendCurveStyle)
        calc.excitonAbsorptionCurveRemoved.connect(self.absorptionStyle.removeCurveStyle)
        calc.excitonBandStructureNumCurvesChanged.connect(self.bandStructureStyle.setNumCurves)
        calc.excitonBandStructureInit.connect(self.bandStructureStyle.applyDefaultStyle)

    def createPanels(self):
        self.system = SystemPanel(self.dataset)
        self.spectra = SpectraPanels(self.dataset, self.spectraParameters, self.calculations, self.dispersionStyle, self.absorptionStyle,
                                     self.bandStructureStyle, parent=self)
        self.wavefunction = WavefunctionPanels(self.dataset, self.wfParameters, self.calculations, parent=self)
        self.spectra.controls.computeWavefunctionRequested.connect(self.computeSelectedWaveFunction)
        self.wavefunction.controls.selectedEstimateChanged.connect(self.spectra.controls.setWaveFunctionEstimate)
        self.system.qPathApplied.connect(self.saveQPath)
        self.system.checkAllBSERequested.connect(self.checkAllBSE)
        self.system.directoryChosen.connect(self.onDirectoryChosen)
        self.spectra.controls.exportFigureRequested.connect(self.exportFigure)
        self.wavefunction.controls.exportImageRequested.connect(self.exportImage)
        self.wavefunction.controls.exportDensityRequested.connect(self.exportDensity)

        # Where the selected exciton lives in reciprocal space, and what it is made of
        self.compositionPanel = CompositionPanel()
        self.calculations.compositionReady.connect(self.onCompositionReady)
        self.calculations.compositionFailed.connect(self.compositionPanel.showProblem)
        # Summing degenerate states or not: what depends on it and is cheap follows at once
        # (the wave function, costly, says it was computed with the other setting)
        self.calculations.sumDegenerateChanged.connect(self.updateComposition)
        self.calculations.sumDegenerateChanged.connect(lambda checked: self.calculations.computeBandStructure())
        self.calculations.excitonSelected.connect(self.updateComposition)
        self.compositionPanel.compositionNeeded.connect(self.updateComposition)
        self.compositionPanel.exportDataRequested.connect(self.exportComposition)
        self.compositionPanel.exportImageRequested.connect(self.exportCompositionImage)
        self.compositionPanel.exportFigureRequested.connect(lambda: self.exportFigure(
            ['kspace3d' if self.compositionPanel.viewComboBox.currentIndex() == 0 else 'kspace']))
        self.wavefunction.analysis.exportFigureRequested.connect(lambda: self.exportFigure(
            ['planeCut' if self.wavefunction.analysis.currentIndex() == 0 else 'distance']))
        # Symmetry and spin (on request), kept on disk between sessions: the representation matrices
        self.resultsCache = ResultsCache(resultsCacheFolder(self.storageFolder()))
        self.applyStorage()
        self.compositionPanel.characterRequested.connect(self.calculations.computeCharacter)
        self.calculations.characterReady.connect(self.compositionPanel.setCharacter)
        self.calculations.characterReady.connect(self.updateCharacterSummary)
        self.calculations.excitonSelected.connect(self.onCharacterSelection)
        self.compositionPanel.setSelectedExciton(self.calculations.selectedExciton)
        self.spectra.controls.showCompositionRequested.connect(lambda: self.showPanel('composition'))
        self.dataset.databaseFound.connect(lambda found: self.compositionPanel.clear())
        self.system.qPathApplied.connect(lambda state: self.compositionPanel.setQPath(self.qPathCartesian()))

        # The styles of the 2D plots
        self.appearancePanel = AppearancePanel({'dispersion': self.dispersionStyle, 'absorption': self.absorptionStyle,
                                                'bands': self.bandStructureStyle}, curveNames=self.curveNames)
        for signal in (self.calculations.excitonAbsorptionReady, self.calculations.excitonBandStructureReady,
                       self.calculations.excitonDispersionReady):
            signal.connect(self.appearancePanel.scheduleRefresh)   # the curves to choose from

        self.panels = Panels(self)
        for inspector in (self.spectra.controls, self.wavefunction.controls, self.appearancePanel):
            inspector.setMinimumWidth(max(MIN_CONTROLS_WIDTH, inspector.minimumWidth()))
        for key, widget in (('system', scrollable(self.system)),
                            ('dispersion', self.spectra.dispersionPlot),
                            ('absorption', self.spectra.absorptionPlot),
                            ('bands', self.spectra.bandStructurePanel),
                            ('wavefunction', self.wavefunction.view),
                            ('analysis', self.wavefunction.analysis),
                            ('composition', self.compositionPanel),
                            ('spectraControls', self.spectra.controls),
                            ('appearance', self.appearancePanel),
                            ('wavefunctionControls', self.wavefunction.controls)):
            self.panels.add(key, widget)

        # Each plot's style, from its panel's title bar and its right-click menu
        views = {'dispersion': self.spectra.dispersionPlot.getPlotItem().vb,
                 'absorption': self.spectra.absorptionPlot.absorption.vb,
                 'bands': self.spectra.bandStructurePlot.getPlotItem().vb}
        self.appearanceActions = {}
        for key, view in views.items():
            action = QAction(appearanceIcon(), 'Appearance…', self)
            action.setToolTip(f'The style of the {GRAPHS[key].lower()} plot')
            action.triggered.connect(lambda checked=False, key=key: self.showAppearance(key))
            self.panels.setTitleBarActions(key, [action])
            view.menu.addSeparator()
            view.menu.addAction(action)
            self.appearanceActions[key] = action

        # The analysis checkbox shows and hides its panel, and follows it
        self.analysisCheckBox = self.wavefunction.controls.showAnalysisCheckBox
        self.analysisCheckBox.toggled.connect(lambda shown: self.panels.setShown('analysis', shown))
        self.panels.panelToggled.connect(self.onPanelToggled)

        # Over the panels while no dataset is open
        self.startPage = StartPage(self)
        self.startPage.openDatasetRequested.connect(self.chooseDataset)
        self.startPage.openSessionRequested.connect(self.chooseSession)
        self.startPage.datasetChosen.connect(self.openDataset)
        self.startPage.sessionChosen.connect(self.openSession)

    def createMenus(self):
        # File
        fileMenu = self.menuBar().addMenu('&File')

        newSessionAction = QAction('&New session', self)
        newSessionAction.setShortcut(QKeySequence.StandardKey.New)
        newSessionAction.setStatusTip('Close the dataset and its results, and start again from the start page')
        newSessionAction.triggered.connect(self.newSession)
        fileMenu.addAction(newSessionAction)
        fileMenu.addSeparator()

        openAction = QAction('&Open dataset…', self)
        openAction.setShortcut(QKeySequence.StandardKey.Open)
        openAction.setStatusTip('Open the folder of a calculation; its SAVE, BSE and GW directories are found automatically')
        openAction.triggered.connect(self.chooseDataset)
        fileMenu.addAction(openAction)

        self.recentMenu = fileMenu.addMenu('Open &recent')
        self.updateRecentMenu()

        # Sessions: a whole setup in a file (see core/session.py)
        fileMenu.addSeparator()
        openSessionAction = QAction('Open &session…', self)
        openSessionAction.setShortcut(QKeySequence('Ctrl+Shift+O'))
        openSessionAction.setStatusTip('Open a session file: its dataset, parameters, view and results')
        openSessionAction.triggered.connect(self.chooseSession)
        fileMenu.addAction(openSessionAction)

        self.recentSessionsMenu = fileMenu.addMenu('Open recent session')
        self.updateRecentSessionsMenu()

        saveSessionAction = QAction('Save session', self)
        saveSessionAction.setShortcut(QKeySequence.StandardKey.Save)
        saveSessionAction.setStatusTip('Save the dataset, parameters, view and results in the current session file')
        saveSessionAction.triggered.connect(self.saveSession)
        fileMenu.addAction(saveSessionAction)

        saveSessionAsAction = QAction('Save session &as…', self)
        saveSessionAsAction.setShortcut(QKeySequence('Ctrl+Shift+S'))
        saveSessionAsAction.triggered.connect(self.saveSessionAs)
        fileMenu.addAction(saveSessionAsAction)

        storageAction = QAction('Results and s&torage…', self)
        storageAction.setStatusTip('Results in sessions and between runs, the space they may take, the symmetry '
                                   'matrices kept, and the folder where they are')
        storageAction.triggered.connect(self.openStorageDialog)
        fileMenu.addAction(storageAction)

        fileMenu.addSeparator()
        exportImageAction = QAction('&Export 3D view as image…', self)
        exportImageAction.setShortcut(QKeySequence('Ctrl+E'))
        exportImageAction.triggered.connect(self.exportImage)
        fileMenu.addAction(exportImageAction)

        exportFigureAction = QAction('Export &figure…', self)
        exportFigureAction.setShortcut(QKeySequence('Ctrl+Shift+F'))
        exportFigureAction.setStatusTip('The plots as a publication figure, or a script that recreates it with Matplotlib')
        exportFigureAction.triggered.connect(self.exportFigure)
        fileMenu.addAction(exportFigureAction)

        self.exportDensityAction = QAction('Export probability &density…', self)
        self.exportDensityAction.setShortcut(QKeySequence('Ctrl+Shift+E'))
        self.exportDensityAction.setEnabled(False)
        self.exportDensityAction.triggered.connect(self.exportDensity)
        fileMenu.addAction(self.exportDensityAction)

        fileMenu.addSeparator()
        quitAction = QAction('&Quit', self)
        quitAction.setShortcut(QKeySequence.StandardKey.Quit)
        quitAction.triggered.connect(self.close)
        fileMenu.addAction(quitAction)

        # View
        viewMenu = self.menuBar().addMenu('&View')

        panelsMenu = viewMenu.addMenu('&Panels')
        # Whatever changed the docks, the ticks as they are now
        panelsMenu.aboutToShow.connect(self.panels.syncToggleActions)
        for action in self.panels.toggleActions():
            panelsMenu.addAction(action)
        viewMenu.addSeparator()

        themeMenu = viewMenu.addMenu('&Theme')
        themeGroup = QActionGroup(self)
        self.themeActions = {}
        for mode in THEME_MODES:
            action = QAction(mode, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, mode=mode: self.setTheme(mode))
            themeGroup.addAction(action)
            themeMenu.addAction(action)
            self.themeActions[mode] = action

        # Layout: presets and the user's own layouts
        self.layoutMenu = self.menuBar().addMenu('&Layout')
        self.attachFloatingAction = QAction('&Attach floating panels', self)
        self.attachFloatingAction.setStatusTip('Put the floating panels back into the main window, where they were')
        self.attachFloatingAction.triggered.connect(self.panels.attachAll)
        # Only when there are floating panels
        self.layoutMenu.aboutToShow.connect(
            lambda: self.attachFloatingAction.setEnabled(bool(self.panels.floatingKeys())))
        self.updateLayoutMenu()

        # Help
        helpMenu = self.menuBar().addMenu('&Help')
        aboutAction = QAction('&About Visual Excitons', self)
        aboutAction.triggered.connect(self.showAbout)
        helpMenu.addAction(aboutAction)

    def createStatusBar(self):
        # Running calculation: its message and stage, progress, and a cancel button
        self.taskLabel = QLabel()
        self.taskProgressBar = QProgressBar()
        self.taskProgressBar.setFixedWidth(160)
        self.taskProgressBar.setMaximumHeight(16)
        self.cancelButton = QToolButton()
        self.cancelButton.setText('Cancel')
        self.cancelButton.setToolTip('Stop the calculation and the queued ones (Esc)')
        self.cancelButton.setAutoRaise(True)
        self.cancelButton.clicked.connect(self.calculations.cancel)

        self.taskWidget = QWidget()
        layout = QHBoxLayout(self.taskWidget)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.addWidget(self.taskLabel)
        layout.addWidget(self.taskProgressBar)
        layout.addWidget(self.cancelButton)
        self.taskWidget.hide()
        self.statusBar().addPermanentWidget(self.taskWidget)

        cancelShortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancelShortcut.activated.connect(self.calculations.cancel)

        self.datasetLabel = QLabel()
        self.datasetLabel.setContentsMargins(8, 0, 8, 0)
        self.statusBar().addPermanentWidget(self.datasetLabel)
        self.updateDatasetLabel()

    # Panels and layouts

    PRESET_SHORTCUTS = {'System': 'Ctrl+1', 'Spectra': 'Ctrl+2', 'Wave function': 'Ctrl+3', 'Overview': 'Ctrl+4'}
    PRESET_TIPS = {'System': 'Data, crystal lattice and Q-path',
                   'Spectra': 'Dispersion, absorption and band structure, with their controls',
                   'Wave function': 'The exciton wave function in real space, its analysis and controls',
                   'Overview': 'All the panels at once'}

    def updateLayoutMenu(self):
        menu = self.layoutMenu
        menu.clear()
        for name in PRESETS:
            action = QAction(name, self)
            action.setShortcut(QKeySequence(self.PRESET_SHORTCUTS[name]))
            action.setStatusTip(self.PRESET_TIPS[name])
            action.triggered.connect(lambda checked=False, name=name: self.applyPreset(name))
            menu.addAction(action)

        names = self.panels.layoutNames()
        if names:
            menu.addSeparator()
            for name in names:
                action = QAction(name, self)
                action.setStatusTip('A layout you saved')
                action.triggered.connect(lambda checked=False, name=name: self.openLayout(name))
                menu.addAction(action)

        menu.addSeparator()
        menu.addAction(self.attachFloatingAction)

        menu.addSeparator()
        saveAction = QAction('&Save layout as…', self)
        saveAction.setStatusTip('Keep the current arrangement of the panels under a name')
        saveAction.triggered.connect(self.saveLayoutAs)
        menu.addAction(saveAction)
        deleteMenu = menu.addMenu('&Delete layout')
        for name in names:
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, name=name: self.deleteLayout(name))
            deleteMenu.addAction(action)
        deleteMenu.setEnabled(bool(names))

    @Slot(str)
    def applyPreset(self, name: str):
        # The analysis panel only if it is on
        closed = () if self.analysisCheckBox.isChecked() else ('analysis',)
        self.panels.applyPreset(name, closed)

    def openLayout(self, name):
        self.panels.openLayout(name)
        self.syncAnalysisCheckBox()

    @Slot()
    def saveLayoutAs(self):
        name, ok = QInputDialog.getText(self, 'Save layout', 'Name of the layout:')
        name = name.strip()
        if not ok or not name:
            return
        if name in PRESETS:
            QMessageBox.warning(self, 'Save layout', f'{name} is the name of a preset layout: choose another one.')
            return
        self.panels.saveLayout(name)
        self.panels.saveLayouts(self.settings)
        self.updateLayoutMenu()
        self.statusBar().showMessage(f'Layout {name} saved: it is in the Layout menu', 6000)

    def deleteLayout(self, name):
        self.panels.removeLayout(name)
        self.panels.saveLayouts(self.settings)
        self.updateLayoutMenu()
        self.statusBar().showMessage(f'Layout {name} deleted', 4000)

    def restoreLayout(self):
        """The layouts saved by the user, and the arrangement of the last run (or the default preset)."""
        self.panels.loadLayouts(self.settings)
        self.panels.homes = {key: home for key, home in self.loadJson('panelHomes', {}).items()
                             if key in self.panels.docks and isinstance(home, dict)}
        self.updateLayoutMenu()
        if not self.panels.restoreState(self.settings.value('panels', b'')):
            self.applyPreset(DEFAULT_PRESET)
        self.syncAnalysisCheckBox()

    def showPanel(self, key):
        self.panels.show(key)
        if key == 'analysis':
            self.analysisCheckBox.setChecked(True)
        elif key == 'composition':
            self.updateComposition()

    # Composition of the selected exciton (computed while its panel is shown)

    @Slot()
    def updateComposition(self, *args):
        # Open, and in front (behind another tab it catches up when brought up, see
        # CompositionPanel.showEvent); a window not shown (tests) shows nothing
        if self.panels.isShown('composition') and (self.compositionPanel.isVisible() or not self.isVisible()):
            self.calculations.computeComposition(self.calculations.sumDegenerate)

    @Slot(object)
    def onCompositionReady(self, composition):
        if composition is not None:
            lattice = self.calculations.lattice
            summary = self.dataset.latticeSummary() or {}
            self.compositionPanel.setCrystal(lattice.lat, lattice.rlat, lattice.red_kpoints, self.calculations.kGrid(),
                                             summary.get('layer'), self.dataset.highSymmetryPoints,
                                             self.qPathCartesian())
        self.compositionPanel.setComposition(composition)

    @Slot()
    def onCharacterSelection(self, *args):
        """Another exciton selected: whose symmetry and spin the Composition panel offers to analyse, and the cost."""
        selected = self.calculations.selectedExciton
        self.compositionPanel.setSelectedExciton(selected)
        self.updateCharacterSummary()
        o = self.dataset
        summary = o.latticeSummary() or {}
        grid, group = summary.get('grid'), summary.get('spaceGroup')
        if selected is None or not grid:
            self.compositionPanel.setCharacterCost('')
            return
        nk = int(np.prod(grid))
        operations = group[3] if group and len(group) > 3 else None
        loaded = any(key[0] == o.saveDir for key in list(self.calculations.wavefunctionCache.keys()))
        text = 'Loads the wave functions of the bands of the BSE' + (' (already loaded).' if loaded else '.')
        if operations:
            minutes = DMAT_SECONDS_PER_KPOINT * nk * operations / 60
            when = f'about {minutes:.0f} min' if minutes >= 1.5 else f'about {minutes * 60:.0f} s'
            text += (f' The first time for this dataset, the symmetry matrices take up to {when} ({nk} k-points, up '
                     f'to {operations} symmetries; fewer at a finite Q); they are then kept, on disk too.')
        self.compositionPanel.setCharacterCost(text)

    @Slot()
    def updateCharacterSummary(self, *args):
        """One line in the Selected exciton section: the symmetry and spin of the selected exciton, if analysed."""
        note = self.spectra.controls.characterSummary
        c = self.calculations.character
        if c is None or not self.calculations.characterMatches():
            note.hide()
            return
        parts = []
        if c.get('irreps'):
            parts.append(f'Symmetry {c["irreps"]} ({c["pointGroup"]})')
        if c.get('spin'):
            spins = ', '.join(f'{v:+.2f}' for v in c['spin']['total'])
            parts.append(f'spin along {c["axis"]}: {spins}')
        note.setText(' · '.join(parts) if parts else 'Symmetry and spin: see the Composition panel.')
        note.show()

    def qPathCartesian(self):
        """The k-points of the Q-path (Cartesian, Bohr⁻¹ without 2π), or None."""
        return self.dataset.qBZ.kpoints('car') if self.dataset.qBZ is not None else None

    @Slot()
    def exportComposition(self):
        c = self.calculations.composition
        if c is None:
            QMessageBox.information(self, 'Export composition', 'Select an exciton in a spectrum first.')
            return
        name = f'{datasetName(self.datasetRecord or {}) or "visual_excitons"}_Q{c["qIndex"] + 1}_exciton{c["excIndex"]}_composition.csv'
        filename, _ = QFileDialog.getSaveFileName(self, 'Export composition', self.exportPath(name), 'CSV files (*.csv)')
        if not filename:
            return
        from visual_excitons.core.kspace import compositionCSV
        try:
            Path(filename).write_text(compositionCSV(c, self.calculations.lattice, datasetName(self.datasetRecord or {})))
        except OSError as error:
            QMessageBox.critical(self, 'Export composition failed', str(error))
            return
        self.rememberExportFolder(filename)
        self.statusBar().showMessage(f'Composition saved to {filename}', 6000)

    @Slot()
    def exportCompositionImage(self):
        c = self.calculations.composition
        if c is None:
            QMessageBox.information(self, 'Export image', 'Select an exciton in a spectrum first.')
            return
        name = f'{datasetName(self.datasetRecord or {}) or "visual_excitons"}_Q{c["qIndex"] + 1}_exciton{c["excIndex"]}_kspace.png'
        filename, _ = QFileDialog.getSaveFileName(self, 'Export image', self.exportPath(name), IMAGE_FILTERS)
        if not filename:
            return
        if not Path(filename).suffix:
            filename += '.png'
        panel = self.compositionPanel
        image = panel.view3D.grabFramebuffer() if panel.is3D() else panel.mapPlot.grab().toImage()
        if not image.save(filename):
            QMessageBox.critical(self, 'Export image failed', f'Could not write {filename}')
            return
        self.rememberExportFolder(filename)
        self.statusBar().showMessage(f'Image saved to {filename}', 6000)

    @Slot()
    def computeSelectedWaveFunction(self):
        """The wave function of the exciton selected in the spectra, shown in its panel."""
        if self.wavefunction.controls.computeSelected():
            self.showPanel('wavefunction')

    @Slot(str, bool)
    def onPanelToggled(self, key, shown):
        if key == 'analysis':
            self.analysisCheckBox.setChecked(shown)
        elif key == 'composition' and shown:
            self.updateComposition()

    def syncAnalysisCheckBox(self):
        self.analysisCheckBox.setChecked(self.panels.isShown('analysis'))

    @Slot(str)
    def setTheme(self, mode: str):
        self.theme.setMode(mode)
        if hasattr(self, 'themeActions'):
            self.themeActions[self.theme.mode].setChecked(True)

    # Appearance of the 2D plots

    def plotStyles(self):
        return self.dispersionStyle, self.absorptionStyle, self.bandStructureStyle

    def appearanceState(self):
        return appearanceState(self.plotStyles(), self.theme.isDark())

    def restoreAppearance(self, state, curves=False):
        restoreAppearance(self.plotStyles(), state, self.theme.isDark(), curves)
        self.appearancePanel.refresh()

    def showAppearance(self, key):
        """The Appearance panel, on the style of plot `key`."""
        self.appearancePanel.setGraph(key)
        self.showPanel('appearance')

    def curveNames(self, key, count):
        """Names of the curves of a plot, for the Appearance panel."""
        if key == 'absorption':
            spectra = self.calculations.excAbsData
            return [f'Q-point {spectra[i]["q"] + 1}' if i < len(spectra) else f'Spectrum {i + 1}' for i in range(count)]
        return [f'{"Exciton" if key == "dispersion" else "Band"} {i + 1}' for i in range(count)]

    # Datasets

    def recentDatasets(self):
        try:
            recent = json.loads(self.settings.value('recentDatasets', '[]'))
        except (TypeError, ValueError):
            recent = []
        return [dataset for dataset in recent if isinstance(dataset, dict)]

    def addRecentDataset(self, dataset):
        recent = [d for d in self.recentDatasets() if d.get('save') != dataset.get('save')]
        recent.insert(0, dataset)
        self.settings.setValue('recentDatasets', json.dumps(recent[:MAX_RECENT_DATASETS]))
        self.updateRecentMenu()

    def updateRecentMenu(self):
        self.recentMenu.clear()
        recent = self.recentDatasets()
        for dataset in recent:
            action = QAction(datasetName(dataset), self)
            action.setToolTip(dataset.get('save') or '')
            action.setEnabled(datasetExists(dataset))
            action.triggered.connect(lambda checked=False, dataset=dataset: self.maybeSaveSession('opening another dataset') and self.openDataset(dataset))
            self.recentMenu.addAction(action)
        self.recentMenu.setEnabled(bool(recent))
        self.startPage.setRecentDatasets([(datasetName(dataset), str(Path(dataset.get('save') or '').parent),
                                           datasetExists(dataset), dataset) for dataset in recent])

    @Slot()
    def chooseDataset(self):
        if not self.maybeSaveSession('opening another dataset'):
            return
        start = str(Path(self.datasetRecord['save']).parent.parent) if self.datasetRecord and self.datasetRecord.get('save') else str(Path.cwd())
        folder = QFileDialog.getExistingDirectory(self, 'Open dataset', start, QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        dataset = findDataset(folder)
        if not datasetExists(dataset):
            QMessageBox.warning(self, 'Open dataset', f'No SAVE directory (with ns.db1) found in\n{folder}')
            return
        if dataset['diago'] is None:
            QMessageBox.warning(self, 'Open dataset', 'No BSE directory (with ndb.BS_diago_Q* files) found next to\n'
                                f'{dataset["save"]}\n\nYou can choose it in the System panel.')
        self.openDataset(dataset)

    def openDataset(self, dataset, restoreCached=True):
        """
        Open `dataset` (dict of its directories, QP file, GW; Q-path and state if
        saved), with the results kept for it from the last time if
        `restoreCached` (and Keep results between runs).
        """
        # Keep the results and the parameters of the dataset being left
        self.cacheResults()
        self.storeDatasetState()
        # Saving now must not overwrite the session of another setup
        self.sessionPath = None
        self.setWindowModified(False)

        # What was saved for this dataset (Q-path, parameters), even when it is
        # found again through Open dataset
        saved = next((d for d in self.recentDatasets() if d.get('save') == dataset.get('save')), {})
        self.datasetRecord = {**{key: saved[key] for key in ('qPath', 'state') if key in saved}, **dict(dataset)}
        dataset = self.datasetRecord
        self.dataset.setGW(bool(dataset.get('gw')))
        self.dataset.setSaveDir(dataset['save'])
        if dataset.get('diago'):
            self.dataset.setDiagoDir(dataset['diago'])
        if dataset.get('qp'):
            self.dataset.setQPDir(dataset['qp'], dataset.get('qpFile'))

        # The Q-path last set on this dataset, if any
        qPath = dataset.get('qPath')
        if qPath:
            if self.system.restoreQPath(qPath):
                self.statusBar().showMessage(f'Q-path {self.dataset.pathString()} restored', 4000)
            else:
                # Not valid any more (e.g. different lattice): forget it
                self.datasetRecord.pop('qPath', None)
                self.statusBar().showMessage('The saved Q-path could not be restored: set it again', 8000)

        self.state.restore(DATASET, dataset.get('state') or self.datasetDefaults)
        self.addRecentDataset(self.datasetRecord)
        self.updateDatasetLabel()
        self.setStartPageShown(False)
        if restoreCached:
            message = self.restoreCachedResults()
            if message:
                self.statusBar().showMessage(message, 8000)

    # Results kept between runs

    def cacheResults(self):
        """Keep the results of the dataset open (wave functions up to wavefunctionCacheLimit), for the next time."""
        if self.datasetRecord is None or not self.keepResults():
            return
        calc = self.calculations
        wf = calc.waveFunction
        # Never in the way of opening another dataset or closing the program: a failure is only reported
        try:
            meta, arrays = calc.resultsSnapshot(includeWaveFunction=wf is not None
                                                and wf.size * 4 <= self.wavefunctionCacheLimit())
            if meta:
                self.resultsCache.store(self.datasetRecord, meta, arrays, programVersion=__version__)
        except Exception as error:
            self.statusBar().showMessage(f'The results could not be kept for the next time: {error}', 8000)

    def restoreCachedResults(self):
        """Show the results kept for the dataset just opened, if any; what happened, for the status bar ('' if nothing)."""
        if self.datasetRecord is None or not self.keepResults():
            return ''
        cached, reason = self.resultsCache.load(self.datasetRecord)
        if cached is None:
            return reason[:1].upper() + reason[1:] if reason else ''
        meta, arrays = cached
        try:
            self.calculations.restoreResults(meta, arrays)
        except Exception as error:     # from an incompatible version, or damaged
            self.resultsCache.path(self.datasetRecord).unlink(missing_ok=True)
            return f'The results kept from the last time could not be shown ({error})'
        return 'The results of the last time were restored'

    # Results and storage (settings: sessionResults, cacheResults, cacheLimit, wavefunctionCacheLimit, cacheFolder)

    def storeSessionResults(self):
        return self.settings.value('sessionResults', True, type=bool)

    def keepResults(self):
        return self.settings.value('cacheResults', True, type=bool)

    def resultsCacheLimit(self):
        return int(self.settings.value('cacheLimit', CACHE_LIMIT, type=int))

    def wavefunctionCacheLimit(self):
        return int(self.settings.value('wavefunctionCacheLimit', WAVEFUNCTION_LIMIT, type=int))

    def storageFolder(self):
        folder = self.settings.value('cacheFolder', '', type=str)
        return Path(folder).expanduser() if folder else defaultStorageFolder()

    def applyStorage(self):
        """Use the storage folder and limits of the settings."""
        storage = self.storageFolder()
        self.resultsCache.folder = resultsCacheFolder(storage)
        self.resultsCache.limit = self.resultsCacheLimit()
        self.calculations.diskCacheFolder = str(storage)

    def storageUsage(self):
        """For the Results and storage dialog: size and number of kept results, size of the symmetry matrices."""
        return self.resultsCache.size(), len(self.resultsCache.entries()), folderUsage(self.storageFolder() / 'symmetry')[0]

    def clearSymmetryCache(self):
        self.calculations.symmetryCache = {}
        return clearFolder(self.storageFolder() / 'symmetry')

    @Slot()
    def openStorageDialog(self):
        values = {'storeSessionResults': self.storeSessionResults(), 'keepResults': self.keepResults(),
                  'cacheLimit': self.resultsCacheLimit(), 'wavefunctionLimit': self.wavefunctionCacheLimit(),
                  'folder': str(self.storageFolder())}
        dialog = StorageDialog(values, defaultStorageFolder(), self.storageUsage, self.resultsCache.clear,
                               self.clearSymmetryCache, parent=self)
        if dialog.exec():
            self.setStorage(dialog.values())

    def setStorage(self, values):
        """Apply the values of the Results and storage dialog; what is kept moves with a new folder."""
        old, new = self.storageFolder(), Path(values['folder']).expanduser()
        if new.resolve() != old.resolve():
            try:
                moveStorage(old, new)
            except OSError as error:
                QMessageBox.warning(self, 'Results and storage', f'What is kept could not be moved to {new}: {error}\n\n'
                                    f'The folder in use stays {old}.')
                new = old
        default = defaultStorageFolder()
        self.settings.setValue('cacheFolder', '' if new.resolve() == default.resolve() else str(new))
        self.settings.setValue('sessionResults', bool(values['storeSessionResults']))
        self.settings.setValue('cacheResults', bool(values['keepResults']))
        self.settings.setValue('cacheLimit', int(values['cacheLimit']))
        self.settings.setValue('wavefunctionCacheLimit', int(values['wavefunctionLimit']))
        self.applyStorage()
        self.resultsCache.prune()
        self.modifiedTimer.start()           # whether results are stored or kept changes what counts as unsaved

    def setStartPageShown(self, shown):
        self.startPage.setVisible(shown)
        # Drawn over every widget of the window (WA_AlwaysStackOnTop): hidden under the start page
        self.wavefunction.view.setGizmoSuppressed(shown)

    @Slot()
    def newSession(self):
        """Close the dataset and its results (preferences stay), back to the start page."""
        if not self.maybeSaveSession('starting a new session'):
            return
        self.calculations.cancel()
        # Its results and parameters stay with it, for when it is opened again
        self.cacheResults()
        self.storeDatasetState()
        self.datasetRecord = None
        self.sessionPath = None
        self.dataset.close()
        self.spectra.clearQPath()
        self.markSessionSaved()
        self.updateDatasetLabel()
        self.setStartPageShown(True)

    def storeDatasetState(self):
        """Save the parameters of the current dataset with it, in the recent datasets."""
        if self.datasetRecord is None:
            return
        self.datasetRecord['state'] = self.state.values(DATASET)
        recent = [dict(self.datasetRecord) if d.get('save') == self.datasetRecord.get('save') else d for d in self.recentDatasets()]
        self.settings.setValue('recentDatasets', json.dumps(recent))
        # The menu and start page open the datasets with what they hold: up to date
        self.updateRecentMenu()

    def loadJson(self, key, default):
        try:
            return json.loads(self.settings.value(key, json.dumps(default)))
        except (TypeError, ValueError):
            return default

    @Slot()
    def checkAllBSE(self):
        """Read every BSE database in the background, then show the checks of all of them."""
        from visual_excitons.core.consistency import checkDataset
        o = self.dataset
        if not o.saveDir or not o.bseFiles:
            return
        key = self.system.bseKey()
        arguments = dict(saveDir=o.saveDir, qpPath=f'{o.qpDir}/{o.qpFile}' if o.gw and o.qpDir and o.qpFile else None,
                         diagoDir=o.diagoDir, bseFiles=dict(o.bseFiles), bseProblems=list(o.bseProblems), bseSample=None)
        self.calculations.tasks.submit('Checking every BSE database…',
                                       lambda context: checkDataset(context=context, **arguments),
                                       lambda findings: self.system.setFullBSEChecks(key, findings), key='check-bse')

    @Slot(str, str)
    def onDirectoryChosen(self, kind, path):
        """
        A directory chosen in the System panel: a SAVE directory opens another
        dataset (with the BSE and GW directories in use); a BSE or GW directory
        changes those of the dataset open, and the results computed from them.
        """
        from visual_excitons.core.databases import bseFiles, qpDatabases
        path = str(Path(path).resolve())
        problem = {'save': lambda: not Path(path, 'ns.db1').is_file() and 'No SAVE database (ns.db1)',
                   'diago': lambda: not bseFiles(path)[0] and 'No BSE databases (ndb.BS_diago_Q*)',
                   'qp': lambda: not qpDatabases(path) and 'No QP database'}[kind]()
        if problem:
            QMessageBox.warning(self, 'Directory not used', f'{problem} found in\n{path}\n\n'
                                'The directory in use stays.')
            self.system.showDirectories()
            return
        o = self.dataset
        if kind == 'save':
            if self.datasetRecord is not None and not self.maybeSaveSession('opening another dataset'):
                self.system.showDirectories()
                return
            self.openDataset({'save': path, 'diago': o.diagoDir or None, 'qp': o.qpDir or None,
                              'qpFile': o.qpFile or None, 'gw': o.gw})
            return
        # The results of the directories in use, kept with them before they go
        self.cacheResults()
        if kind == 'diago':
            o.setDiagoDir(path)
            # The excitons may be others: everything computed from them goes
            self.calculations.resetDataset()
            self.wavefunction.onDatasetChanged(True)
        else:
            o.setQPDir(path)        # the spectra go in onQPDatabaseChosen
        if self.datasetRecord is not None:
            self.datasetRecord.update({'diago': o.diagoDir or None, 'qp': o.qpDir or None, 'qpFile': o.qpFile or None})
            self.addRecentDataset(self.datasetRecord)
        self.updateDatasetLabel()
        self.modifiedTimer.start()

    @Slot(bool)
    def onGWChanged(self, gw):
        """With or without the QP corrections: the energies change, the spectra go."""
        if self.datasetRecord is None or bool(self.datasetRecord.get('gw')) == gw:
            return            # opening a dataset, which sets it
        self.cacheResults()
        self.datasetRecord['gw'] = gw
        self.calculations.resetSpectra()
        self.addRecentDataset(self.datasetRecord)
        self.updateDatasetLabel()
        self.modifiedTimer.start()

    @Slot(list, str)
    def onQPDatabaseChosen(self, databases, name):
        """
        Remember the QP database used with the dataset (e.g. ndb.QP_140_146
        rather than ndb.QP); another one changes the energies: the spectra go.
        """
        if self.datasetRecord is None:
            return
        changed = (self.datasetRecord.get('qp'), self.datasetRecord.get('qpFile')) != (self.dataset.qpDir, name)
        if changed and self.dataset.gw:
            self.cacheResults()           # those of the QP database in use, before they go
        self.datasetRecord['qp'], self.datasetRecord['qpFile'] = self.dataset.qpDir, name
        if changed and self.dataset.gw and self.calculations.hasResults():
            self.calculations.resetSpectra()

    @Slot(dict)
    def saveQPath(self, state: dict):
        """Remember the Q-path of the current dataset, restored when it is opened again."""
        if self.datasetRecord is None or self.datasetRecord.get('save') != self.dataset.saveDir:
            return
        self.datasetRecord['qPath'] = state
        self.addRecentDataset(self.datasetRecord)

    @Slot()
    def updateDatasetLabel(self, *args):
        name = datasetName({'save': self.dataset.saveDir, 'diago': self.dataset.diagoDir,
                            'qp': self.dataset.qpDir if self.dataset.gw else None})
        parts = [name] if name else ['No dataset']
        if self.dataset.variant:
            parts.append(f'ibrav {self.dataset.ibrav} ({self.dataset.variant})' if self.dataset.ibrav != -1 else self.dataset.variant)
        if self.dataset.nQpoints:
            parts.append(self.dataset.qPointCount())
        self.datasetLabel.setText('  ·  '.join(parts))
        # [*]: where Qt shows the unsaved changes mark
        title = [self.sessionName() + '[*]'] if self.datasetRecord is not None else []
        title += [name] if name else []
        self.setWindowTitle(' — '.join(title + ['Visual Excitons']))

    # Sessions

    def sessionName(self):
        """The name of the current session: of its file, or Untitled before it is saved."""
        return Path(self.sessionPath).stem if self.sessionPath else 'Untitled'

    def recentSessions(self):
        return [path for path in self.loadJson('recentSessions', []) if isinstance(path, str)]

    def addRecentSession(self, path):
        path = str(Path(path).resolve())
        recent = [path] + [p for p in self.recentSessions() if p != path]
        self.settings.setValue('recentSessions', json.dumps(recent[:MAX_RECENT_DATASETS]))
        self.updateRecentSessionsMenu()

    def updateRecentSessionsMenu(self):
        self.recentSessionsMenu.clear()
        recent = self.recentSessions()
        for path in recent:
            action = QAction(Path(path).stem, self)
            action.setToolTip(path)
            action.setEnabled(Path(path).is_file())
            action.triggered.connect(lambda checked=False, path=path: self.maybeSaveSession('opening another session') and self.openSession(path))
            self.recentSessionsMenu.addAction(action)
        self.recentSessionsMenu.setEnabled(bool(recent))
        self.startPage.setRecentSessions([(Path(path).stem, str(Path(path).parent), Path(path).is_file(), path)
                                          for path in recent])

    def sessionFolder(self):
        return self.settings.value('sessionDir', str(Path.cwd()))

    @Slot()
    def saveSession(self):
        if self.sessionPath:
            self.writeSessionFile(self.sessionPath)
        else:
            self.saveSessionAs()

    @Slot()
    def saveSessionAs(self):
        if self.datasetRecord is None:
            QMessageBox.information(self, 'Save session', 'Open a dataset first.')
            return
        suggestion = Path(self.sessionPath).name if self.sessionPath else self.exportBaseName() + SESSION_SUFFIX
        filename, _ = QFileDialog.getSaveFileName(self, 'Save session', str(Path(self.sessionFolder()) / suggestion),
                                                  SESSION_FILTER)
        if not filename:
            return
        if not filename.endswith(SESSION_SUFFIX):
            filename += SESSION_SUFFIX
        self.writeSessionFile(filename)

    def sessionContent(self):
        """The manifest and arrays of a session file of the current setup."""
        self.storeDatasetState()
        dataset = {key: value for key, value in self.datasetRecord.items() if key != 'state'}
        manifest = {
            'dataset': dataset,
            'fingerprint': datasetFingerprint(dataset),
            'state': {'global': self.state.values(GLOBAL), 'dataset': self.state.values(DATASET)},
        }
        meta, arrays = self.calculations.resultsSnapshot() if self.storeSessionResults() else ({}, {})
        manifest['results'] = meta
        return manifest, arrays

    def writeSessionFile(self, path):
        if self.datasetRecord is None:
            QMessageBox.information(self, 'Save session', 'Open a dataset first.')
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            manifest, arrays = self.sessionContent()
            writeSession(path, manifest, arrays, programVersion=__version__)
        except OSError as error:
            QMessageBox.critical(self, 'Save session failed', str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.sessionPath = str(Path(path).resolve())
        self.settings.setValue('sessionDir', str(Path(path).resolve().parent))
        self.addRecentSession(path)
        self.updateDatasetLabel()
        self.markSessionSaved()
        note = '' if manifest['results'] or not self.storeSessionResults() else ' (no results to store)'
        if self.calculations.isBusy():
            note += '; the calculation still running is not included'
        self.statusBar().showMessage(f'Session saved to {path} ({Path(path).stat().st_size / 2**20:.1f} MB){note}', 8000)

    @Slot()
    def chooseSession(self):
        if not self.maybeSaveSession('opening another session'):
            return
        filename, _ = QFileDialog.getOpenFileName(self, 'Open session', self.sessionFolder(), SESSION_FILTER)
        if filename:
            self.openSession(filename)

    def openSession(self, path):
        try:
            manifest, arrays = readSession(path)
        except SessionError as error:
            QMessageBox.critical(self, 'Open session failed', str(error))
            return

        dataset = dict(manifest.get('dataset') or {})
        relocated = False
        if not datasetExists(dataset):
            dataset = self.locateDataset(dataset)
            if dataset is None:
                return
            relocated = True

        self.calculations.cancel()
        state = manifest.get('state', {})
        # Preferences of the session first: the dataset's parameters (camera
        # included) are restored when it is opened, after its lattice is drawn
        self.state.restore(GLOBAL, state.get('global', {}))
        dataset['state'] = state.get('dataset', {})
        results = manifest.get('results') or {}
        # The session's own results, if it has them; else those kept from the last time
        self.openDataset(dataset, restoreCached=not results)

        message = f'Session {Path(path).stem} opened'
        if results:
            if fingerprintsMatch(datasetFingerprint(dataset), manifest.get('fingerprint', {}), strict=not relocated):
                try:
                    self.calculations.restoreResults(results, arrays)
                    # Restoring the curves gave them the common style: now each its own
                    self.restoreAppearance(state.get('global', {}).get('appearance/styles'), curves=True)
                    message += ' with its results'
                except Exception as error:   # a session from an incompatible version, or damaged
                    message += f'; its results could not be shown ({error})'
            else:
                message += '; its results were not shown: the dataset changed since it was saved'

        self.sessionPath = str(Path(path).resolve())
        self.settings.setValue('sessionDir', str(Path(path).resolve().parent))
        self.addRecentSession(path)
        self.updateDatasetLabel()
        self.markSessionSaved()
        # Again once what opening it started has settled (e.g. the view)
        QTimer.singleShot(0, self.markSessionSaved)
        self.statusBar().showMessage(message, 10000)

    # Unsaved changes

    def sessionSignature(self):
        """What a session file of the current setup would hold, as a string (its results by version)."""
        state = {**self.state.values(GLOBAL), **self.state.values(DATASET)}
        # Not part of the setup: open sections, and the Appearance panel's own settings
        state = {key: value for key, value in state.items()
                 if '/section/' not in key and not key.startswith('appearancePanel/')}
        dataset = {key: value for key, value in (self.datasetRecord or {}).items() if key != 'state'}
        results = None
        if self.storeSessionResults():
            results = [self.calculations.resultsVersion, list(self.calculations.selectedExciton or [])]
        return json.dumps([state, dataset, results], sort_keys=True, default=str)

    def markSessionSaved(self):
        self.savedSignature = self.sessionSignature() if self.sessionPath else None
        self.setWindowModified(False)

    @Slot()
    def updateModified(self):
        if self.sessionPath is not None:
            modified = self.sessionSignature() != self.savedSignature
        else:
            # Not saved yet: only results would be lost (the parameters stay with the dataset), unless they are
            # kept between runs
            modified = (self.datasetRecord is not None and self.storeSessionResults()
                        and not self.keepResults() and self.calculations.hasResults())
        if modified != self.isWindowModified():
            self.setWindowModified(modified)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.KeyRelease, QEvent.Type.Wheel):
            if self.datasetRecord is not None:
                self.modifiedTimer.start()
        return False

    def maybeSaveSession(self, action):
        """
        Before `action` (e.g. "closing"), offer to save the unsaved changes of
        the session; False if the user cancels (or saving failed).
        """
        self.updateModified()
        if not self.isWindowModified():
            return True
        if self.sessionPath:
            text = f'The session {self.sessionName()} has changes that are not saved.\n\nSave them before {action}?'
        else:
            text = f'The results of this session are not saved.\n\nSave the session before {action}?'
        answer = QMessageBox.warning(
            self, 'Unsaved changes', text,
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            if self.sessionPath:
                self.writeSessionFile(self.sessionPath)
            else:
                self.saveSessionAs()
            self.updateModified()
            return not self.isWindowModified()
        return answer == QMessageBox.StandardButton.Discard

    def locateDataset(self, dataset):
        """Ask for the folder of a dataset that is not where the session says; None if not found."""
        answer = QMessageBox.question(
            self, 'Dataset not found',
            f'The dataset of this session was not found at\n{dataset.get("save") or "(unknown)"}\n\n'
            'Has it been moved? Locate its folder to open the session with it.',
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Open)
        if answer != QMessageBox.StandardButton.Open:
            return None
        folder = QFileDialog.getExistingDirectory(self, 'Locate the dataset', str(Path.cwd()),
                                                  QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return None
        found = findDataset(folder)
        if not datasetExists(found):
            QMessageBox.warning(self, 'Dataset not found', f'No SAVE directory (with ns.db1) found in\n{folder}')
            return None
        found['qPath'] = dataset.get('qPath')
        return found

    # Calculations

    @Slot(bool)
    def onBusyChanged(self, busy: bool):
        self.taskWidget.setVisible(busy)
        # The window stays usable: a busy cursor, not a wait cursor
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()
            if not self.statusBar().currentMessage():
                self.statusBar().showMessage('Ready', 2000)

    @Slot(str)
    def onTaskStarted(self, message: str):
        self.taskMessage = message
        self.taskStage = ''
        self.taskProgressBar.setRange(0, 0)  # unknown length until a stage reports it
        self.updateTaskLabel()

    @Slot(int, int, str)
    def onProgress(self, done: int, total: int, stage: str):
        if total > 0:
            self.taskProgressBar.setRange(0, total)
            self.taskProgressBar.setValue(min(done, total))
        else:
            self.taskProgressBar.setRange(0, 0)
        self.taskStage = stage
        self.updateTaskLabel()

    def updateTaskLabel(self):
        text = getattr(self, 'taskMessage', '')
        if getattr(self, 'taskStage', ''):
            text = f'{text.rstrip("…")} — {self.taskStage}'
        queued = self.calculations.tasks.queuedCount()
        if queued:
            text += f'  (+{queued} queued)'
        self.taskLabel.setText(text)

    @Slot(str)
    def onTaskCancelled(self, message: str):
        self.statusBar().showMessage(f'Cancelled: {message.rstrip("…").lower()}', 4000)

    @Slot(str, str)
    def onError(self, title: str, message: str):
        QMessageBox.critical(self, title, message)

    @Slot(int, int, float)
    def onExcitonSelected(self, qIndex: int, excIndex: int, energy: float):
        self.statusBar().showMessage(f'Selected exciton {excIndex} at Q-point {qIndex + 1} (E = {energy:.4f} eV)', 8000)

    # Export

    def exportBaseName(self):
        """File name without extension: the dataset, and the exciton of the wave function if any."""
        name = datasetName(self.datasetRecord or {}) or 'visual_excitons'
        if self.calculations.waveFunction is not None and self.calculations.wfExciton is not None:
            qIndex, excIndex = self.calculations.wfExciton
            name += f'_Q{qIndex + 1}_exciton{excIndex}'
        return name

    def exportPath(self, filename):
        folder = self.settings.value('exportDir', str(Path.cwd()))
        return str(Path(folder) / filename)

    def rememberExportFolder(self, filename):
        self.settings.setValue('exportDir', str(Path(filename).parent))

    @Slot(bool)
    def onDatasetForExports(self, found):
        # A density belongs to the dataset it was computed on
        self.exportDensityAction.setEnabled(False)
        self.wavefunction.controls.exportDensityButton.setEnabled(False)

    # The export dialogs' choices, as kept in the settings (see the dialogs)

    IMAGE_EXPORT_KEYS = {'scale': int, 'width': int, 'transparent': bool, 'gizmo': bool, 'cellInfo': bool, 'caption': bool}

    def figureExportState(self):
        try:
            saved = json.loads(self.settings.value('figureExport/options', '{}'))
        except (TypeError, ValueError):
            saved = {}
        return saved if isinstance(saved, dict) else {}

    def restoreFigureExportState(self, state):
        if isinstance(state, dict):
            self.settings.setValue('figureExport/options', json.dumps(state))

    def imageExportState(self):
        state = {}
        for key, kind in self.IMAGE_EXPORT_KEYS.items():
            if self.settings.contains(f'imageExport/{key}'):
                state[key] = self.settings.value(f'imageExport/{key}', type=kind)
        return state

    def restoreImageExportState(self, state):
        if isinstance(state, dict):
            for key, kind in self.IMAGE_EXPORT_KEYS.items():
                if key in state:
                    self.settings.setValue(f'imageExport/{key}', kind(state[key]))

    @Slot()
    def exportImage(self):
        # The view must have been shown to be rendered
        self.showPanel('wavefunction')
        QApplication.processEvents()
        view = self.wavefunction.view
        dialog = ImageExportDialog(view, self)
        if dialog.exec() != ImageExportDialog.DialogCode.Accepted:
            return
        self.modifiedTimer.start()          # its choices are part of the session
        filename, _ = QFileDialog.getSaveFileName(self, 'Export image', self.exportPath(self.exportBaseName() + '.png'),
                                                  IMAGE_FILTERS)
        if not filename:
            return
        if not Path(filename).suffix:
            filename += '.png'
        try:
            saveImage(dialog.composedImage(), filename, view.backgroundColor())
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, 'Export image failed', str(error))
            return
        self.rememberExportFolder(filename)
        width, height = dialog.imageSize()
        self.statusBar().showMessage(f'Image ({width} × {height}) saved to {filename}', 6000)

    @Slot()
    def exportFigure(self, panels=None):
        """The figure export dialog; `panels`: those to check at first (the panel's own, from its button)."""
        data = figureData(self.calculations, self.compositionPanel.figureData(),
                          self.wavefunction.analysis.figureData())
        if not figures.availablePanels(data):
            QMessageBox.information(self, 'Export figure',
                                    'Nothing to export yet: compute a dispersion, absorption spectra, a band '
                                    "structure, an exciton's composition or a wave function's analysis.")
            return
        if panels:
            panels = [p for p in panels if p in figures.availablePanels(data)] or None
        styles = figureStyles(self.dispersionStyle, self.absorptionStyle, self.bandStructureStyle)
        name = datasetName(self.datasetRecord or {}) or 'figure'
        dialog = FigureExportDialog(data, styles, defaultName=f'{name}_figure', programVersion=__version__, parent=self,
                                    panels=panels)
        dialog.exec()
        self.modifiedTimer.start()          # its choices are part of the session
        if getattr(dialog, 'savedFile', None):
            self.statusBar().showMessage(f'Saved {dialog.savedFile}', 6000)

    @Slot()
    def exportDensity(self):
        if self.calculations.waveFunction is None:
            QMessageBox.information(self, 'Export probability density', 'Compute a wave function first.')
            return
        filters = 'Gaussian cube (*.cube);;XCrySDen XSF (*.xsf)'
        filename, chosenFilter = QFileDialog.getSaveFileName(
            self, 'Export probability density', self.exportPath(self.exportBaseName() + '.cube'), filters)
        if not filename:
            return
        if Path(filename).suffix.lower() not in ('.cube', '.xsf'):
            filename += '.xsf' if 'xsf' in chosenFilter else '.cube'
        self.rememberExportFolder(filename)
        # As shown (with the cell origin), or as computed
        shifted = self.wavefunction.controls.exportShiftedCheckBox.isChecked()
        self.calculations.exportDensity(filename, self.wavefunction.shownShift() if shifted else None)

    # Misc

    def showAbout(self):
        QMessageBox.about(self, 'About Visual Excitons',
                          f'<b>Visual Excitons {__version__}</b><br>Visualization of excitonic properties computed with '
                          '<a href="https://www.yambo-code.eu/">Yambo</a>, read through YamboPy.')

    def closeEvent(self, event):
        if not self.maybeSaveSession('closing'):
            event.ignore()
            return
        # Stop the calculations; the running one ends at its next progress check
        self.calculations.cancel()
        self.calculations.tasks.waitForDone(10000)
        self.cacheResults()
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('panels', self.panels.saveState())
        self.panels.recordHomes()
        self.settings.setValue('panelHomes', json.dumps(self.panels.homes))
        self.settings.setValue('theme', self.theme.mode)
        self.settings.setValue('state', json.dumps(self.state.values(GLOBAL)))
        self.storeDatasetState()
        # Last: closing them changes what is saved above (closed docks)
        self.panels.closeFloatingWindows()
        super().closeEvent(event)
