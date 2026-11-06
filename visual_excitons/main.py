# This Python file uses the following encoding: utf-8
import sys
from pathlib import Path

# Make `visual_excitons` importable however this script is started
# (python visual_excitons/main.py, an IDE, ...)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtWidgets import QApplication

from visual_excitons.gui.main_window import MainWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName('Visual Excitons')
    app.setOrganizationName('VisualExcitons')

    mainWindow = MainWindow()
    mainWindow.show()

    sys.exit(app.exec())
