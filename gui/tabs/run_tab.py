from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MplPath
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

from gui.services import (
    build_avac_configuration,
    build_local_claw_env,
    count_output_frames,
    read_ascii_raster,
    resolve_clawpack_source_dir,
    write_claw_qinit_xyz,
    write_claw_topography_ascii,
    write_yaml,
)
from gui.state import AppState

try:
    import geopandas as gpd
except Exception:  # noqa: BLE001
    gpd = None


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
        output_dir = str(comp.get("output_directory", "_output"))
        output_display = output_dir[1:] if output_dir.startswith("_") and len(output_dir) > 1 else output_dir
        lines = [
            f"Project: {self.state.project_dir}",
            f"DEM size: {m.get('ncols', '?')} x {m.get('nrows', '?')}",
            f"Cell size: {m.get('cellsize', '?')}",
            f"Expected frames: {self.expected_frames}",
            f"Output folder: {output_display}",
        ]
        self.summary.setText("\n".join(lines))

    def start_run(self) -> None:
        makefile = self.state.project_dir / "Makefile"
        if not makefile.exists():
            QMessageBox.warning(self, "Missing Makefile", "Extract AVAC files first in Project Setup tab.")
            return
        claw_source_path = resolve_clawpack_source_dir(self.state.project_dir)
        if not claw_source_path.exists():
            QMessageBox.warning(
                self,
                "Missing Clawpack",
                "Shared Clawpack source is required for GUI runs.\nUse 'Install Shared Clawpack' in Project Setup.",
            )
            return
        try:
            self._materialize_simulation_configs()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Configuration error", str(exc))
            return

        self.log.clear()
        self.progress.setValue(0)

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        env = build_local_claw_env(
            os.environ.copy(),
            self.state.project_dir,
            python_executable=sys.executable,
        )
        self.log.append(f"Using CLAW root: {env.get('CLAW', '')}")
        self.log.append(f"Using CLAW Python: {env.get('CLAW_PYTHON', '')}")
        self.log.append(f"Using Meson editable skip paths: {env.get('MESONPY_EDITABLE_SKIP', '')}")

        self.process.setWorkingDirectory(str(self.state.project_dir))
        self.process.setProcessEnvironment(self.process_environment_from_dict(env))
        # Requires a POSIX-compatible shell that supports `-lc`.
        shell = os.environ.get("SHELL", "/bin/sh")
        self.process.start(shell, ["-lc", "make clean && make .output"])
        self.progress_timer.start(1500)

    def _effective_dem_path(self) -> Path | None:
        if self.state.dem_path and self.state.dem_path.exists():
            return self.state.dem_path
        return None

    def _effective_starting_areas_path(self) -> Path | None:
        if self.state.starting_areas_path and self.state.starting_areas_path.exists():
            return self.state.starting_areas_path
        return None

    @staticmethod
    def _guess_crs_from_bounds(xmin: float, xmax: float, ymin: float, ymax: float) -> str:
        if abs(float(xmin)) > 180.0 or abs(float(xmax)) > 180.0 or abs(float(ymin)) > 90.0 or abs(float(ymax)) > 90.0:
            return "EPSG:2154"
        return "EPSG:4326"

    def _starting_area_mask(self, frame, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        xx, yy = np.meshgrid(x, y)
        points = np.column_stack((xx.ravel(), yy.ravel()))
        inside_any = np.zeros(points.shape[0], dtype=bool)

        for geom in frame.geometry:
            if geom is None or geom.is_empty:
                continue
            if geom.geom_type == "Polygon":
                polygons = [geom]
            elif geom.geom_type == "MultiPolygon":
                polygons = list(geom.geoms)
            else:
                continue

            for poly in polygons:
                exterior = np.asarray(poly.exterior.coords)
                if exterior.ndim != 2 or exterior.shape[0] < 3:
                    continue
                inside_poly = MplPath(exterior).contains_points(points)
                for interior in poly.interiors:
                    ring = np.asarray(interior.coords)
                    if ring.ndim == 2 and ring.shape[0] >= 3:
                        inside_poly &= ~MplPath(ring).contains_points(points)
                inside_any |= inside_poly

        return inside_any.reshape((y.size, x.size))

    def _initial_depth_from_release(self, raster, zone_mask: np.ndarray) -> np.ndarray:
        release = self.state.parameters.get("release", {})
        altitude = np.array(raster.z, dtype=float)
        depth = np.zeros_like(altitude, dtype=float)
        if not np.any(zone_mask):
            return depth

        d0 = float(release.get("d0", 0.0))
        z_ref = float(release.get("z_ref", 0.0))
        gradient_hypso = float(release.get("gradient_hypso", 0.0))
        theta_cr = float(release.get("theta_cr", 30.0))
        nu = float(release.get("nu", 0.2))
        corr_elevation = bool(release.get("correction_elevation", False))
        corr_slope = bool(release.get("correction_slope", False))
        cellsize = float(raster.metadata.get("cellsize", 1.0))

        valid = np.isfinite(altitude)
        fill_value = float(np.nanmean(altitude[valid])) if np.any(valid) else 0.0
        z_fill = np.nan_to_num(altitude, nan=fill_value)
        grad_y, grad_x = np.gradient(z_fill, cellsize)
        slope = np.sqrt(grad_x * grad_x + grad_y * grad_y)

        if corr_slope:
            theta_rad = np.deg2rad(theta_cr)
            q_angle = np.arctan(slope)
            numerator = np.sin(theta_rad) - nu * np.cos(theta_rad)
            denominator = np.sin(q_angle) - nu * np.cos(q_angle)
            factor1 = np.zeros_like(slope, dtype=float)
            safe = (q_angle > np.deg2rad(25.0)) & (np.abs(denominator) > 1e-12)
            factor1[safe] = numerator / denominator[safe]
        else:
            factor1 = np.ones_like(slope, dtype=float)

        if corr_elevation:
            factor2 = (altitude - z_ref) * gradient_hypso / 100.0
        else:
            factor2 = np.zeros_like(altitude, dtype=float)

        if corr_elevation and corr_slope:
            candidate = (d0 + factor2) * factor1
        elif corr_elevation and not corr_slope:
            candidate = d0 + factor2
        elif (not corr_elevation) and corr_slope:
            candidate = d0 * factor1
        else:
            candidate = np.full_like(altitude, d0, dtype=float)

        depth[zone_mask] = candidate[zone_mask]
        depth[~np.isfinite(depth)] = 0.0
        return depth

    def _materialize_simulation_configs(self) -> None:
        dem_path = self._effective_dem_path()
        if dem_path is None:
            raise ValueError("DEM file is missing. Select a DEM in 'Input Data & Shapes' before running.")
        starting_path = self._effective_starting_areas_path()
        if starting_path is None:
            raise ValueError("Starting areas shapefile is missing. Select it in 'Input Data & Shapes' before running.")
        if gpd is None:
            raise RuntimeError("geopandas is required to regenerate init.xyz but is not available in this environment.")

        raster = read_ascii_raster(dem_path)
        dem_metadata = dict(raster.metadata)
        self.state.dem_metadata = dem_metadata
        dem_crs = self._guess_crs_from_bounds(
            dem_metadata["xmin"],
            dem_metadata["xmax"],
            dem_metadata["ymin"],
            dem_metadata["ymax"],
        )

        polygons = gpd.read_file(starting_path)
        if len(polygons) == 0:
            raise ValueError(f"Starting areas shapefile has no features: {starting_path}")
        if polygons.crs is not None and str(polygons.crs).upper() != dem_crs:
            polygons = polygons.to_crs(dem_crs)

        zone_mask = self._starting_area_mask(polygons, raster.x, raster.y)
        if not np.any(zone_mask):
            raise ValueError("Starting areas do not overlap DEM extent after CRS handling.")
        initial_depth = self._initial_depth_from_release(raster, zone_mask)

        parameters_path = self.state.project_dir / "AVAC_parameters.yaml"
        configuration_path = self.state.project_dir / "AVAC_configuration.yaml"
        topography_path = self.state.project_dir / "topography.asc"
        init_path = self.state.project_dir / "init.xyz"

        write_claw_topography_ascii(topography_path, raster)
        write_claw_qinit_xyz(init_path, raster.x, raster.y, initial_depth)
        write_yaml(parameters_path, self.state.parameters)
        configuration = build_avac_configuration(
            self.state.parameters,
            dem_metadata,
            topofile=topography_path.name,
            initiation_file=init_path.name,
            type_dem=3,
            type_init=1,
        )
        write_yaml(configuration_path, configuration)

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
