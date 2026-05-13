from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow


def run() -> int:
    app = QApplication([])
    project_dir = Path.cwd()
    window = MainWindow(project_dir=project_dir)
    window.show()
    return app.exec()
