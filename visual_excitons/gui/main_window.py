"""
Main window: a navigation bar on the left switches between the pages (System,
Spectra, Wavefunction); menus, a status bar and persistent settings frame them.
"""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QMainWindow, QStackedWidget, QWidget, QHBoxLayout, QLabel, QFileDialog, QMessageBox,
                               QApplication, QProgressBar, QToolButton)

from visual_excitons.core.options import Options
from visual_excitons.core.calculations import Calculations
from visual_excitons.core.style import DispersionStyle, AbsorptionStyle, BandStructureStyle
from visual_excitons.core.dataset import findDataset, datasetName, datasetExists
from .options_widget import OptionsWidget
from .graphs_widget import GraphsWidget
from .graphs_3d_widget import Graphs3DWidget
from .navigation_bar import NavigationBar
from .theme import themeManager, THEME_MODES
from visual_excitons import __version__
from .persistence import StateRegistry, GLOBAL, DATASET
from .image_export import ImageExportDialog, IMAGE_FILTERS, saveImage
from .figure_export import FigureExportDialog, figureData, figureStyles
from visual_excitons.core import figures
from visual_excitons.core.session import (readSession, writeSession, datasetFingerprint, fingerprintsMatch,
                                          SessionError, SESSION_SUFFIX, SESSION_FILTER)


# Opened on the first run, when there is no recent dataset (relative to the repository)
DEFAULT_DATASET_FOLDER = Path(__file__).resolve().parents[2] / 'data' / 'BiI3_Bulk_8x8x8'

MAX_RECENT_DATASETS = 8

