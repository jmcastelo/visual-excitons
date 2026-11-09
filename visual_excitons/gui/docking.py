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

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QPalette, QColor
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
                  ('spectraControls', RIGHT, None)],
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

    def applyTheme(self, *args):
        """Tab colors for the current palette (call after each theme change)."""
        styleSheet = self.baseStyleSheet + tabStyleSheet(QApplication.palette())
        self.manager.setStyleSheet(styleSheet)
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
        # Until a layout is applied: all in one area, so that every dock belongs
        # to the manager
        first = next(iter(self.docks.values()))
        if dock is first:
            self.manager.addDockWidget(CENTER, dock)
        else:
            self.manager.addDockWidgetTabToArea(dock, first.dockAreaWidget())
        return dock

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
