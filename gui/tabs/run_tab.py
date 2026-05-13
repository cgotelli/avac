from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.services import count_output_frames
from gui.state import AppState


class RunSimulationTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.process = QProcess(self)
        self.expected_frames = 1

        layout = QVBoxLayout(self)

        self.summary = QLabel("Select input data and parameters to prepare run summary.")
        self.summary.setWordWrap(True)

        controls = QHBoxLayout()
        self.run_btn = QPushButton("Run AVAC (make .output)")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)

        self.run_btn.clicked.connect(self.start_run)
        self.stop_btn.clicked.connect(self.stop_run)

        controls.addWidget(self.run_btn)
        controls.addWidget(self.stop_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        layout.addWidget(self.summary)
        layout.addLayout(controls)
        layout.addWidget(self.progress)
        layout.addWidget(self.log)

        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.on_finished)

        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.refresh_progress)

        self.state.changed.connect(self.update_summary)
        self.update_summary()

    def update_summary(self) -> None:
        m = self.state.dem_metadata
        comp = self.state.parameters.get("computation", {})
        self.expected_frames = int(comp.get("nb_simul", 1))
        lines = [
            f"Project: {self.state.project_dir}",
            f"DEM size: {m.get('ncols', '?')} x {m.get('nrows', '?')}",
            f"Cell size: {m.get('cellsize', '?')}",
            f"Expected frames: {self.expected_frames}",
            f"Output dir: {comp.get('output_directory', '_output')}",
        ]
        self.summary.setText("\n".join(lines))

    def start_run(self) -> None:
        makefile = self.state.project_dir / "Makefile"
        if not makefile.exists():
            QMessageBox.warning(self, "Missing Makefile", "Extract AVAC files first in Project Setup tab.")
            return

        self.log.clear()
        self.progress.setValue(0)

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        env = os.environ.copy()
        local_claw_path = (self.state.project_dir / ".vendor" / "clawpack-src").resolve()
        if local_claw_path.exists():
            env["CLAW"] = str(local_claw_path)
        else:
            env["CLAW"] = env.get("CLAW", "")

        self.process.setWorkingDirectory(str(self.state.project_dir))
        self.process.setProcessEnvironment(self.process_environment_from_dict(env))
        # Requires a POSIX-compatible shell that supports `-lc`.
        shell = os.environ.get("SHELL", "/bin/sh")
        self.process.start(shell, ["-lc", "make clean && make .output"])
        self.progress_timer.start(1500)

    def process_environment_from_dict(self, mapping: dict[str, str]):
        from PyQt6.QtCore import QProcessEnvironment

        env = QProcessEnvironment()
        for key, value in mapping.items():
            env.insert(str(key), str(value))
        return env

    def stop_run(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        self.progress_timer.stop()

    def read_stdout(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        self.log.insertPlainText(text)
        self.log.ensureCursorVisible()

    def read_stderr(self) -> None:
        text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="ignore")
        self.log.insertPlainText(text)
        self.log.ensureCursorVisible()

    def refresh_progress(self) -> None:
        output_dir = self.state.parameters.get("computation", {}).get("output_directory", "_output")
        count = count_output_frames(self.state.project_dir, output_dir)
        value = int(min(100, (count / max(1, self.expected_frames)) * 100))
        self.progress.setValue(value)

    def on_finished(self, exit_code: int, _exit_status) -> None:
        self.progress_timer.stop()
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        log_path = Path(self.state.project_dir) / "avac.log"
        log_path.write_text(self.log.toPlainText(), encoding="utf-8")
        self.state.last_run_log = log_path

        if exit_code == 0:
            self.progress.setValue(100)
            self.log.append("\nRun completed successfully.")
        else:
            self.log.append(f"\nRun failed with exit code {exit_code}.")
