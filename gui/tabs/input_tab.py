from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.services import read_ascii_raster
from gui.state import AppState

try:
    import geopandas as gpd
except Exception:  # noqa: BLE001
    gpd = None


class InputDataTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.raster = None

        root = QHBoxLayout(self)

        controls = QVBoxLayout()

        files_box = QGroupBox("Input files")
        form = QFormLayout(files_box)

        self.dem_label = QLabel("Not selected")
        self.starting_label = QLabel("Not selected")
        self.profile_label = QLabel("Optional")

        dem_btn = QPushButton("Select DEM (.asc)")
        dem_btn.clicked.connect(self.pick_dem)
        starting_btn = QPushButton("Select Starting Areas (.shp)")
        starting_btn.clicked.connect(self.pick_starting_areas)
        profile_btn = QPushButton("Select Profile (.shp)")
        profile_btn.clicked.connect(self.pick_profile)

        self.show_hillshade = QCheckBox("Show hillshade")
        self.show_hillshade.setChecked(True)
        self.show_hillshade.stateChanged.connect(self.redraw)
        self.show_slope = QCheckBox("Show slope overlay")
        self.show_slope.stateChanged.connect(self.redraw)

        form.addRow(self.dem_label, dem_btn)
        form.addRow(self.starting_label, starting_btn)
        form.addRow(self.profile_label, profile_btn)
        form.addRow(self.show_hillshade)
        form.addRow(self.show_slope)

        self.validation = QTextEdit()
        self.validation.setReadOnly(True)
        self.validation.setMinimumHeight(220)

        controls.addWidget(files_box)
        controls.addWidget(QLabel("Validation and metadata"))
        controls.addWidget(self.validation)

        root.addLayout(controls, 1)

        self.figure = Figure(figsize=(8, 6), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        root.addWidget(self.canvas, 2)

        self.state.changed.connect(self.sync_from_state)
        self.sync_from_state()

    def pick_dem(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Select DEM", str(self.state.project_dir), "ASCII grids (*.asc)")
        if not selected:
            return
        self.state.set_paths(dem=Path(selected))

    def pick_starting_areas(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Select shapefile", str(self.state.project_dir), "Shapefiles (*.shp)")
        if not selected:
            return
        self.state.set_paths(starting_areas=Path(selected))

    def pick_profile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Select profile shapefile", str(self.state.project_dir), "Shapefiles (*.shp)")
        if not selected:
            return
        self.state.set_paths(profile=Path(selected))

    def sync_from_state(self) -> None:
        self.dem_label.setText(str(self.state.dem_path) if self.state.dem_path else "DEM not selected")
        self.starting_label.setText(str(self.state.starting_areas_path) if self.state.starting_areas_path else "Starting areas not selected")
        self.profile_label.setText(str(self.state.profile_path) if self.state.profile_path else "Profile not selected")

        self.validation.clear()
        if self.state.dem_path and self.state.dem_path.exists():
            self.raster = read_ascii_raster(self.state.dem_path)
            self.state.dem_metadata = self.raster.metadata
            m = self.raster.metadata
            self.validation.append("DEM parsed successfully")
            self.validation.append(f"- Dimensions: {m['ncols']} x {m['nrows']}")
            self.validation.append(f"- Extent: x [{m['xmin']:.2f}, {m['xmax']:.2f}] | y [{m['ymin']:.2f}, {m['ymax']:.2f}]")
            self.validation.append(f"- Cell size: {m['cellsize']:.2f}")
        else:
            self.raster = None

        if self.state.starting_areas_path and self.state.starting_areas_path.exists():
            if gpd is None:
                self.validation.append("Shapefile selected, but geopandas is not available to inspect features.")
            else:
                frame = gpd.read_file(self.state.starting_areas_path)
                self.validation.append(f"Starting areas polygons: {len(frame)}")
                self.validation.append(f"CRS: {frame.crs}")

        if self.state.profile_path and self.state.profile_path.exists() and gpd is not None:
            frame = gpd.read_file(self.state.profile_path)
            self.validation.append(f"Profile geometries: {len(frame)}")

        self.redraw()

    def redraw(self) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_title("DEM Preview")

        if self.raster is None:
            ax.text(0.5, 0.5, "Select a DEM to preview", ha="center", va="center", transform=ax.transAxes)
            self.canvas.draw_idle()
            return

        z = self.raster.z
        x = self.raster.x
        y = self.raster.y

        if self.show_hillshade.isChecked():
            gradient_y, gradient_x = np.gradient(np.nan_to_num(z, nan=np.nanmean(z)))
            slope = np.pi / 2.0 - np.arctan(np.sqrt(gradient_x * gradient_x + gradient_y * gradient_y))
            aspect = np.arctan2(-gradient_x, gradient_y)
            azimuth = np.deg2rad(315)
            altitude = np.deg2rad(45)
            hs = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
            ax.pcolormesh(x, y, hs, cmap="Greys", shading="auto", alpha=0.9)

        im = ax.pcolormesh(x, y, z, cmap="terrain", shading="auto", alpha=0.75 if self.show_hillshade.isChecked() else 1.0)
        self.figure.colorbar(im, ax=ax, label="Elevation")

        if self.show_slope.isChecked():
            gy, gx = np.gradient(np.nan_to_num(z, nan=np.nanmean(z)))
            slope_deg = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))
            ax.contour(x, y, slope_deg, levels=[20, 30, 40], colors=["yellow", "orange", "red"], linewidths=0.9)

        if self.state.starting_areas_path and self.state.starting_areas_path.exists() and gpd is not None:
            polygons = gpd.read_file(self.state.starting_areas_path)
            polygons.plot(ax=ax, facecolor="none", edgecolor="yellow", linewidth=1.4)

        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.set_aspect("equal")
        self.canvas.draw_idle()
