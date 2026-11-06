"""
Vertical navigation bar on the left of the main window, one button per page.

Icons are drawn with QPainter in the palette's text color, so they follow the
theme and need no image files.
"""

import math

from PySide6.QtCore import Qt, Signal, QPointF, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QPainterPath, QColor, QPalette
from PySide6.QtWidgets import QWidget, QToolButton, QVBoxLayout, QButtonGroup, QSizePolicy, QApplication

from .theme import themeManager


ICON_SIZE = 28


def _drawCrystal(p: QPainter, s: float):
    # A cube in oblique projection with an atom at each visible corner
    a, d = 0.52 * s, 0.22 * s
    x0, y0 = 0.14 * s, 0.32 * s
    front = [QPointF(x0, y0), QPointF(x0 + a, y0), QPointF(x0 + a, y0 + a), QPointF(x0, y0 + a)]
    back = [pt + QPointF(d, -d) for pt in front]
    for i in range(4):
        p.drawLine(front[i], front[(i + 1) % 4])
        p.drawLine(back[i], back[(i + 1) % 4])
        p.drawLine(front[i], back[i])
    r = 0.07 * s
    p.save()
    p.setBrush(p.pen().color())
    for pt in front + back[:3]:
        p.drawEllipse(pt, r, r)
    p.restore()


def _drawSpectrum(p: QPainter, s: float):
    # Axes and an absorption spectrum with two peaks
    m = 0.14 * s
    p.drawLine(QPointF(m, m), QPointF(m, s - m))
    p.drawLine(QPointF(m, s - m), QPointF(s - m, s - m))
    path = QPainterPath()
    n = 60
    for k in range(n + 1):
        t = k / n
        y = 0.75 * math.exp(-((t - 0.32) / 0.07) ** 2) + 0.45 * math.exp(-((t - 0.68) / 0.1) ** 2)
        pt = QPointF(m + t * (s - 2 * m), s - m - 0.04 * s - y * (s - 2.6 * m))
        path.moveTo(pt) if k == 0 else path.lineTo(pt)
    p.drawPath(path)


def _drawOrbital(p: QPainter, s: float):
    # Nested isosurfaces around a fixed particle
    c = QPointF(0.5 * s, 0.5 * s)
    for rx, ry in ((0.40, 0.28), (0.27, 0.18), (0.13, 0.09)):
        p.drawEllipse(c, rx * s, ry * s)
    p.save()
    p.setBrush(p.pen().color())
    p.drawEllipse(c, 0.04 * s, 0.04 * s)
    p.restore()


ICON_PAINTERS = {'crystal': _drawCrystal, 'spectrum': _drawSpectrum, 'orbital': _drawOrbital}


def navigationIcon(name: str, color: QColor, size: int = ICON_SIZE, scale: float = 2.0) -> QIcon:
    pixmap = QPixmap(int(size * scale), int(size * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    ICON_PAINTERS[name](p, float(size))
    p.end()
    return QIcon(pixmap)


class NavigationBar(QWidget):
    pageSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.idClicked.connect(self.pageSelected)

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(4, 8, 4, 8)
        self.layout_.setSpacing(4)
        self.layout_.addStretch(1)

        self.buttons = []
        self.refreshTheme()
        themeManager().themeChanged.connect(self.refreshTheme)

    def addPage(self, text: str, iconName: str, toolTip: str = ''):
        button = QToolButton()
        button.setText(text)
        button.setToolTip(toolTip)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setFixedWidth(84)
        button.setMinimumHeight(64)
        button.iconName = iconName
        self.group.addButton(button, len(self.buttons))
        self.layout_.insertWidget(len(self.buttons), button)
        self.buttons.append(button)
        self._updateIcons()
        return button

    def setCurrentIndex(self, index: int):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def refreshTheme(self, *args):
        self._applyColors()
        self._updateIcons()

    def _applyColors(self):
        # Slightly darker than the window, like a side bar
        palette = QPalette(QApplication.palette())
        window = palette.color(QPalette.ColorRole.Window)
        palette.setColor(QPalette.ColorRole.Window, window.darker(112) if window.lightness() > 128 else window.darker(125))
        self.setPalette(palette)

    def _updateIcons(self):
        color = QApplication.palette().color(QPalette.ColorRole.WindowText)
        for button in self.buttons:
            button.setIcon(navigationIcon(button.iconName, color))
