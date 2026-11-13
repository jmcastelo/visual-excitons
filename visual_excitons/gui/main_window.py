"""
Main window: dockable panels (see docking.py) for the system, the spectra and
the wave function, arranged by preset or saved layouts (Layout menu); menus, a
status bar and persistent settings frame them.
"""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QSettings, QTimer, QEvent
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QLabel, QFileDialog, QMessageBox, QApplication,
                               QProgressBar, QToolButton, QInputDialog)

from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from visual_excitons.core.dataset import findDataset, datasetName, datasetExists
from .options_widget import OptionsWidget
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
DEFAULT_DATASET_FOLDER = Path(__file__).resolve().parents[2] / 'data' / 'BiI3_Bulk_8x8x8'

MAX_RECENT_DATASETS = 8

# Narrowest width of the control panels
MIN_CONTROLS_WIDTH = 260


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings('VisualExcitons', 'VisualExcitons')
        self.theme = themeManager()

        self.options = Options()
        self.calculations = Calculations(self.options)
        self.dataset = None
        self.sessionPath = None   # session file of the current setup, if saved or opened

        self.createStyles()
        self.createPanels()
        self.createMenus()
        self.createStatusBar()

        # A new SAVE directory invalidates everything computed before; reset
        # first, then redraw the lattice
        self.options.databaseFound.connect(lambda found: self.calculations.resetDataset())
        self.options.databaseFound.connect(self.wavefunction.onDatasetChanged)
        self.options.databaseFound.connect(self.updateDatasetLabel)
        self.options.numQPointsChanged.connect(self.updateDatasetLabel)
        self.options.saveDirChanged.connect(self.updateDatasetLabel)

        self.calculations.busyStarted.connect(self.onTaskStarted)
        self.calculations.busyChanged.connect(self.onBusyChanged)
        self.calculations.progressChanged.connect(self.onProgress)
        self.calculations.taskCancelled.connect(self.onTaskCancelled)
        self.calculations.errorOccurred.connect(self.onError)
        self.calculations.excitonSelected.connect(self.onExcitonSelected)
        self.calculations.wfComputed.connect(lambda: self.exportDensityAction.setEnabled(True))
        self.calculations.densityExported.connect(
            lambda filename: self.statusBar().showMessage(f'Probability density saved to {filename}', 6000))
        self.options.databaseFound.connect(self.onDatasetForExports)
        self.options.qpDatabasesChanged.connect(self.onQPDatabaseChosen)

        self.theme.themeChanged.connect(self.spectra.setDarkTheme)
        self.theme.themeChanged.connect(self.wavefunction.setDarkTheme)
        self.theme.themeChanged.connect(self.panels.applyTheme)
        self.setTheme(self.settings.value('theme', 'System'))

        # Parameters kept between sessions (see persistence.py): preferences now,
        # those of a dataset when it is opened
        self.state = StateRegistry()
        self.state.add('spectra', self.spectra.inspector.persistence)
        self.state.add('wavefunction', self.wavefunction.inspector.persistence)
        # The camera (the name dates from when it was kept with the page layout:
        # kept for the settings and sessions saved then)
        self.state.add('wavefunctionLayout', self.wavefunction.persistence)
        # The Appearance of the 2D plots (in sessions with the style of each curve)
        self.appearance = PersistentState()
        self.appearance.remember('styles', get=self.appearanceState, set=self.restoreAppearance)
        self.state.add('appearance', self.appearance)
        self.state.add('appearancePanel', self.appearancePanel.persistence)
        # A dataset opened for the first time starts from the defaults, not from
        # the parameters of the previous one
        self.datasetDefaults = self.state.values(DATASET)
        self.state.restore(GLOBAL, self.loadJson('state', {}))

        if not self.restoreGeometry(self.settings.value('geometry', b'')):
            self.resize(1600, 1000)
        self.restoreLayout()
        self.openInitialDataset()

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
        self.system = OptionsWidget(self.options)
        self.spectra = SpectraPanels(self.options, self.calculations, self.dispersionStyle, self.absorptionStyle,
                                     self.bandStructureStyle, parent=self)
        self.wavefunction = WavefunctionPanels(self.options, self.calculations, parent=self)
        self.spectra.inspector.computeWavefunctionRequested.connect(self.computeSelectedWaveFunction)
        self.wavefunction.parameters3DWidget.selectedEstimateChanged.connect(self.spectra.inspector.setWaveFunctionEstimate)
        self.system.qPathApplied.connect(self.saveQPath)
        self.system.checkAllBSERequested.connect(self.checkAllBSE)
        self.spectra.inspector.exportFigureRequested.connect(self.exportFigure)
        self.wavefunction.parameters3DWidget.exportImageRequested.connect(self.exportImage)
        self.wavefunction.parameters3DWidget.exportDensityRequested.connect(self.exportDensity)

        # The styles of the 2D plots
        self.appearancePanel = AppearancePanel({'dispersion': self.dispersionStyle, 'absorption': self.absorptionStyle,
                                                'bands': self.bandStructureStyle}, curveNames=self.curveNames)
        for signal in (self.calculations.excitonAbsorptionReady, self.calculations.excitonBandStructureReady,
                       self.calculations.excitonDispersionReady):
            signal.connect(self.appearancePanel.scheduleRefresh)   # the curves to choose from

        self.panels = Panels(self)
        for inspector in (self.spectra.inspector, self.wavefunction.inspector, self.appearancePanel):
            inspector.setMinimumWidth(max(MIN_CONTROLS_WIDTH, inspector.minimumWidth()))
        for key, widget in (('system', scrollable(self.system)),
                            ('dispersion', self.spectra.dispersionWidget),
                            ('absorption', self.spectra.absorptionWidget),
                            ('bands', self.spectra.bandStructureWidget),
                            ('wavefunction', self.wavefunction.excitonWfWidget),
                            ('analysis', self.wavefunction.analysisWidget),
                            ('spectraControls', self.spectra.inspector),
                            ('appearance', self.appearancePanel),
                            ('wavefunctionControls', self.wavefunction.inspector)):
            self.panels.add(key, widget)

        # Each plot's style, from its panel's title bar and its right-click menu
        views = {'dispersion': self.spectra.dispersionWidget.getPlotItem().vb,
                 'absorption': self.spectra.absorptionWidget.absorption.vb,
                 'bands': self.spectra.bandStructureWidget.getPlotItem().vb}
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
        self.analysisCheckBox = self.wavefunction.parameters3DWidget.showAnalysisCheckBox
        self.analysisCheckBox.toggled.connect(lambda shown: self.panels.setShown('analysis', shown))
        self.panels.panelToggled.connect(self.onPanelToggled)

    def createMenus(self):
        # File
        fileMenu = self.menuBar().addMenu('&File')

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

        self.sessionResultsAction = QAction('Store results in sessions', self)
        self.sessionResultsAction.setCheckable(True)
        self.sessionResultsAction.setChecked(self.settings.value('sessionResults', True, type=bool))
        self.sessionResultsAction.setStatusTip('Store the computed results in session files, so that they are '
                                               'shown at once when opened (larger files)')
        self.sessionResultsAction.toggled.connect(lambda store: self.settings.setValue('sessionResults', store))
        fileMenu.addAction(self.sessionResultsAction)

        fileMenu.addSeparator()
        exportImageAction = QAction('&Export 3D view as image…', self)
        exportImageAction.setShortcut(QKeySequence('Ctrl+E'))
        exportImageAction.triggered.connect(self.exportImage)
        fileMenu.addAction(exportImageAction)

        exportFigureAction = QAction('Export 2D &figure…', self)
        exportFigureAction.setShortcut(QKeySequence('Ctrl+Shift+F'))
        exportFigureAction.setStatusTip('The 2D plots as a publication figure, or a script that recreates it with Matplotlib')
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

    @Slot()
    def computeSelectedWaveFunction(self):
        """The wave function of the exciton selected in the spectra, shown in its panel."""
        if self.wavefunction.parameters3DWidget.computeSelected():
            self.showPanel('wavefunction')

    @Slot(str, bool)
    def onPanelToggled(self, key, shown):
        if key == 'analysis':
            self.analysisCheckBox.setChecked(shown)

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

    def openInitialDataset(self):
        for dataset in self.recentDatasets():
            if datasetExists(dataset):
                self.openDataset(dataset)
                return
        if DEFAULT_DATASET_FOLDER.is_dir():
            dataset = findDataset(DEFAULT_DATASET_FOLDER)
            if datasetExists(dataset):
                self.openDataset(dataset)

    @Slot()
    def chooseDataset(self):
        if not self.maybeSaveSession('opening another dataset'):
            return
        start = str(Path(self.dataset['save']).parent.parent) if self.dataset and self.dataset.get('save') else str(Path.cwd())
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

    def openDataset(self, dataset):
        # Keep the parameters of the dataset being left
        self.storeDatasetState()
        # Saving now must not overwrite the session of another setup
        self.sessionPath = None
        self.setWindowModified(False)

        # What was saved for this dataset (Q-path, parameters), even when it is
        # found again through Open dataset
        saved = next((d for d in self.recentDatasets() if d.get('save') == dataset.get('save')), {})
        self.dataset = {**{key: saved[key] for key in ('qPath', 'state') if key in saved}, **dict(dataset)}
        dataset = self.dataset
        self.options.setGW(bool(dataset.get('gw')))
        self.options.setSaveDir(dataset['save'])
        if dataset.get('diago'):
            self.options.setDiagoDir(dataset['diago'])
        if dataset.get('qp'):
            self.options.setQPDir(dataset['qp'], dataset.get('qpFile'))

        # The Q-path last set on this dataset, if any
        qPath = dataset.get('qPath')
        if qPath:
            if self.system.restoreQPath(qPath):
                self.statusBar().showMessage(f'Q-path {self.options.getPathString()} restored', 4000)
            else:
                # Not valid any more (e.g. different lattice): forget it
                self.dataset.pop('qPath', None)
                self.statusBar().showMessage('The saved Q-path could not be restored: set it again', 8000)

        self.state.restore(DATASET, dataset.get('state') or self.datasetDefaults)
        self.addRecentDataset(self.dataset)
        self.updateDatasetLabel()

    def storeDatasetState(self):
        """Save the parameters of the current dataset with it, in the recent datasets."""
        if self.dataset is None:
            return
        self.dataset['state'] = self.state.values(DATASET)
        recent = [dict(self.dataset) if d.get('save') == self.dataset.get('save') else d for d in self.recentDatasets()]
        self.settings.setValue('recentDatasets', json.dumps(recent))

    def loadJson(self, key, default):
        try:
            return json.loads(self.settings.value(key, json.dumps(default)))
        except (TypeError, ValueError):
            return default

    @Slot()
    def checkAllBSE(self):
        """Read every BSE database in the background, then show the checks of all of them."""
        from visual_excitons.core.consistency import checkDataset
        o = self.options
        if not o.saveDir or not o.bseFiles:
            return
        key = self.system.bseKey()
        arguments = dict(saveDir=o.saveDir, qpPath=f'{o.qpDir}/{o.qpFile}' if o.gw and o.qpDir and o.qpFile else None,
                         diagoDir=o.diagoDir, bseFiles=dict(o.bseFiles), bseProblems=list(o.bseProblems), bseSample=None)
        self.calculations.tasks.submit('Checking every BSE database…',
                                       lambda context: checkDataset(context=context, **arguments),
                                       lambda findings: self.system.setFullBSEChecks(key, findings), key='check-bse')

    @Slot(list, str)
    def onQPDatabaseChosen(self, databases, name):
        """Remember the QP database used with the dataset (e.g. ndb.QP_140_146 rather than ndb.QP)."""
        if self.dataset is not None:
            self.dataset['qp'], self.dataset['qpFile'] = self.options.qpDir, name

    @Slot(dict)
    def saveQPath(self, state: dict):
        """Remember the Q-path of the current dataset, restored when it is opened again."""
        if self.dataset is None or self.dataset.get('save') != self.options.saveDir:
            return
        self.dataset['qPath'] = state
        self.addRecentDataset(self.dataset)

    @Slot()
    def updateDatasetLabel(self, *args):
        name = datasetName({'save': self.options.saveDir, 'diago': self.options.diagoDir,
                            'qp': self.options.qpDir if self.options.gw else None})
        parts = [name] if name else ['No dataset']
        if self.options.variant:
            parts.append(f'ibrav {self.options.ibrav} ({self.options.variant})' if self.options.ibrav != -1 else self.options.variant)
        if self.options.nQpoints:
            parts.append(self.options.qPointCount())
        self.datasetLabel.setText('  ·  '.join(parts))
        # [*]: where Qt shows the unsaved changes mark
        title = [Path(self.sessionPath).stem + '[*]'] if self.sessionPath else []
        title += [name] if name else []
        self.setWindowTitle(' — '.join(title + ['Visual Excitons']))

    # Sessions

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
        if self.dataset is None:
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
        dataset = {key: value for key, value in self.dataset.items() if key != 'state'}
        manifest = {
            'dataset': dataset,
            'fingerprint': datasetFingerprint(dataset),
            'state': {'global': self.state.values(GLOBAL), 'dataset': self.state.values(DATASET)},
        }
        meta, arrays = self.calculations.resultsSnapshot() if self.sessionResultsAction.isChecked() else ({}, {})
        manifest['results'] = meta
        return manifest, arrays

    def writeSessionFile(self, path):
        if self.dataset is None:
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
        note = '' if manifest['results'] or not self.sessionResultsAction.isChecked() else ' (no results to store)'
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
        self.openDataset(dataset)

        results = manifest.get('results') or {}
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
        dataset = {key: value for key, value in (self.dataset or {}).items() if key != 'state'}
        results = None
        if self.sessionResultsAction.isChecked():
            results = [self.calculations.resultsVersion, list(self.calculations.selectedExciton or [])]
        return json.dumps([state, dataset, results], sort_keys=True, default=str)

    def markSessionSaved(self):
        self.savedSignature = self.sessionSignature() if self.sessionPath else None
        self.setWindowModified(False)

    @Slot()
    def updateModified(self):
        modified = self.sessionPath is not None and self.sessionSignature() != self.savedSignature
        if modified != self.isWindowModified():
            self.setWindowModified(modified)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.KeyRelease, QEvent.Type.Wheel):
            if self.sessionPath is not None:
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
        name = Path(self.sessionPath).stem
        answer = QMessageBox.warning(
            self, 'Unsaved changes', f'The session {name} has changes that are not saved.\n\n'
            f'Save them before {action}?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            self.writeSessionFile(self.sessionPath)
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
        name = datasetName(self.dataset or {}) or 'visual_excitons'
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
        self.wavefunction.parameters3DWidget.exportDensityButton.setEnabled(False)

    @Slot()
    def exportImage(self):
        # The view must have been shown to be rendered
        self.showPanel('wavefunction')
        QApplication.processEvents()
        view = self.wavefunction.excitonWfWidget
        dialog = ImageExportDialog(view, self)
        if dialog.exec() != ImageExportDialog.DialogCode.Accepted:
            return
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
    def exportFigure(self):
        data = figureData(self.calculations)
        if not figures.availablePanels(data):
            QMessageBox.information(self, 'Export 2D figure',
                                    'Nothing to export yet: compute a dispersion, absorption spectra or a band structure.')
            return
        styles = figureStyles(self.dispersionStyle, self.absorptionStyle, self.bandStructureStyle)
        name = datasetName(self.dataset or {}) or 'figure'
        dialog = FigureExportDialog(data, styles, defaultName=f'{name}_figure', programVersion=__version__, parent=self)
        dialog.exec()
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
        self.calculations.exportDensity(filename)

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
