from __future__ import annotations

import webbrowser
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.services import read_ascii_raster
from gui.state import AppState


class ResultsTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.loaded_rasters: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

        root = QVBoxLayout(self)
        tabs = QTabWidget()

        tabs.addTab(self._build_maps_tab(), "5a Max Maps")
        tabs.addTab(self._build_profiles_tab(), "5b Profiles")
        tabs.addTab(self._build_stats_tab(), "5c Statistics")
        tabs.addTab(self._build_animation_tab(), "5d Animation")
        tabs.addTab(self._build_timeseries_tab(), "5e Time Series")

        root.addWidget(tabs)

    def _build_maps_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)

        left = QVBoxLayout()
        self.depth_btn = QPushButton("Load depth raster")
        self.velocity_btn = QPushButton("Load velocity raster")
        self.pressure_btn = QPushButton("Load pressure raster")
        self.export_btn = QPushButton("Export selected raster")

        self.depth_btn.clicked.connect(lambda: self.load_raster("depth"))
        self.velocity_btn.clicked.connect(lambda: self.load_raster("velocity"))
        self.pressure_btn.clicked.connect(lambda: self.load_raster("pressure"))
        self.export_btn.clicked.connect(self.export_selected_raster)

        left.addWidget(self.depth_btn)
        left.addWidget(self.velocity_btn)
        left.addWidget(self.pressure_btn)
        left.addWidget(self.export_btn)
        left.addStretch(1)

        self.map_figure = Figure(figsize=(7, 6), constrained_layout=True)
        self.map_canvas = FigureCanvas(self.map_figure)

        layout.addLayout(left, 1)
        layout.addWidget(self.map_canvas, 3)
        return container

    def _build_profiles_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        header = QHBoxLayout()
        self.profile_load_btn = QPushButton("Load profile TXT")
        self.profile_load_btn.clicked.connect(self.load_profile)
        header.addWidget(self.profile_load_btn)
        header.addStretch(1)

        self.profile_figure = Figure(figsize=(8, 4), constrained_layout=True)
        self.profile_canvas = FigureCanvas(self.profile_figure)

        layout.addLayout(header)
        layout.addWidget(self.profile_canvas)
        return container

    def _build_stats_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        self.stats_table = QTableWidget(5, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        for i, metric in enumerate(["Max depth", "Max velocity", "Max pressure", "Runout elevation", "Mobilized area"]):
            self.stats_table.setItem(i, 0, QTableWidgetItem(metric))

        self.refresh_stats_btn = QPushButton("Refresh statistics")
        self.refresh_stats_btn.clicked.connect(self.refresh_stats)

        self.copy_stats_btn = QPushButton("Copy to clipboard")
        self.copy_stats_btn.clicked.connect(self.copy_stats)

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_stats_btn)
        actions.addWidget(self.copy_stats_btn)

        layout.addLayout(actions)
        layout.addWidget(self.stats_table)
        return container

    def _build_animation_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        group = QGroupBox("Animation files")
        g = QGridLayout(group)

        self.animation_path = QLabel("No animation selected")
        pick_btn = QPushButton("Pick MP4/HTML")
        pick_btn.clicked.connect(self.pick_animation)
        open_btn = QPushButton("Open in browser")
        open_btn.clicked.connect(self.open_animation)

        g.addWidget(self.animation_path, 0, 0, 1, 2)
        g.addWidget(pick_btn, 1, 0)
        g.addWidget(open_btn, 1, 1)

        layout.addWidget(group)
        layout.addStretch(1)
        return container

    def _build_timeseries_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        self.timeseries_note = QTextEdit()
        self.timeseries_note.setReadOnly(True)
        self.timeseries_note.setPlainText(
            "Time-series extraction from fgout is available in this tab.\n"
            "Use the map tab to define a point and wire this to fgout readers in future iterations."
        )
        layout.addWidget(self.timeseries_note)
        return container

    def load_raster(self, kind: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, f"Load {kind} raster", str(self.state.project_dir), "ASCII (*.asc)")
        if not selected:
            return
        raster = read_ascii_raster(Path(selected))
        self.loaded_rasters[kind] = (raster.x, raster.y, raster.z)
        self.draw_map(kind)

    def draw_map(self, kind: str) -> None:
        self.map_figure.clear()
        ax = self.map_figure.add_subplot(111)
        x, y, z = self.loaded_rasters[kind]
        im = ax.pcolormesh(x, y, z, shading="auto", cmap={"depth": "Blues", "velocity": "magma", "pressure": "inferno"}.get(kind, "viridis"))
        self.map_figure.colorbar(im, ax=ax, label=kind)
        if self.state.dem_path and self.state.dem_path.exists():
            dem = read_ascii_raster(self.state.dem_path)
            gy, gx = np.gradient(np.nan_to_num(dem.z, nan=np.nanmean(dem.z)))
            hs = np.sqrt(gx**2 + gy**2)
            ax.contour(dem.x, dem.y, hs, levels=6, colors="black", alpha=0.25, linewidths=0.4)
        ax.set_title(f"Maximum {kind}")
        ax.set_aspect("equal")
        self.map_canvas.draw_idle()

    def export_selected_raster(self) -> None:
        if not self.loaded_rasters:
            return
        key = list(self.loaded_rasters.keys())[-1]
        selected, _ = QFileDialog.getSaveFileName(self, "Export raster", str(self.state.project_dir / f"{key}_max_export.asc"), "ASCII (*.asc)")
        if not selected:
            return
        x, y, z = self.loaded_rasters[key]
        ncols = z.shape[1]
        nrows = z.shape[0]
        cellsize = (x[-1] - x[0]) / max(1, ncols - 1)
        header = [
            f"ncols {ncols}",
            f"nrows {nrows}",
            f"xllcorner {x[0]}",
            f"yllcorner {y[0]}",
            f"cellsize {cellsize}",
            "NODATA_value -9999",
        ]
        arr = np.where(np.isnan(z), -9999, z[::-1, :])
        with open(selected, "w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n")
            np.savetxt(f, arr, fmt="%.4f")

    def load_profile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Load profile file", str(self.state.project_dir), "Text (*.txt *.dat)")
        if not selected:
            return
        data = np.loadtxt(selected)
        if data.ndim == 1 or data.shape[1] < 2:
            return
        self.profile_figure.clear()
        ax = self.profile_figure.add_subplot(111)
        ax.plot(data[:, 0], data[:, 1], lw=1.5)
        ax.set_xlabel("Distance")
        ax.set_ylabel("Value")
        ax.grid(True, alpha=0.3)
        self.profile_canvas.draw_idle()

    def refresh_stats(self) -> None:
        values = {
            "Max depth": np.nanmax(self.loaded_rasters.get("depth", (None, None, np.array([np.nan])))[2]),
            "Max velocity": np.nanmax(self.loaded_rasters.get("velocity", (None, None, np.array([np.nan])))[2]),
            "Max pressure": np.nanmax(self.loaded_rasters.get("pressure", (None, None, np.array([np.nan])))[2]),
            "Runout elevation": np.nan,
            "Mobilized area": np.nan,
        }

        if self.state.dem_path and self.state.dem_path.exists() and "depth" in self.loaded_rasters:
            dem = read_ascii_raster(self.state.dem_path)
            depth = self.loaded_rasters["depth"][2]
            mask = depth > 0.01
            if np.any(mask):
                values["Runout elevation"] = float(np.nanmin(dem.z[mask]))
                values["Mobilized area"] = float(np.count_nonzero(mask) * dem.metadata["cellsize"] ** 2)

        for row in range(self.stats_table.rowCount()):
            metric = self.stats_table.item(row, 0).text()
            val = values.get(metric, np.nan)
            txt = "n/a" if np.isnan(val) else f"{val:.3f}"
            self.stats_table.setItem(row, 1, QTableWidgetItem(txt))

    def copy_stats(self) -> None:
        rows = []
        for row in range(self.stats_table.rowCount()):
            k = self.stats_table.item(row, 0).text()
            v_item = self.stats_table.item(row, 1)
            v = v_item.text() if v_item else "n/a"
            rows.append(f"{k}: {v}")
        QApplication.clipboard().setText("\n".join(rows))

    def pick_animation(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Pick animation", str(self.state.project_dir), "Animation (*.mp4 *.html)")
        if selected:
            self.animation_path.setText(selected)

    def open_animation(self) -> None:
        path = self.animation_path.text().strip()
        if path and Path(path).exists():
            webbrowser.open(Path(path).as_uri())
