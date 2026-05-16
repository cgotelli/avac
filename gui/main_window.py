from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from gui.state import AppState
from gui.tabs.input_workspace_tab import InputWorkspaceTab
from gui.tabs.parameters_tab import ParametersTab
from gui.tabs.results_tab import ResultsTab
from gui.tabs.run_tab import RunSimulationTab
from gui.tabs.setup_tab import ProjectSetupTab


class MainWindow(QMainWindow):
    def __init__(self, project_dir: Path):
        super().__init__()
        self.setWindowTitle("AVAC Desktop GUI")
        self.resize(1400, 900)

        self.state = AppState(project_dir=project_dir)

        self.tabs = QTabWidget(self)
        self.setCentralWidget(self.tabs)

        self.setup_tab = ProjectSetupTab(self.state)
        self.input_workspace_tab = InputWorkspaceTab(self.state)
        self.parameters_tab = ParametersTab(self.state)
        self.run_tab = RunSimulationTab(self.state)
        self.results_tab = ResultsTab(self.state)

        self.tabs.addTab(self.setup_tab, "Project Setup")
        self.tabs.addTab(self.input_workspace_tab, "Input Data & Shapes")
        self.tabs.addTab(self.parameters_tab, "Parameters")
        self.tabs.addTab(self.run_tab, "Run Simulation")
        self.tabs.addTab(self.results_tab, "Results & Analysis")
