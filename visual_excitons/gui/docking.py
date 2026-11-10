"""
Dockable panels, with the Qt Advanced Docking System (PySide6-QtAds).

Every view and control panel of the main window is a dock: it can be placed
next to any other, tabbed with it, floated in its own window or closed (and
reopened from View › Panels). Preset layouts arrange them for each step of the
workflow (System, Spectra, Wave function) or show everything (Overview); the
user can save their own layouts too, by name.

The arrangement is kept between restarts (`saveState`), as are the user's
layouts (`saveLayouts`); they are preferences, not part of session files.
"""

from PySide6.QtCore import QObject, Signal, QTimer, QEvent
from PySide6.QtGui import QPalette, QColor, QAction, QIcon
from PySide6.QtWidgets import QScrollArea, QFrame, QWidget, QApplication
import PySide6QtAds as ads

# Dock keys (their object names, used in the saved state) and titles
PANELS = {
    'system': 'System',
    'dispersion': 'Dispersion',
    'absorption': 'Absorption',
    'bands': 'Band structure',
    'wavefunction': 'Wave function',
    'analysis': 'Analysis',
    'spectraControls': 'Spectra controls',
    'appearance': 'Appearance',
    'wavefunctionControls': 'Wave function controls',
}

LEFT, RIGHT, TOP, BOTTOM, CENTER = (ads.LeftDockWidgetArea, ads.RightDockWidgetArea, ads.TopDockWidgetArea,
                                    ads.BottomDockWidgetArea, ads.CenterDockWidgetArea)
TAB = 'tab'

# Preset layouts. Each step places a dock: (key, where, relative to), where is
# an area relative to the dock area of the other dock (or of the whole window if
# None), or TAB to add it as a tab there. The first tab placed in an area is
# shown. `sizes` gives the shares of the splitter that holds a dock's area, in
# the order of its widgets. Docks not placed are closed (as hidden tabs, so
# that they reopen next to a related panel).
PRESETS = {
    'System': {
        'steps': [('system', CENTER, None)],
        'sizes': [],
    },
    'Spectra': {
        'steps': [('dispersion', CENTER, None),
                  ('absorption', RIGHT, 'dispersion'),
                  ('bands', BOTTOM, 'dispersion'),
                  ('spectraControls', RIGHT, None),
                  ('appearance', TAB, 'spectraControls')],
        'sizes': [('spectraControls', [0.78, 0.22]), ('absorption', [0.5, 0.5])],
    },
    'Wave function': {
        'steps': [('wavefunction', CENTER, None),
                  ('analysis', BOTTOM, 'wavefunction'),
                  ('wavefunctionControls', RIGHT, None)],
        'sizes': [('wavefunctionControls', [0.78, 0.22]), ('analysis', [0.6, 0.4])],
    },
    'Overview': {
        'steps': [('wavefunction', CENTER, None),
                  ('dispersion', LEFT, None),
                  ('bands', TAB, 'dispersion'),
                  ('absorption', BOTTOM, 'dispersion'),
                  ('analysis', BOTTOM, 'wavefunction'),
                  ('spectraControls', RIGHT, None),
                  ('appearance', TAB, 'spectraControls'),
                  ('wavefunctionControls', TAB, 'spectraControls'),
                  ('system', TAB, 'spectraControls')],
        'sizes': [('spectraControls', [0.32, 0.46, 0.22]), ('absorption', [0.5, 0.5]), ('analysis', [0.6, 0.4])],
    },
}

# Where a dock left out of a preset is put (closed), by order of preference
CLOSED_NEIGHBOURS = {
    'system': ['spectraControls', 'wavefunctionControls'],
    'dispersion': ['absorption', 'bands', 'wavefunction'],
    'absorption': ['dispersion', 'bands', 'wavefunction'],
    'bands': ['dispersion', 'absorption', 'wavefunction'],
    'wavefunction': ['dispersion', 'absorption', 'system'],
    'analysis': ['wavefunction', 'absorption', 'system'],
    'spectraControls': ['wavefunctionControls', 'system'],
    'appearance': ['spectraControls', 'wavefunctionControls', 'system'],
    'wavefunctionControls': ['spectraControls', 'system'],
}