SYSTEM_PAGE, SPECTRA_PAGE, WAVEFUNCTION_PAGE = range(3)


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
        self.createPages()
        self.createMenus()
        self.createStatusBar()

        # A new SAVE directory invalidates everything computed before; reset
        # first, then redraw the lattice
        self.options.databaseFound.connect(lambda found: self.calculations.resetDataset())
        self.options.databaseFound.connect(self.wavefunctionPage.onDatasetChanged)
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

        self.theme.themeChanged.connect(self.spectraPage.setDarkTheme)
        self.theme.themeChanged.connect(self.wavefunctionPage.setDarkTheme)
        self.setTheme(self.settings.value('theme', 'System'))

        # Parameters kept between sessions (see persistence.py): preferences now,
        # those of a dataset when it is opened
        self.state = StateRegistry()
        self.state.add('spectra', self.spectraPage.inspector.persistence)
        self.state.add('spectraLayout', self.spectraPage.persistence)
        self.state.add('wavefunction', self.wavefunctionPage.inspector.persistence)
        self.state.add('wavefunctionLayout', self.wavefunctionPage.persistence)
        # A dataset opened for the first time starts from the defaults, not from
        # the parameters of the previous one
        self.datasetDefaults = self.state.values(DATASET)
        self.state.restore(GLOBAL, self.loadJson('state', {}))

        if not self.restoreGeometry(self.settings.value('geometry', b'')):
            self.resize(1600, 1000)
        self.setPage(int(self.settings.value('page', SYSTEM_PAGE)))
        self.openInitialDataset()

    # Construction

    def createStyles(self):
        self.dispersionStyle = DispersionStyle()
        self.absorptionStyle = AbsorptionStyle()
        self.bandStructureStyle = BandStructureStyle()

        self.dispersionStyle.setLinkedStyles([self.absorptionStyle, self.bandStructureStyle])
        self.absorptionStyle.setLinkedStyles([self.dispersionStyle, self.bandStructureStyle])
        self.bandStructureStyle.setLinkedStyles([self.dispersionStyle, self.absorptionStyle])

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

    def createPages(self):
        self.systemPage = OptionsWidget(self.options)
        self.spectraPage = GraphsWidget(self.options, self.calculations, self.dispersionStyle, self.absorptionStyle,
                                        self.bandStructureStyle)
        self.wavefunctionPage = Graphs3DWidget(self.options, self.calculations)
        self.spectraPage.inspector.showWavefunctionRequested.connect(lambda: self.setPage(WAVEFUNCTION_PAGE))
        self.systemPage.qPathApplied.connect(self.saveQPath)
        self.spectraPage.inspector.exportFigureRequested.connect(self.exportFigure)
        self.wavefunctionPage.parameters3DWidget.exportImageRequested.connect(self.exportImage)
        self.wavefunctionPage.parameters3DWidget.exportDensityRequested.connect(self.exportDensity)

        self.stack = QStackedWidget()
        for page in (self.systemPage, self.spectraPage, self.wavefunctionPage):
            self.stack.addWidget(page)

        self.navigation = NavigationBar()
        self.navigation.addPage('System', 'crystal', 'Data, crystal lattice and Q-path (Ctrl+1)')
        self.navigation.addPage('Spectra', 'spectrum', 'Dispersion, absorption and band structure (Ctrl+2)')
        self.navigation.addPage('Wave\nfunction', 'orbital', 'Exciton wave function in real space (Ctrl+3)')
        self.navigation.pageSelected.connect(self.setPage)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

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

        pageGroup = QActionGroup(self)
        self.pageActions = []
        for index, text in enumerate(('&System', 'S&pectra', '&Wave function')):
            action = QAction(text, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(f'Ctrl+{index + 1}'))
            action.triggered.connect(lambda checked=False, index=index: self.setPage(index))
            pageGroup.addAction(action)
            viewMenu.addAction(action)
            self.pageActions.append(action)

        viewMenu.addSeparator()
        self.inspectorAction = QAction('Show &side panel', self)
        self.inspectorAction.setCheckable(True)
        self.inspectorAction.setChecked(self.settings.value('showInspector', True, type=bool))
        self.inspectorAction.setShortcut(QKeySequence('Ctrl+B'))
        self.inspectorAction.toggled.connect(self.setInspectorVisible)
        viewMenu.addAction(self.inspectorAction)
        self.setInspectorVisible(self.inspectorAction.isChecked())

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

    # Pages and panels

    @Slot(int)
    def setPage(self, index: int):
        index = min(max(int(index), 0), self.stack.count() - 1)
        self.stack.setCurrentIndex(index)
        self.navigation.setCurrentIndex(index)
        if hasattr(self, 'pageActions'):
            self.pageActions[index].setChecked(True)

    @Slot(bool)
    def setInspectorVisible(self, visible: bool):
        for page in (self.spectraPage, self.wavefunctionPage):
            page.inspector.setVisible(visible)

    @Slot(str)
    def setTheme(self, mode: str):
        self.theme.setMode(mode)
        if hasattr(self, 'themeActions'):
            self.themeActions[self.theme.mode].setChecked(True)

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
            action.triggered.connect(lambda checked=False, dataset=dataset: self.openDataset(dataset))
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
                                f'{dataset["save"]}\n\nYou can choose it on the System page.')
        self.openDataset(dataset)

    def openDataset(self, dataset):
        # Keep the parameters of the dataset being left
        self.storeDatasetState()
        # Saving now must not overwrite the session of another setup
        self.sessionPath = None

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
            self.options.setQPDir(dataset['qp'])

        # The Q-path last set on this dataset, if any
        qPath = dataset.get('qPath')
        if qPath:
            if self.systemPage.restoreQPath(qPath):
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
            parts.append(f'{self.options.nQpoints} Q-points')
        self.datasetLabel.setText('  ·  '.join(parts))
        title = [Path(self.sessionPath).stem] if self.sessionPath else []
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
            action.triggered.connect(lambda checked=False, path=path: self.openSession(path))
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
            'page': self.stack.currentIndex(),
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
        note = '' if manifest['results'] or not self.sessionResultsAction.isChecked() else ' (no results to store)'
        if self.calculations.isBusy():
            note += '; the calculation still running is not included'
        self.statusBar().showMessage(f'Session saved to {path} ({Path(path).stat().st_size / 2**20:.1f} MB){note}', 8000)

    @Slot()
    def chooseSession(self):
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
                    message += ' with its results'
                except Exception as error:   # a session from an incompatible version, or damaged
                    message += f'; its results could not be shown ({error})'
            else:
                message += '; its results were not shown: the dataset changed since it was saved'
        self.setPage(int(manifest.get('page', self.stack.currentIndex())))

        self.sessionPath = str(Path(path).resolve())
        self.settings.setValue('sessionDir', str(Path(path).resolve().parent))
        self.addRecentSession(path)
        self.updateDatasetLabel()
        self.statusBar().showMessage(message, 10000)

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
        self.wavefunctionPage.parameters3DWidget.exportDensityButton.setEnabled(False)

    @Slot()
    def exportImage(self):
        # The view must have been shown to be rendered
        self.setPage(WAVEFUNCTION_PAGE)
        QApplication.processEvents()
        view = self.wavefunctionPage.excitonWfWidget
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
        # Stop the calculations; the running one ends at its next progress check
        self.calculations.cancel()
        self.calculations.tasks.waitForDone(10000)
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('page', self.stack.currentIndex())
        self.settings.setValue('theme', self.theme.mode)
        self.settings.setValue('showInspector', self.inspectorAction.isChecked())
        self.settings.setValue('state', json.dumps(self.state.values(GLOBAL)))
        self.storeDatasetState()
        super().closeEvent(event)
