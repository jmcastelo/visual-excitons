"""
Side panel of collapsible sections, shared by all pages.

Each section has a clickable header with an arrow and shows or hides its
contents. The panel scrolls when the open sections do not fit, and the labels
of all its forms share one column width so fields line up across sections.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (QWidget, QToolButton, QVBoxLayout, QScrollArea, QFrame, QFormLayout, QLabel,
                               QSizePolicy, QHBoxLayout, QSlider, QApplication, QSplitter)

from .theme import themeManager
from .persistence import PersistentState, GLOBAL


class CollapsibleSection(QWidget):
    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)

        self.expanded = expanded

        self.header = QToolButton()
        self.header.setText(title)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.setAutoRaise(True)
        font = QFont(self.header.font())
        font.setBold(True)
        self.header.setFont(font)
        self.header.clicked.connect(lambda: self.setExpanded(not self.expanded))

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)

        self.content = QWidget()
        self.content.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.header)
        layout.addWidget(line)
        layout.addWidget(self.content)

    def setContentLayout(self, layout):
        layout.setContentsMargins(14, 6, 4, 10)
        self.content.setLayout(layout)

    def isExpanded(self):
        return self.expanded

    def setExpanded(self, expanded: bool):
        self.expanded = expanded
        self.header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)
        self.toggled.emit(expanded)


class Inspector(QScrollArea):
    """Scrollable column of CollapsibleSections."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.body = QWidget()
        self.bodyLayout = QVBoxLayout(self.body)
        self.bodyLayout.setContentsMargins(8, 4, 8, 8)
        self.bodyLayout.setSpacing(6)
        self.bodyLayout.addStretch(1)
        self.setWidget(self.body)

        self.sections = {}
        # Values kept between sessions (see persistence.py)
        self.persistence = PersistentState()

    def addSection(self, title: str, layout, expanded: bool = True) -> CollapsibleSection:
        section = CollapsibleSection(title, expanded)
        section.setContentLayout(layout)
        self.bodyLayout.insertWidget(self.bodyLayout.count() - 1, section)
        self.sections[title] = section
        # Which sections are open
        self.persistence.remember(f'section/{title}', section)
        return section

    def remember(self, key, widget=None, scope=GLOBAL, get=None, set=None):
        self.persistence.remember(key, widget, scope, get, set)

    def alignLabels(self):
        """Give the labels of all form layouts the width of the widest one."""
        labels = []
        for section in self.sections.values():
            for form in section.content.findChildren(QFormLayout) + [section.content.layout()]:
                if not isinstance(form, QFormLayout):
                    continue
                for row in range(form.rowCount()):
                    item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                    if item is not None and isinstance(item.widget(), QLabel):
                        labels.append(item.widget())
        if labels:
            width = max(label.sizeHint().width() for label in labels)
            for label in labels:
                label.setMinimumWidth(width)


INSPECTOR_WIDTH = 360


def pageLayout(view: QWidget, inspector: QWidget) -> QHBoxLayout:
    """
    Layout of a page: its main view, resizable against the inspector on its
    right, without margins (the main window frames the page).
    """
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(view)
    splitter.addWidget(inspector)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 0)
    splitter.setCollapsible(0, False)
    inspector.setMinimumWidth(260)
    splitter.setSizes([10 * INSPECTOR_WIDTH, INSPECTOR_WIDTH])

    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(splitter)
    return layout


def formLayout() -> QFormLayout:
    """Form layout with the conventions of the inspector."""
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
    form.setVerticalSpacing(6)
    return form


class ValueSlider(QWidget):
    """Horizontal slider with its current value shown beside it."""

    valueChanged = Signal(int)

    def __init__(self, minimum, maximum, value, formatter, parent=None):
        super().__init__(parent)
        self.formatter = formatter

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(int(value))

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.label.setMinimumWidth(self.label.fontMetrics().horizontalAdvance('0.000') + 4)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.label)

        self.slider.valueChanged.connect(self._onValueChanged)
        self._updateLabel(self.slider.value())

    def _updateLabel(self, value):
        self.label.setText(self.formatter(value))

    def _onValueChanged(self, value):
        self._updateLabel(value)
        self.valueChanged.emit(value)

    def setToolTip(self, text):
        super().setToolTip(text)
        self.slider.setToolTip(text)


class NoteLabel(QLabel):
    """
    Small grey explanatory text, word-wrapped, that always gets the height its
    text needs at its current width (QFormLayout does not ask labels for their
    height for a given width, so a plain wrapped QLabel gets clipped), and that
    follows the theme.
    """

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 0.92)
        self.setFont(font)
        self._applyColor()
        themeManager().themeChanged.connect(self._applyColor)

    def _applyColor(self, *args):
        # Between the text and window colors, readable on both themes
        palette = QApplication.palette()
        text, window = palette.color(QPalette.ColorRole.WindowText), palette.color(QPalette.ColorRole.Window)
        color = QColor((2 * text.red() + window.red()) // 3, (2 * text.green() + window.green()) // 3,
                       (2 * text.blue() + window.blue()) // 3)
        self.setStyleSheet(f'color: {color.name()}')

    def _fitHeight(self):
        height = self.heightForWidth(self.width())
        if height > 0 and height != self.minimumHeight():
            self.setMinimumHeight(height)

    def setText(self, text):
        super().setText(text)
        self._fitHeight()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fitHeight()