DEFAULT_PRESET = 'Overview'


def mixColors(a: QColor, b: QColor, t: float) -> str:
    """The color a fraction `t` of the way from `a` to `b`, as #rrggbb."""
    return QColor(round(a.red() + t * (b.red() - a.red())), round(a.green() + t * (b.green() - a.green())),
                  round(a.blue() + t * (b.blue() - a.blue()))).name()


def tabStyleSheet(palette: QPalette) -> str:
    """
    Colors of the dock tabs for `palette`. QtAds's own stylesheet takes them
    from the palette when it is first applied, and keeps them after a theme
    change: on a dark theme, the titles of the tabs behind ended up almost
    black on dark grey.
    """
    text, window = palette.color(QPalette.ColorRole.WindowText), palette.color(QPalette.ColorRole.Window)
    return f"""
ads--CDockWidgetTab {{ background: {window.name()}; border-color: {mixColors(window, text, 0.15)}; }}
ads--CDockWidgetTab[activeTab="true"] {{ background: {mixColors(window, text, 0.12)}; }}
ads--CDockWidgetTab QLabel {{ color: {mixColors(window, text, 0.75)}; }}
ads--CDockWidgetTab[activeTab="true"] QLabel {{ color: {text.name()}; }}
"""


def scrollable(widget: QWidget) -> QScrollArea:
    """`widget` in a frameless scroll area, for forms that can be docked in a small space."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area


def attachIcon() -> QIcon:
    """QtAds's own detach icon (two windows), in its version for the current theme."""
    dark = QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
    suffix = '_dark' if dark else ''
    icon = QIcon(f':/ads/images/detach-button{suffix}.svg')
    icon.addFile(f':/ads/images/detach-button-disabled{suffix}.svg', mode=QIcon.Mode.Disabled)
    return icon


def side(fromRect, toRect):
    """Where `toRect` lies relative to `fromRect`: LEFT, RIGHT, TOP or BOTTOM."""
    dx = toRect.center().x() - fromRect.center().x()
    dy = toRect.center().y() - fromRect.center().y()
    if abs(dx) * fromRect.height() >= abs(dy) * fromRect.width():
        return RIGHT if dx > 0 else LEFT
    return BOTTOM if dy > 0 else TOP


