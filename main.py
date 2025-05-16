# This Python file uses the following encoding: utf-8
import sys
from PySide6.QtWidgets import QApplication
from main_widget import MainWidget

if __name__ == "__main__":
    app = QApplication(sys.argv)

    mainWidget = MainWidget()
    mainWidget.resize(1600, 1000)
    mainWidget.show()

    sys.exit(app.exec())
