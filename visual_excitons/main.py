# This Python file uses the following encoding: utf-8
import sys
from PySide6.QtWidgets import QApplication

from gui.main_widget import MainWidget

if __name__ == "__main__":
    app = QApplication(sys.argv)

    mainWidget = MainWidget()
    mainWidget.resize(1920, 1080)
    mainWidget.show()

    sys.exit(app.exec())
