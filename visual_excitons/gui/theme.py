"""
Application theme: the system's own look, or a light or dark Fusion theme.

The plots follow the effective theme (see ThemeManager.isDark), so they never
glare against a dark interface or vanish against a light one.
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory
import pyqtgraph as pg


THEME_MODES = ('System', 'Light', 'Dark')

# Plot colors per theme: foreground (axes, ticks, text) and background
PLOT_COLORS = {
    False: {'foreground': QColor(20, 20, 20), 'background': QColor(255, 255, 255)},
    True: {'foreground': QColor(220, 222, 226), 'background': QColor(30, 31, 34)},
}


def _palette(dark: bool) -> QPalette:
    if dark:
        window, base, alternate = QColor(43, 45, 48), QColor(30, 31, 34), QColor(38, 40, 43)
        text, disabledText = QColor(223, 225, 229), QColor(120, 123, 128)
        button, highlight, link = QColor(55, 57, 61), QColor(53, 116, 240), QColor(110, 160, 255)
        light, mid, dark_, shadow = QColor(70, 72, 76), QColor(50, 52, 56), QColor(25, 26, 28), QColor(10, 10, 10)
    else:
        window, base, alternate = QColor(239, 240, 242), QColor(255, 255, 255), QColor(246, 247, 248)
        text, disabledText = QColor(28, 29, 31), QColor(150, 152, 156)
        button, highlight, link = QColor(248, 249, 250), QColor(41, 98, 218), QColor(30, 90, 200)
        light, mid, dark_, shadow = QColor(255, 255, 255), QColor(200, 202, 206), QColor(160, 162, 166), QColor(90, 90, 90)

    p = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        disabled = group == QPalette.ColorGroup.Disabled
        foreground = disabledText if disabled else text
        p.setColor(group, QPalette.ColorRole.Window, window)
        p.setColor(group, QPalette.ColorRole.WindowText, foreground)
        p.setColor(group, QPalette.ColorRole.Base, base)
        p.setColor(group, QPalette.ColorRole.AlternateBase, alternate)
        p.setColor(group, QPalette.ColorRole.ToolTipBase, base)
        p.setColor(group, QPalette.ColorRole.ToolTipText, text)
        p.setColor(group, QPalette.ColorRole.PlaceholderText, disabledText)
        p.setColor(group, QPalette.ColorRole.Text, foreground)
        p.setColor(group, QPalette.ColorRole.Button, button)
        p.setColor(group, QPalette.ColorRole.ButtonText, foreground)
        p.setColor(group, QPalette.ColorRole.BrightText, QColor(255, 80, 80))
        p.setColor(group, QPalette.ColorRole.Highlight, mid if disabled else highlight)
        p.setColor(group, QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        p.setColor(group, QPalette.ColorRole.Link, link)
        p.setColor(group, QPalette.ColorRole.Light, light)
        p.setColor(group, QPalette.ColorRole.Midlight, light)
        p.setColor(group, QPalette.ColorRole.Mid, mid)
        p.setColor(group, QPalette.ColorRole.Dark, dark_)
        p.setColor(group, QPalette.ColorRole.Shadow, shadow)
    return p


class ThemeManager(QObject):
    """Applies a theme mode to the application and tells the plots about it."""

    # Emitted with True when the effective theme is dark
    themeChanged = Signal(bool)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        # The system look, restored by the 'System' mode
        self.systemStyle = app.style().name()
        self.systemPalette = QPalette(app.palette())
        self.mode = 'System'

    def setMode(self, mode: str):
        if mode not in THEME_MODES:
            mode = 'System'
        self.mode = mode

        if mode == 'System':
            self.app.setStyle(QStyleFactory.create(self.systemStyle))
            self.app.setPalette(self.systemPalette)
        else:
            self.app.setStyle(QStyleFactory.create('Fusion'))
            self.app.setPalette(_palette(mode == 'Dark'))

        dark = self.isDark()
        colors = PLOT_COLORS[dark]
        # Defaults for plot items created from now on
        pg.setConfigOption('foreground', colors['foreground'])
        pg.setConfigOption('background', colors['background'])
        self.themeChanged.emit(dark)

    def isDark(self) -> bool:
        return self.app.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def plotColors(self):
        return PLOT_COLORS[self.isDark()]


_manager = None


def themeManager() -> ThemeManager:
    """The application's theme manager, created on first use."""
    global _manager
    if _manager is None:
        _manager = ThemeManager(QApplication.instance())
    return _manager


def plotForeground() -> QColor:
    """Color for plot text and lines that must contrast with the plot background."""
    return QColor(themeManager().plotColors()['foreground'])