class Panels(QObject):
    """The dock manager of the main window and its docks, presets and saved layouts."""

    # Docks shown or hidden by the user (not while a layout is being applied)
    panelToggled = Signal(str, bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        ads.CDockManager.setConfigFlag(ads.CDockManager.eConfigFlag.FocusHighlighting, False)
        self.manager = ads.CDockManager(window)
        self.baseStyleSheet = self.manager.styleSheet()
        self.docks = {}
        self.arranging = False
        # Where each dock was last docked, for Attach: the docks it was a tab
        # with, and the dock next to its area with the side it was on. Updated
        # after every change of layout (any mouse release, presets, restores)
        self.homes = {}
        self.extraTitleBarActions = {}
        self.attachActions = {}
        self.homesTimer = QTimer(self)
        self.homesTimer.setSingleShot(True)
        self.homesTimer.setInterval(0)
        self.homesTimer.timeout.connect(self.recordHomes)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonRelease:
            self.homesTimer.start()   # a drag may have moved a dock
        return False

    def applyTheme(self, *args):
        """Tab colors for the current palette (call after each theme change)."""
        styleSheet = self.baseStyleSheet + tabStyleSheet(QApplication.palette())
        self.manager.setStyleSheet(styleSheet)
        for action in self.attachActions.values():
            action.setIcon(attachIcon())
        for container in self.manager.floatingWidgets():
            if container.styleSheet():
                container.setStyleSheet(styleSheet)

    def add(self, key: str, widget: QWidget) -> ads.CDockWidget:
        dock = ads.CDockWidget(self.manager, PANELS[key])
        dock.setObjectName(key)
        dock.setWidget(widget)
        # Its own minimum size (e.g. the controls, never narrower than their
        # widest section), not that of the dock's tab
        dock.setMinimumSizeHintMode(ads.CDockWidget.eMinimumSizeHintMode.MinimumSizeHintFromContent)
        dock.viewToggled.connect(lambda shown, key=key: self.arranging or self.panelToggled.emit(key, shown))
        self.docks[key] = dock
        # Back into the main window, from its floating window
        action = QAction(attachIcon(), 'Attach', self)
        action.setToolTip('Put the panel back into the main window, where it was')
        action.triggered.connect(lambda checked=False, key=key: self.attach(key))
        self.attachActions[key] = action
        dock.topLevelChanged.connect(lambda floating: self.updateAttachActions())
        # Until a layout is applied: all in one area, so that every dock belongs
        # to the manager
        first = next(iter(self.docks.values()))
        if dock is first:
            self.manager.addDockWidget(CENTER, dock)
        else:
            self.manager.addDockWidgetTabToArea(dock, first.dockAreaWidget())
        return dock

    def setTitleBarActions(self, key, actions):
        """Actions in the title bar of a dock (followed by Attach while it floats)."""
        self.extraTitleBarActions[key] = list(actions)
        self.updateTitleBarActions(key, force=True)

    def updateTitleBarActions(self, key, force=False):
        # QtAds shows the actions of a dock whether visible or not: Attach is
        # only given to floating docks
        dock = self.docks[key]
        actions = self.extraTitleBarActions.get(key, []) + ([self.attachActions[key]] if self.isFloating(key) else [])
        if not force and dock.titleBarActions() == actions:
            return
        dock.setTitleBarActions(actions)
        area = dock.dockAreaWidget()
        if area is not None:
            area.titleBar().updateDockWidgetActionsButtons()

    # Floating docks back into the main window

    def isFloating(self, key):
        dock = self.docks[key]
        return dock.isFloating() or dock.isInFloatingContainer()

    def isDocked(self, key):
        """Open in the main window."""
        return not self.docks[key].isClosed() and not self.isFloating(key) and self.docks[key].dockAreaWidget() is not None

    def updateAttachActions(self):
        for key in self.docks:
            self.updateTitleBarActions(key)

    def recordHomes(self):
        """Note where each dock open in the main window is (see homes)."""
        self.updateAttachActions()
        docked = [key for key in self.docks if self.isDocked(key)]
        areas = {key: self.docks[key].dockAreaWidget() for key in docked}
        rects = {}
        for key, area in areas.items():
            topLeft = area.mapTo(self.window, area.rect().topLeft())
            rects[key] = area.rect().translated(topLeft)
        for key in docked:
            area = areas[key]
            tabs = [other for other in docked if other != key and areas[other] is area]
            neighbour, where = None, None
            others = [other for other in docked if areas[other] is not area]
            if others:
                center = rects[key].center()
                nearest = min(others, key=lambda other: (rects[other].center() - center).manhattanLength())
                neighbour, where = nearest, side(rects[nearest], rects[key])
            self.homes[key] = {'tabs': tabs, 'neighbour': neighbour, 'side': int(where.value) if where else None}

    def attach(self, key):
        """Put a floating dock back where it was in the main window (or next to a related one)."""
        if not self.isFloating(key):
            return
        dock = self.docks[key]
        home = self.homes.get(key, {})
        tab = next((other for other in home.get('tabs', []) if other in self.docks and self.isDocked(other)), None)
        neighbour = home.get('neighbour')
        if tab is not None:
            self.manager.addDockWidgetTabToArea(dock, self.docks[tab].dockAreaWidget())
        elif neighbour in self.docks and self.isDocked(neighbour) and home.get('side') is not None:
            self.manager.addDockWidget(ads.DockWidgetArea(home['side']), dock, self.docks[neighbour].dockAreaWidget())
        else:
            related = next((other for other in CLOSED_NEIGHBOURS.get(key, []) if self.isDocked(other)), None)
            if related is not None:
                self.manager.addDockWidgetTabToArea(dock, self.docks[related].dockAreaWidget())
            else:
                self.manager.addDockWidget(RIGHT, dock)
        dock.setAsCurrentTab()
        self.recordHomes()

    def attachAll(self):
        for key in list(self.docks):
            self.attach(key)

    def floatingKeys(self):
        return [key for key in self.docks if not self.docks[key].isClosed() and self.isFloating(key)]

    def toggleActions(self):
        """Actions that show or hide each dock, in the order of PANELS."""
        return [self.docks[key].toggleViewAction() for key in PANELS if key in self.docks]

    def isShown(self, key):
        return not self.docks[key].isClosed()

    def show(self, key):
        """Open the dock if closed and bring it to the front."""
        dock = self.docks[key]
        if dock.isClosed():
            dock.toggleView(True)
        dock.setAsCurrentTab()
        if dock.isFloating() or dock.isInFloatingContainer():
            dock.window().raise_()
            dock.window().activateWindow()

    def setShown(self, key, shown):
        dock = self.docks[key]
        if dock.isClosed() == shown:
            dock.toggleView(shown)

    # Layouts

    def applyPreset(self, name: str, closed=()):
        """
        Arrange the docks as in preset `name`. Docks in `closed` are put in
        their place but closed (e.g. the analysis when it is off), so that they
        open there.
        """
        preset = PRESETS[name]
        steps = preset['steps']
        self.arranging = True
        try:
            for dock in self.docks.values():
                self.manager.removeDockWidget(dock)
            placed = {}
            for key, where, relativeTo in steps:
                dock = self.docks[key]
                target = placed[relativeTo].dockAreaWidget() if relativeTo else None
                if where == TAB:
                    self.manager.addDockWidgetTabToArea(dock, target)
                else:
                    self.manager.addDockWidget(where, dock, target)
                if dock.isClosed():
                    dock.toggleView(True)
                placed[key] = dock
            # The first tab of each area in front
            for key, where, relativeTo in steps:
                if where != TAB and any(w == TAB and r == key for k, w, r in steps):
                    placed[key].setAsCurrentTab()
            # The other docks: closed, next to a related one
            for key, dock in self.docks.items():
                if key in placed:
                    continue
                neighbour = next((placed[k] for k in CLOSED_NEIGHBOURS[key] if k in placed), next(iter(placed.values())))
                self.manager.addDockWidgetTabToArea(dock, neighbour.dockAreaWidget())
                dock.toggleView(False)
                neighbour.setAsCurrentTab()
            for key in closed:
                if key in placed:
                    placed[key].toggleView(False)
        finally:
            self.arranging = False
        sizes = [(key, shares) for key, shares in preset['sizes'] if key in placed]
        self.setShares(sizes)
        # Once laid out, when the window was not shown yet
        QTimer.singleShot(0, lambda: self.setShares(sizes))
        self.homesTimer.start()

    def setShares(self, sizes):
        for key, shares in sizes:
            area = self.docks[key].dockAreaWidget()
            if area is None:
                continue
            current = self.manager.splitterSizes(area)
            if len(current) != len(shares):
                continue
            total = sum(current) or self.window.width()
            self.manager.setSplitterSizes(area, [max(1, round(share * total)) for share in shares])

    def closeFloatingWindows(self):
        """
        Close the windows of the floating docks, when the main window closes
        (after saving the state, which has them): they are windows of their
        own, and the application only quits once no window is left open.
        """
        self.arranging = True
        try:
            for container in self.manager.floatingWidgets():
                container.close()
        finally:
            self.arranging = False

    def saveState(self) -> bytes:
        return bytes(self.manager.saveState())

    def restoreState(self, state) -> bool:
        """Restore a saved arrangement; False (and nothing changed) if it is not valid."""
        if not state:
            return False
        self.arranging = True
        try:
            return bool(self.manager.restoreState(state))
        finally:
            self.arranging = False
            self.homesTimer.start()

    # The user's layouts

    def layoutNames(self):
        return sorted(self.manager.perspectiveNames(), key=str.lower)

    def saveLayout(self, name):
        self.manager.addPerspective(name)

    def openLayout(self, name):
        self.arranging = True
        try:
            self.manager.openPerspective(name)
        finally:
            self.arranging = False
            self.homesTimer.start()

    def removeLayout(self, name):
        self.manager.removePerspective(name)

    def saveLayouts(self, settings):
        settings.beginGroup('layouts')
        settings.remove('')
        self.manager.savePerspectives(settings)
        settings.endGroup()

    def loadLayouts(self, settings):
        settings.beginGroup('layouts')
        self.manager.loadPerspectives(settings)
        settings.endGroup()
