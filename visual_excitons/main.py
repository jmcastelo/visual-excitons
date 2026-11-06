# This Python file uses the following encoding: utf-8
import sys
from pathlib import Path

# Make `visual_excitons` importable when this file is run directly from a
# clone (python visual_excitons/main.py); installed, it already is
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from visual_excitons import __version__
from visual_excitons.gui.main_window import MainWindow


def main():
    """Start the application (the `visual-excitons` command)."""
    # All OpenGL contexts share their resources (shaders, buffers), so the 3D
    # items can also be drawn by a separate window, as in image exports
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName('Visual Excitons')
    app.setApplicationVersion(__version__)
    app.setOrganizationName('VisualExcitons')

    mainWindow = MainWindow()
    mainWindow.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
