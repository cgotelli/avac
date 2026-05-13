from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from gui.state import AppState
from gui.tabs.input_tab import InputDataTab
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
        self.input_tab = InputDataTab(self.state)
        self.parameters_tab = ParametersTab(self.state)
        self.run_tab = RunSimulationTab(self.state)
        self.results_tab = ResultsTab(self.state)

        self.tabs.addTab(self.setup_tab, "1. Project Setup")
        self.tabs.addTab(self.input_tab, "2. Input Data")
        self.tabs.addTab(self.parameters_tab, "3. Parameters")
        self.tabs.addTab(self.run_tab, "4. Run Simulation")
        self.tabs.addTab(self.results_tab, "5. Results & Analysis")
