"""
The start page: shown over the panels while no dataset is open (on start, and
after File › New session), with buttons to open a dataset or a session and
the recent ones.
"""

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QCommandLinkButton, QVBoxLayout, QHBoxLayout,
                               QGridLayout, QScrollArea, QSizePolicy)


class StartPage(QScrollArea):
    openDatasetRequested = Signal()
    openSessionRequested = Signal()
    datasetChosen = Signal(dict)
    sessionChosen = Signal(str)

    def __init__(self, window):
        """Over the central widget (the panels) of main window `window`, following its geometry."""
        super().__init__(window)
        self.mainWindow = window
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # The content wraps: scrolled only vertically, on small windows
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The window's color, following the theme
        self.setBackgroundRole(QPalette.ColorRole.Window)
        self.setAutoFillBackground(True)

        content = QWidget()
        content.setBackgroundRole(QPalette.ColorRole.Window)
        content.setAutoFillBackground(True)

        title = QLabel('Visual Excitons')
        font = QFont(title.font())
        font.setPointSizeF(font.pointSizeF() * 2.2)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitle = QLabel('Explore the excitons computed with Yambo: open a dataset (the folder of a calculation) '
                          'or a session saved before.')
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.openDatasetButton = QPushButton('Open dataset…')
        self.openDatasetButton.setToolTip('Open the folder of a calculation; its SAVE, BSE and GW directories are '
                                          'found automatically')
        self.openDatasetButton.clicked.connect(self.openDatasetRequested)
        self.openSessionButton = QPushButton('Open session…')
        self.openSessionButton.setToolTip('Open a session file: its dataset, parameters, view and results')
        self.openSessionButton.clicked.connect(self.openSessionRequested)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for button in (self.openDatasetButton, self.openSessionButton):
            button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button)
        buttons.addStretch(1)

        # The recent sessions and datasets, side by side
        self.sessionsLayout, self.sessionsEmpty = QVBoxLayout(), QLabel('No sessions yet.')
        self.datasetsLayout, self.datasetsEmpty = QVBoxLayout(), QLabel('No datasets yet.')
        recent = QGridLayout()
        recent.setHorizontalSpacing(32)
        for column, (text, layout, empty) in enumerate((('Recent sessions', self.sessionsLayout, self.sessionsEmpty),
                                                       ('Recent datasets', self.datasetsLayout, self.datasetsEmpty))):
            heading = QLabel(text)
            headingFont = QFont(heading.font())
            headingFont.setBold(True)
            headingFont.setPointSizeF(headingFont.pointSizeF() * 1.2)
            heading.setFont(headingFont)
            empty.setEnabled(False)
            layout.setSpacing(0)
            layout.addWidget(empty, 0, Qt.AlignmentFlag.AlignHCenter)
            recent.addWidget(heading, 0, column, Qt.AlignmentFlag.AlignHCenter)
            recent.addLayout(layout, 1, column, Qt.AlignmentFlag.AlignTop)
            recent.setColumnStretch(column, 1)

        column = QVBoxLayout()
        column.setSpacing(12)
        column.addStretch(1)
        column.addWidget(title)
        column.addWidget(subtitle)
        column.addLayout(buttons)
        column.addSpacing(16)
        column.addLayout(recent)
        column.addStretch(1)

        # Centred, not wider than easy to read
        frame = QWidget()
        frame.setMaximumWidth(900)
        frame.setLayout(column)
        outer = QHBoxLayout(content)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        outer.addWidget(frame, 8)
        outer.addStretch(1)
        self.setWidget(content)

        self.sessionLinks, self.datasetLinks = [], []
        window.installEventFilter(self)
        self.place()

    def eventFilter(self, watched, event):
        if watched is self.mainWindow and event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.Show):
            self.place()
        return False

    def place(self):
        """Over the central widget, above it."""
        central = self.mainWindow.centralWidget()
        if central is not None:
            self.setGeometry(central.geometry())
        self.raise_()

    def showEvent(self, event):
        self.place()
        super().showEvent(event)

    @staticmethod
    def fill(layout, empty, links, items, chosen):
        """`items`: (title, description, enabled, value) of each link; `chosen` is emitted with its value."""
        for link in links:
            layout.removeWidget(link)
            link.deleteLater()
        links.clear()
        for title, description, enabled, value in items:
            link = QCommandLinkButton(title, description)
            link.setToolTip(description if enabled else f'{description} (not found)')
            link.setEnabled(enabled)
            link.clicked.connect(lambda checked=False, value=value: chosen.emit(value))
            layout.addWidget(link)
            links.append(link)
        empty.setVisible(not items)

    def setRecentSessions(self, items):
        self.fill(self.sessionsLayout, self.sessionsEmpty, self.sessionLinks, items, self.sessionChosen)

    def setRecentDatasets(self, items):
        self.fill(self.datasetsLayout, self.datasetsEmpty, self.datasetLinks, items, self.datasetChosen)
