from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from gui.state import AppState
from gui.tabs.input_tab import InputDataTab
from gui.tabs.shape_editor_tab import ShapeEditorTab


class InputWorkspaceTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)
        self.input_tab = InputDataTab(state)
        self.shape_editor_tab = ShapeEditorTab(state)
        self.tabs.addTab(self.input_tab, "Data Preview")
        self.tabs.addTab(self.shape_editor_tab, "Shape Editor")

        layout.addWidget(self.tabs)
