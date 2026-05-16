from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def run() -> int:
    argv = sys.argv if sys.argv else ["avac_gui.py"]
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
    app = QApplication(argv)
    app.setApplicationName("AVAC")
    app.setApplicationDisplayName("AVAC")
    project_dir = Path.cwd()
    window = MainWindow(project_dir=project_dir)
    window.setWindowTitle("AVAC")
    window.show()
    return app.exec()
