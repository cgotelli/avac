from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.services import check_environment, extract_avac_files, install_clawpack_from_zip, resolve_clawpack_source_dir
from gui.state import AppState


class ProjectSetupTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        layout = QVBoxLayout(self)

        project_box = QGroupBox("Project")
        project_form = QFormLayout(project_box)

        self.project_label = QLabel(str(self.state.project_dir))
        self.project_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        pick_project_btn = QPushButton("Select Project Folder")
        pick_project_btn.clicked.connect(self.pick_project_folder)

        quickstart_btn = QPushButton("Load Pralognan Example")
        quickstart_btn.clicked.connect(self.load_quickstart)

        row = QHBoxLayout()
        row.addWidget(pick_project_btn)
        row.addWidget(quickstart_btn)

        project_form.addRow("Current folder:", self.project_label)
        project_form.addRow("Actions:", self._as_widget(row))

        env_box = QGroupBox("Environment status")
        env_layout = QVBoxLayout(env_box)

        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMinimumHeight(180)

        actions = QHBoxLayout()
        refresh_btn = QPushButton("Refresh Status")
        refresh_btn.clicked.connect(self.refresh_environment)

        extract_btn = QPushButton("Extract AVAC Files to Project")
        extract_btn.clicked.connect(self.extract_avac)

        setup_claw_btn = QPushButton("Install Shared Clawpack")
        setup_claw_btn.clicked.connect(self.install_clawpack)

        actions.addWidget(refresh_btn)
        actions.addWidget(extract_btn)
        actions.addWidget(setup_claw_btn)

        env_layout.addLayout(actions)
        env_layout.addWidget(self.status_text)

        tips = QFrame()
        tips_layout = QVBoxLayout(tips)
        tips_label = QLabel("Tips: use scripts/bootstrap_local_env.sh for a local environment and launch.bat on Windows/WSL.")
        tips_label.setWordWrap(True)
        tips_layout.addWidget(tips_label)

        layout.addWidget(project_box)
        layout.addWidget(env_box)
        layout.addWidget(tips)
        layout.addStretch(1)

        self.refresh_environment()

    def _as_widget(self, layout: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _resolve_setup_asset(self, filename: str) -> Path | None:
        repo_root = Path(__file__).resolve().parents[2]
        candidates = [repo_root / filename, self.state.project_dir / filename]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def pick_project_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select project directory", str(self.state.project_dir))
        if not selected:
            return
        self.state.update_project_dir(selected)
        self.project_label.setText(str(self.state.project_dir))
        self.refresh_environment()

    def load_quickstart(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        candidates = [repo_root, self.state.project_dir]

        def resolve_asset(name: str) -> Path | None:
            for base in candidates:
                path = base / name
                if path.exists():
                    return path
            return None

        dem = resolve_asset("topo1m.asc")
        starting = resolve_asset("ZA.shp")

        missing = [
            label
            for label, value in (("DEM (topo1m.asc)", dem), ("Starting areas (ZA.shp)", starting))
            if value is None
        ]
        if missing:
            QMessageBox.warning(
                self,
                "Quickstart",
                "Cannot load quickstart dataset. Missing: " + ", ".join(missing),
            )
            return

        self.state.set_paths(dem=dem, starting_areas=starting)
        QMessageBox.information(self, "Quickstart", "Demo dataset loaded.")

    def refresh_environment(self) -> None:
        status = check_environment(self.state.project_dir)
        self.state.environment = status

        lines = [
            f"Python: {'OK' if status.python_ok else 'Missing'} ({status.python_path})",
            f"gfortran: {'OK' if status.gfortran_found else 'Missing'} ({status.gfortran_path or '-'})",
            f"Clawpack: {'OK' if status.clawpack_ready else 'Missing'} ({status.claw_path or '-'})",
            f"AVAC solver files: {'OK' if status.avac_files_extracted else 'Missing'}",
        ]
        if status.notes:
            lines.append("\nNotes:")
            lines.extend([f"- {note}" for note in status.notes])
        self.status_text.setPlainText("\n".join(lines))

    def extract_avac(self) -> None:
        archive = self._resolve_setup_asset("files.tar.gz")
        if archive is None:
            QMessageBox.critical(
                self,
                "Extraction failed",
                "Cannot find files.tar.gz in the selected project folder or repository root.",
            )
            return
        try:
            self.status_text.append(f"\nExtracting AVAC files from: {archive}")
            extract_avac_files(archive, self.state.project_dir)
            QMessageBox.information(self, "Extraction", "AVAC files extracted successfully.")
            self.refresh_environment()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Extraction failed", str(exc))

    def install_clawpack(self) -> None:
        zip_path = self._resolve_setup_asset("clawpack-v5.14.0.zip")
        if zip_path is None:
            QMessageBox.critical(
                self,
                "Error",
                "Cannot find clawpack-v5.14.0.zip in the selected project folder or repository root.",
            )
            return

        target = resolve_clawpack_source_dir(self.state.project_dir)
        self.status_text.append(f"\nInstalling shared clawpack to: {target}")
        self.status_text.append(f"Using source zip: {zip_path}")
        try:
            returncode, output = install_clawpack_from_zip(zip_path, self.state.project_dir)
            self.status_text.append(output)
            if returncode == 0:
                QMessageBox.information(self, "Clawpack", "Shared Clawpack installation completed.")
            else:
                QMessageBox.warning(self, "Clawpack", "Installation finished with errors. Check logs in this panel.")
            self.refresh_environment()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Clawpack install failed", str(exc))
