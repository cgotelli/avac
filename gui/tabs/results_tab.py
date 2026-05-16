from __future__ import annotations

import base64
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import matplotlib.cm as cm
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PIL import Image
from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from shapely.geometry import box

from gui.services import (
    build_local_claw_env,
    derive_notebook_pressure_field,
    derive_notebook_profile_axes,
    FGoutFrameData,
    latest_result_directory,
    list_fgout_frames,
    list_result_directories,
    load_fgout_frame,
    load_fgmax_results,
    read_ascii_raster,
    read_yaml,
)
from gui.state import AppState

try:
    import geopandas as gpd
except Exception:  # noqa: BLE001
    gpd = None

WEBENGINE_DISABLED = os.environ.get("AVAC_DISABLE_WEBENGINE", "0") == "1"
if WEBENGINE_DISABLED:
    QWebChannel = None
    QWebEngineView = None
else:
    try:
        from PyQt6.QtWebChannel import QWebChannel
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except Exception:  # noqa: BLE001
        QWebChannel = None
        QWebEngineView = None


LEAFLET_PROFILE_EDITOR_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
  <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css\" />
  <style>
    html, body, #map { height: 100%; margin: 0; }
    .leaflet-container { background: #f0f3f5; }
    .help {
      position: absolute;
      z-index: 900;
      top: 8px;
      left: 52px;
      background: rgba(255, 255, 255, 0.94);
      padding: 6px 10px;
      border-radius: 6px;
      font: 12px/1.3 sans-serif;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
    }
  </style>
</head>
<body>
  <div class=\"help\">Draw/Edit/Delete profile lines directly on the map.</div>
  <div id=\"map\"></div>
  <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
  <script src=\"https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js\"></script>
  <script src=\"qrc:///qtwebchannel/qwebchannel.js\"></script>
  <script>
    const map = L.map('map', { zoomControl: true });
    map.setView([46.8, 6.7], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    const drawLayer = new L.FeatureGroup();
    map.addLayer(drawLayer);

    const drawControl = new L.Control.Draw({
      draw: {
        polygon: false,
        polyline: { shapeOptions: { color: '#0f766e', weight: 3 } },
        rectangle: false,
        circle: false,
        marker: false,
        circlemarker: false
      },
      edit: { featureGroup: drawLayer }
    });
    map.addControl(drawControl);

    let host = null;
    let demImageLayer = null;
    let demBounds = null;

    function isReasonableBounds(b) {
      if (!b || !b.isValid()) {
        return false;
      }
      const spanLat = Math.abs(b.getNorth() - b.getSouth());
      const spanLng = Math.abs(b.getEast() - b.getWest());
      return spanLat > 0 && spanLng > 0 && spanLat < 20 && spanLng < 20;
    }

    function fitToData() {
      const lineBounds = drawLayer.getBounds();
      if (isReasonableBounds(lineBounds)) {
        map.fitBounds(lineBounds, { padding: [0, 0], animate: false });
        return;
      }
      if (demBounds && isReasonableBounds(demBounds)) {
        map.fitBounds(demBounds, { padding: [0, 0], animate: false });
      }
    }

    function emitGeoJsonToHost() {
      if (!host || !host.pushGeoJson) {
        return;
      }
      host.pushGeoJson(JSON.stringify(drawLayer.toGeoJSON()));
    }

    function loadProfileGeoJson(featureCollection) {
      drawLayer.clearLayers();
      if (featureCollection && featureCollection.features) {
        L.geoJSON(featureCollection, {
          style: { color: '#0f766e', weight: 3 }
        }).eachLayer(function (layer) {
          drawLayer.addLayer(layer);
        });
      }
      fitToData();
    }

    function clearProfiles() {
      drawLayer.clearLayers();
      emitGeoJsonToHost();
      fitToData();
    }

    function loadDemRaster(payload) {
      if (demImageLayer) {
        map.removeLayer(demImageLayer);
        demImageLayer = null;
      }
      demBounds = null;

      if (payload && payload.image && payload.bounds) {
        const b = L.latLngBounds(payload.bounds);
        if (isReasonableBounds(b)) {
          demBounds = b;
          demImageLayer = L.imageOverlay(payload.image, demBounds, {
            opacity: 1.0,
            interactive: false
          });
          demImageLayer.addTo(map);
        }
      }
      fitToData();
    }

    window.loadDemRaster = loadDemRaster;
    window.loadProfileGeoJson = loadProfileGeoJson;
    window.clearProfiles = clearProfiles;

    map.on(L.Draw.Event.CREATED, function (e) {
      drawLayer.addLayer(e.layer);
      emitGeoJsonToHost();
    });
    map.on(L.Draw.Event.EDITED, emitGeoJsonToHost);
    map.on(L.Draw.Event.DELETED, emitGeoJsonToHost);

    new QWebChannel(qt.webChannelTransport, function (channel) {
      host = channel.objects.profileBridge;
      setTimeout(function () { map.invalidateSize(); fitToData(); }, 50);
    });
  </script>
</body>
</html>
"""


class ProfileLeafletBridge(QObject):
    geojson_received = pyqtSignal(str)

    @pyqtSlot(str)
    def pushGeoJson(self, payload: str) -> None:
        self.geojson_received.emit(payload)


def _empty_profile_frame(crs: str = "EPSG:4326"):
    if gpd is None:
        return None
    return gpd.GeoDataFrame(data={"profile_id": []}, geometry=[], crs=crs)


class ResultsTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.loaded_rasters: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self.active_kind: str | None = None
        self.result_topography: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self.current_result_dir: Path | None = None
        self.fgout_frames: list[tuple[int, float]] = []
        self.fgout_cache: dict[int, FGoutFrameData] = {}
        self.active_time_kind: str = "depth"
        self.profile_web_supported = bool(QWebEngineView and QWebChannel)
        self.profile_webengine_disabled = WEBENGINE_DISABLED
        self.profile_leaflet_bridge: ProfileLeafletBridge | None = None
        self.profile_web_view = None
        self._profile_leaflet_loaded = False
        self.profile_vector = _empty_profile_frame(crs="EPSG:4326")
        self.last_profile_series: list[dict[str, np.ndarray]] = []
        self.last_profile_source: str = ""
        self.animation_process = QProcess(self)
        self._pending_animation_prefix: Path | None = None
        self._animation_was_stopped = False

        self.animation_process.readyReadStandardOutput.connect(self._read_animation_stdout)
        self.animation_process.readyReadStandardError.connect(self._read_animation_stderr)
        self.animation_process.finished.connect(self._on_animation_finished)

        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.load_last_btn = QPushButton("Load Last Run Results")
        self.load_other_btn = QPushButton("Load Other Simulation...")
        self.refresh_runs_btn = QPushButton("Refresh Runs")
        self.status_label = QLabel("No results loaded.")
        self.status_label.setWordWrap(True)

        self.load_last_btn.clicked.connect(self.load_last_results)
        self.load_other_btn.clicked.connect(self.pick_results_directory)
        self.refresh_runs_btn.clicked.connect(self.refresh_result_hints)

        controls.addWidget(self.load_last_btn)
        controls.addWidget(self.load_other_btn)
        controls.addWidget(self.refresh_runs_btn)
        controls.addWidget(self.status_label, 1)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_maps_tab(), "Max Maps")
        self.tabs.addTab(self._build_time_maps_tab(), "Time Maps")
        self.tabs.addTab(self._build_profiles_tab(), "Profiles")
        self.tabs.addTab(self._build_animation_tab(), "Animation")
        self.tabs.currentChanged.connect(self._on_results_subtab_changed)

        root.addLayout(controls)
        root.addWidget(self.tabs)

        self.state.changed.connect(self._on_state_changed)
        self.refresh_result_hints()

    def _build_maps_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)

        left = QVBoxLayout()
        self.depth_btn = QPushButton("Show depth map")
        self.velocity_btn = QPushButton("Show velocity map")
        self.pressure_btn = QPushButton("Show pressure map")
        self.export_btn = QPushButton("Export current raster")

        self.depth_btn.clicked.connect(lambda: self.show_map_or_prompt("depth"))
        self.velocity_btn.clicked.connect(lambda: self.show_map_or_prompt("velocity"))
        self.pressure_btn.clicked.connect(lambda: self.show_map_or_prompt("pressure"))
        self.export_btn.clicked.connect(self.export_selected_raster)

        self.map_info = QLabel("Load results to display derived maximum maps.")
        self.map_info.setWordWrap(True)

        left.addWidget(self.depth_btn)
        left.addWidget(self.velocity_btn)
        left.addWidget(self.pressure_btn)
        left.addWidget(self.export_btn)
        left.addWidget(self.map_info)
        left.addStretch(1)

        self.map_figure = Figure(figsize=(7, 6), constrained_layout=True)
        self.map_canvas = FigureCanvas(self.map_figure)

        layout.addLayout(left, 1)
        layout.addWidget(self.map_canvas, 3)
        return container

    def _build_time_maps_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)

        left = QVBoxLayout()
        self.time_kind_combo = QComboBox()
        self.time_kind_combo.addItems(["depth", "velocity", "pressure"])
        self.time_kind_combo.currentTextChanged.connect(self._on_time_controls_changed)

        self.time_frame_combo = QComboBox()
        self.time_frame_combo.currentIndexChanged.connect(self._on_time_controls_changed)

        self.time_refresh_btn = QPushButton("Refresh frame list")
        self.time_refresh_btn.clicked.connect(self.refresh_time_frame_list)
        self.time_show_btn = QPushButton("Show selected frame")
        self.time_show_btn.clicked.connect(self.draw_selected_time_map)
        self.time_export_png_btn = QPushButton("Export current PNG")
        self.time_export_png_btn.clicked.connect(self.export_current_time_map_png)
        self.time_export_all_btn = QPushButton("Export all frames to PNG")
        self.time_export_all_btn.clicked.connect(self.export_all_time_maps_png)

        self.time_map_info = QLabel("Load results to list fgout frames and display time-dependent maps.")
        self.time_map_info.setWordWrap(True)

        left.addWidget(QLabel("Field"))
        left.addWidget(self.time_kind_combo)
        left.addWidget(QLabel("Time frame"))
        left.addWidget(self.time_frame_combo)
        left.addWidget(self.time_refresh_btn)
        left.addWidget(self.time_show_btn)
        left.addWidget(self.time_export_png_btn)
        left.addWidget(self.time_export_all_btn)
        left.addWidget(self.time_map_info)
        left.addStretch(1)

        self.time_map_figure = Figure(figsize=(7, 6), constrained_layout=True)
        self.time_map_canvas = FigureCanvas(self.time_map_figure)

        layout.addLayout(left, 1)
        layout.addWidget(self.time_map_canvas, 3)
        return container

    def _build_profiles_tab(self) -> QWidget:
        container = QWidget()
        self.profile_tab_widget = container
        layout = QVBoxLayout(container)

        header = QHBoxLayout()
        self.profile_save_btn = QPushButton("Save Profiles")
        self.profile_save_as_btn = QPushButton("Save Profiles As...")
        self.profile_clear_btn = QPushButton("Clear Drawn Profiles")
        self.profile_plot_btn = QPushButton("Plot Profiles")
        self.profile_export_csv_btn = QPushButton("Export Profiles Data")
        self.profile_overlay_checkbox = QCheckBox("Overlay all profiles")
        self.profile_overlay_checkbox.setChecked(True)
        self.profile_overlay_checkbox.setToolTip("Uncheck to show one row of plots per profile.")

        self.profile_save_btn.clicked.connect(self.save_profiles)
        self.profile_save_as_btn.clicked.connect(self.save_profiles_as)
        self.profile_clear_btn.clicked.connect(self.clear_drawn_profiles)
        self.profile_plot_btn.clicked.connect(self.plot_saved_profiles)
        self.profile_export_csv_btn.clicked.connect(self.export_profiles_csv)

        header.addWidget(self.profile_save_btn)
        header.addWidget(self.profile_save_as_btn)
        header.addWidget(self.profile_clear_btn)
        header.addWidget(self.profile_plot_btn)
        header.addWidget(self.profile_export_csv_btn)
        header.addWidget(self.profile_overlay_checkbox)
        header.addStretch(1)

        self.profile_status = QLabel("Draw one or more profile lines on the map, then save and plot.")
        self.profile_status.setWordWrap(True)

        if self.profile_web_supported:
            self.profile_web_view = QWebEngineView()
            self.profile_leaflet_bridge = ProfileLeafletBridge()
            self.profile_leaflet_bridge.geojson_received.connect(self.apply_profile_geojson_from_leaflet)

            channel = QWebChannel(self.profile_web_view.page())
            channel.registerObject("profileBridge", self.profile_leaflet_bridge)
            self.profile_web_view.page().setWebChannel(channel)
            self.profile_web_view.loadFinished.connect(self._on_profile_leaflet_loaded)
            self.profile_web_view.setHtml(LEAFLET_PROFILE_EDITOR_HTML)
            self.profile_web_view.setMinimumHeight(360)
        else:
            self.profile_web_view = None

        self.profile_figure = Figure(figsize=(8, 5), constrained_layout=True)
        self.profile_canvas = FigureCanvas(self.profile_figure)
        self.profile_canvas.setMinimumHeight(280)

        layout.addLayout(header)
        layout.addWidget(self.profile_status)
        if self.profile_web_view is not None:
            layout.addWidget(self.profile_web_view, 3)
        else:
            fallback = QLabel(
                "Leaflet profile editor is unavailable because PyQt6-WebEngine is not installed."
                if not self.profile_webengine_disabled
                else "Leaflet profile editor is disabled by the webengine disable flag."
            )
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
        layout.addWidget(self.profile_canvas)
        return container

    def _build_animation_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        build_group = QGroupBox("Generate Animation")
        build_layout = QGridLayout(build_group)
        build_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.animation_variable = QComboBox()
        self.animation_variable.addItems(["pressure", "depth", "velocity"])
        default_variable = str(self.state.parameters.get("animation", {}).get("variable", "depth")).strip().lower()
        index = self.animation_variable.findText(default_variable)
        self.animation_variable.setCurrentIndex(index if index >= 0 else 1)

        self.animation_fps = QSpinBox()
        self.animation_fps.setRange(1, 60)
        self.animation_fps.setValue(5)

        self.animation_generate_btn = QPushButton("Generate MP4")
        self.animation_stop_btn = QPushButton("Stop")
        self.animation_stop_btn.setEnabled(False)
        self.animation_generate_btn.clicked.connect(self.generate_animation)
        self.animation_stop_btn.clicked.connect(self.stop_animation_generation)

        self.animation_status = QLabel("Generate an animation from loaded fgout results.")
        self.animation_status.setWordWrap(True)

        build_layout.addWidget(QLabel("Field"), 0, 0)
        build_layout.addWidget(self.animation_variable, 0, 1)
        build_layout.addWidget(QLabel("FPS"), 0, 2)
        build_layout.addWidget(self.animation_fps, 0, 3)
        build_layout.addWidget(self.animation_generate_btn, 1, 0, 1, 2)
        build_layout.addWidget(self.animation_stop_btn, 1, 2, 1, 2)
        build_layout.addWidget(self.animation_status, 2, 0, 1, 4)

        player_group = QGroupBox("MP4 Output")
        player_layout = QGridLayout(player_group)
        player_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.animation_path = QLabel("No MP4 selected")
        self.animation_path.setWordWrap(True)
        self.animation_path.setMaximumHeight(32)
        self.animation_open_btn = QPushButton("Open MP4 in Player")

        self.animation_open_btn.clicked.connect(self.open_animation)

        player_layout.addWidget(self.animation_path, 0, 0, 1, 2)
        player_layout.addWidget(self.animation_open_btn, 1, 0, 1, 2)

        self.animation_log = QTextEdit()
        self.animation_log.setReadOnly(True)
        self.animation_log.setMinimumHeight(260)
        self.animation_log.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout.addWidget(build_group)
        layout.addWidget(player_group)
        layout.addWidget(self.animation_log, 1)
        return container

    def _on_state_changed(self) -> None:
        self.refresh_result_hints()
        self.push_profile_layers_to_leaflet()

    def _on_results_subtab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.profile_tab_widget:
            self.push_profile_layers_to_leaflet()

    def _effective_dem_path(self) -> Path | None:
        if self.state.dem_path and self.state.dem_path.exists():
            return self.state.dem_path
        return None

    @staticmethod
    def _guess_crs_from_bounds(xmin: float, xmax: float, ymin: float, ymax: float) -> str:
        if abs(float(xmin)) > 180.0 or abs(float(xmax)) > 180.0 or abs(float(ymin)) > 90.0 or abs(float(ymax)) > 90.0:
            return "EPSG:2154"
        return "EPSG:4326"

    def _effective_dem_crs(self) -> str:
        dem = self._effective_dem_path()
        if dem is None:
            return "EPSG:4326"
        try:
            metadata = read_ascii_raster(dem).metadata
            return self._guess_crs_from_bounds(
                metadata.get("xmin", 0.0),
                metadata.get("xmax", 0.0),
                metadata.get("ymin", 0.0),
                metadata.get("ymax", 0.0),
            )
        except Exception:  # noqa: BLE001
            return "EPSG:4326"

    def _effective_profile_crs(self) -> str:
        if gpd is not None and self.profile_vector is not None and getattr(self.profile_vector, "crs", None) is not None:
            return str(self.profile_vector.crs)
        return self._effective_dem_crs()

    def _profile_vector_for_leaflet_json(self) -> str:
        if gpd is None or self.profile_vector is None or len(self.profile_vector) == 0:
            return '{"type":"FeatureCollection","features":[]}'

        frame = self.profile_vector
        if frame.crs is None:
            frame = frame.set_crs(self._effective_profile_crs(), allow_override=True)
        if frame.crs is not None and str(frame.crs).upper() != "EPSG:4326":
            frame = frame.to_crs("EPSG:4326")
        return frame.to_json(drop_id=True)

    def _dem_bounds_for_profile_leaflet_json(self) -> str:
        dem_path = self._effective_dem_path()
        if dem_path is None or gpd is None:
            return "{}"

        try:
            raster = read_ascii_raster(dem_path)
            metadata = raster.metadata
            z = np.array(raster.z, dtype=float)
            valid = np.isfinite(z)
            if not np.any(valid):
                return "{}"

            low, high = np.nanpercentile(z[valid], [2.0, 98.0])
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                low = float(np.nanmin(z[valid]))
                high = float(np.nanmax(z[valid]))
                if high <= low:
                    high = low + 1.0

            elev_norm = np.clip((z - low) / (high - low), 0.0, 1.0)
            terrain_rgb = cm.get_cmap("terrain")(elev_norm)[..., :3]

            z_fill = np.nan_to_num(z, nan=float(np.nanmean(z[valid])))
            gy, gx = np.gradient(z_fill)
            slope = np.pi / 2.0 - np.arctan(np.sqrt(gx * gx + gy * gy))
            aspect = np.arctan2(-gx, gy)
            azimuth = np.deg2rad(315.0)
            altitude = np.deg2rad(45.0)
            hillshade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
            hillshade = np.clip((hillshade + 1.0) * 0.5, 0.0, 1.0)

            rgb = np.clip(terrain_rgb * 0.72 + hillshade[..., None] * 0.28, 0.0, 1.0)

            rgba = np.zeros((z.shape[0], z.shape[1], 4), dtype=np.uint8)
            rgba[..., 0:3] = (rgb * 255.0).astype(np.uint8)
            rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
            rgba = np.flipud(rgba)

            image = Image.fromarray(rgba, mode="RGBA")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            payload_image = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

            dem_frame = gpd.GeoDataFrame(
                [{"geometry": box(metadata["xmin"], metadata["ymin"], metadata["xmax"], metadata["ymax"])}],
                geometry="geometry",
                crs=self._effective_dem_crs(),
            )
            if dem_frame.crs is not None and str(dem_frame.crs).upper() != "EPSG:4326":
                dem_frame = dem_frame.to_crs("EPSG:4326")
            minx, miny, maxx, maxy = dem_frame.total_bounds

            if not np.all(np.isfinite([minx, miny, maxx, maxy])):
                return "{}"
            if minx < -180.0 or maxx > 180.0 or miny < -90.0 or maxy > 90.0:
                return "{}"

            return json.dumps(
                {
                    "image": payload_image,
                    "bounds": [[float(miny), float(minx)], [float(maxy), float(maxx)]],
                }
            )
        except Exception:  # noqa: BLE001
            return "{}"

    def _run_profile_leaflet(self, script: str) -> None:
        if self.profile_web_view is None or not self._profile_leaflet_loaded:
            return
        self.profile_web_view.page().runJavaScript(script)

    def _run_profile_leaflet_geojson(self, function_name: str, payload_json: str) -> None:
        script = f"window.{function_name}(JSON.parse({json.dumps(payload_json)}));"
        self._run_profile_leaflet(script)

    def push_profile_layers_to_leaflet(self) -> None:
        if self.profile_web_view is None:
            return
        self._run_profile_leaflet_geojson("loadDemRaster", self._dem_bounds_for_profile_leaflet_json())
        self._run_profile_leaflet_geojson("loadProfileGeoJson", self._profile_vector_for_leaflet_json())

    def _on_profile_leaflet_loaded(self, ok: bool) -> None:
        self._profile_leaflet_loaded = bool(ok)
        if ok:
            self.push_profile_layers_to_leaflet()

    def apply_profile_geojson_from_leaflet(self, payload: str) -> None:
        if gpd is None:
            self.profile_status.setText("Leaflet updated, but geopandas is not available to store profile lines.")
            return

        try:
            parsed = json.loads(payload)
            features = parsed.get("features", []) if isinstance(parsed, dict) else []
            profile_crs = self._effective_profile_crs()

            if features:
                updated = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
                if "geometry" in updated:
                    updated = updated[updated.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
                if len(updated) > 0 and str(profile_crs).upper() != "EPSG:4326":
                    updated = updated.to_crs(profile_crs)
            else:
                updated = _empty_profile_frame(crs=profile_crs)

            if updated is None:
                return
            if "profile_id" not in updated.columns:
                updated["profile_id"] = [f"Profile {i + 1}" for i in range(len(updated))]

            self.profile_vector = updated.reset_index(drop=True)
            self.last_profile_series = []
            self.last_profile_source = ""
            self.profile_status.setText(f"{len(self.profile_vector)} profile line(s) ready. Save to write profil.shp.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Leaflet sync failed", str(exc))

    def _target_profile_save_path(self) -> Path:
        if self.state.profile_path is not None:
            return self.state.profile_path
        return self.state.project_dir / "profil.shp"

    def _save_profiles_to_path(self, path: Path) -> bool:
        if gpd is None:
            QMessageBox.warning(self, "Missing dependency", "geopandas is required to save profile shapefiles.")
            return False
        if self.profile_vector is None or len(self.profile_vector) == 0:
            QMessageBox.warning(self, "No profiles", "Draw at least one profile line before saving.")
            return False

        frame = self.profile_vector.copy()
        if frame.crs is None:
            frame = frame.set_crs(self._effective_profile_crs(), allow_override=True)
        if "profile_id" not in frame.columns:
            frame["profile_id"] = [f"Profile {i + 1}" for i in range(len(frame))]
        frame = frame[["profile_id", "geometry"]]

        path = Path(path)
        if path.suffix.lower() != ".shp":
            path = path.with_suffix(".shp")
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_file(path)
        self.state.set_paths(profile=path)
        self.profile_status.setText(f"Saved {len(frame)} profile line(s) to {path}.")
        return True

    def save_profiles(self) -> None:
        self._save_profiles_to_path(self._target_profile_save_path())

    def save_profiles_as(self) -> None:
        target = self._target_profile_save_path()
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save profile shapefile",
            str(target),
            "Shapefiles (*.shp)",
        )
        if not selected:
            return
        self._save_profiles_to_path(Path(selected))

    def clear_drawn_profiles(self) -> None:
        self.profile_vector = _empty_profile_frame(crs=self._effective_profile_crs())
        self.last_profile_series = []
        self.last_profile_source = ""
        self._run_profile_leaflet("window.clearProfiles();")
        self.profile_status.setText("Cleared drawn profiles.")

    def plot_saved_profiles(self) -> None:
        resolved = self._resolve_profile_frame_source(silent=False)
        if resolved is None:
            return
        frame, source_label = resolved
        self.compute_profiles_from_frame(frame, source_label=source_label, silent=False)

    def export_profiles_csv(self) -> None:
        if "depth" not in self.loaded_rasters or "velocity" not in self.loaded_rasters or "pressure" not in self.loaded_rasters:
            QMessageBox.warning(self, "Missing maps", "Load simulation results first.")
            return

        profile_series = self.last_profile_series
        source_label = self.last_profile_source
        if not profile_series:
            resolved = self._resolve_profile_frame_source(silent=False)
            if resolved is None:
                return
            frame, source_label = resolved
            try:
                profile_series = self._compute_profile_series_from_frame(frame)
            except Exception as exc:  # noqa: BLE001
                self.profile_status.setText(f"Profile export failed: {exc}")
                QMessageBox.critical(self, "Profile export error", str(exc))
                return
            self.last_profile_series = profile_series
            self.last_profile_source = source_label

        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export profile values to CSV",
            str(self.state.project_dir / "profiles-data.csv"),
            "CSV (*.csv)",
        )
        if not selected:
            return

        csv_path = Path(selected)
        if csv_path.suffix.lower() != ".csv":
            csv_path = csv_path.with_suffix(".csv")
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        headers: list[str] = []
        for idx in range(len(profile_series)):
            p = idx + 1
            headers.extend([f"X P{p}", f"Y P{p}", f"velocity P{p}", f"pressure P{p}", f"depth P{p}"])

        row_count = max(len(series["x"]) for series in profile_series)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for row_idx in range(row_count):
                row: list[object] = []
                for series in profile_series:
                    if row_idx < len(series["x"]):
                        row.extend(
                            [
                                float(series["x"][row_idx]),
                                float(series["y"][row_idx]),
                                float(series["velocity"][row_idx]),
                                float(series["pressure"][row_idx]),
                                float(series["depth"][row_idx]),
                            ]
                        )
                    else:
                        row.extend(["", "", "", "", ""])
                writer.writerow(row)

        self.profile_status.setText(
            f"Exported {len(profile_series)} profile(s) to CSV: {csv_path} (source: {source_label})."
        )

    def refresh_result_hints(self) -> None:
        output_dir = self.state.parameters.get("computation", {}).get("output_directory", "_output")
        result_dirs = list_result_directories(self.state.project_dir, configured_output_dir=output_dir)
        if not result_dirs:
            self.status_label.setText("No result folders found yet.")
            return
        latest = latest_result_directory(self.state.project_dir, configured_output_dir=output_dir)
        if latest is None:
            self.status_label.setText(f"Found {len(result_dirs)} result folder(s).")
            return
        self.status_label.setText(f"Found {len(result_dirs)} result folder(s). Latest: {latest}")

    def load_last_results(self) -> None:
        output_dir = self.state.parameters.get("computation", {}).get("output_directory", "_output")
        latest = latest_result_directory(self.state.project_dir, configured_output_dir=output_dir)
        if latest is None:
            QMessageBox.warning(
                self,
                "No results",
                "No AVAC result folder was found.\nRun a simulation first or pick a folder manually.",
            )
            return
        self.load_results_from_directory(latest)

    def pick_results_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select result directory", str(self.state.project_dir))
        if not selected:
            return
        self.load_results_from_directory(Path(selected))

    def load_results_from_directory(self, result_dir: Path) -> None:
        result_dir = Path(result_dir)
        if not result_dir.exists():
            QMessageBox.warning(self, "Missing folder", f"Result directory does not exist:\n{result_dir}")
            return

        rho = float(self.state.parameters.get("rheology", {}).get("rho", 300.0))
        try:
            fgmax = load_fgmax_results(result_dir, rho=rho)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Load failed", str(exc))
            return

        self.current_result_dir = result_dir
        self.result_topography = (fgmax.x, fgmax.y, fgmax.topography)
        self.loaded_rasters["depth"] = (fgmax.x, fgmax.y, fgmax.depth)
        self.loaded_rasters["velocity"] = (fgmax.x, fgmax.y, fgmax.velocity)
        self.loaded_rasters["pressure"] = (fgmax.x, fgmax.y, fgmax.pressure)
        self.active_kind = "depth"
        self.draw_map("depth")
        self.refresh_time_frame_list()
        self._auto_select_latest_animation()
        self.push_profile_layers_to_leaflet()
        self.last_profile_series = []
        self.last_profile_source = ""

        self.map_info.setText(f"Loaded maps from {result_dir}")
        self.status_label.setText(f"Loaded results: {result_dir}")

    def _auto_select_latest_animation(self) -> None:
        patterns = ("AVAC-animation-for-*.mp4", "AVAC_animation_for_*.mp4")
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(self.state.project_dir.glob(pattern))
        if not candidates:
            return
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        self._set_animation_path(latest)

    @staticmethod
    def _format_time_frame_label(frame_no: int, frame_time: float) -> str:
        if np.isfinite(frame_time):
            return f"Frame {frame_no:04d} | t={frame_time:.3f} s"
        return f"Frame {frame_no:04d}"

    def refresh_time_frame_list(self) -> None:
        self.time_frame_combo.blockSignals(True)
        self.time_frame_combo.clear()
        self.time_frame_combo.blockSignals(False)
        self.fgout_frames = []
        self.fgout_cache.clear()

        if self.current_result_dir is None:
            self.time_map_info.setText("Load results to populate fgout frames.")
            self.time_map_figure.clear()
            self.time_map_canvas.draw_idle()
            return

        frames = list_fgout_frames(self.current_result_dir, fgno=1)
        if not frames:
            self.time_map_info.setText(f"No fgout time frames found in {self.current_result_dir}.")
            self.time_map_figure.clear()
            self.time_map_canvas.draw_idle()
            return

        self.fgout_frames = [(item.frame_no, item.time) for item in frames]
        self.time_frame_combo.blockSignals(True)
        for frame_no, frame_time in self.fgout_frames:
            self.time_frame_combo.addItem(self._format_time_frame_label(frame_no, frame_time), frame_no)
        self.time_frame_combo.blockSignals(False)
        self.time_frame_combo.setCurrentIndex(0)
        self.time_map_info.setText(f"Loaded {len(self.fgout_frames)} fgout frames from {self.current_result_dir}.")
        self.draw_selected_time_map()

    def _on_time_controls_changed(self, *_args) -> None:
        self.draw_selected_time_map()

    def _selected_time_frame_no(self) -> int | None:
        if self.time_frame_combo.count() == 0:
            return None
        data = self.time_frame_combo.currentData()
        if data is None:
            return None
        try:
            return int(data)
        except (TypeError, ValueError):
            return None

    def _load_fgout_frame_cached(self, frame_no: int) -> FGoutFrameData:
        if frame_no in self.fgout_cache:
            return self.fgout_cache[frame_no]

        rho = float(self.state.parameters.get("rheology", {}).get("rho", 300.0))
        output_format = str(self.state.parameters.get("output", {}).get("output_format", "binary32"))
        if self.current_result_dir is None:
            raise ValueError("No result directory loaded.")

        frame_data = load_fgout_frame(
            self.current_result_dir,
            self.state.project_dir,
            frame_no,
            rho=rho,
            fgno=1,
            output_format=output_format,
        )
        self.fgout_cache[frame_no] = frame_data
        return frame_data

    def _draw_time_map(self, frame_data: FGoutFrameData, kind: str) -> None:
        z = {"depth": frame_data.depth, "velocity": frame_data.velocity, "pressure": frame_data.pressure}.get(kind, frame_data.depth)
        z_plot = np.asarray(z, dtype=float)
        topo_plot = np.asarray(frame_data.topography, dtype=float)
        x_plot = np.asarray(frame_data.x, dtype=float)
        y_plot = np.asarray(frame_data.y, dtype=float)

        if x_plot.ndim == 1 and y_plot.ndim == 1:
            if z_plot.shape == (x_plot.size, y_plot.size):
                z_plot = z_plot.T
                if topo_plot.shape == z_plot.T.shape:
                    topo_plot = topo_plot.T
            if z_plot.shape != (y_plot.size, x_plot.size):
                raise ValueError(
                    f"Incompatible fgout dimensions: z{z_plot.shape}, x{tuple(x_plot.shape)}, y{tuple(y_plot.shape)}"
                )
        elif x_plot.ndim == 2 and y_plot.ndim == 2:
            if x_plot.shape != z_plot.shape and x_plot.T.shape == z_plot.shape and y_plot.T.shape == z_plot.shape:
                x_plot = x_plot.T
                y_plot = y_plot.T
            if x_plot.shape != z_plot.shape or y_plot.shape != z_plot.shape:
                raise ValueError(
                    f"Incompatible fgout 2D grids: z{z_plot.shape}, X{tuple(x_plot.shape)}, Y{tuple(y_plot.shape)}"
                )
        else:
            raise ValueError(f"Unsupported fgout coordinate dimensions: x ndim {x_plot.ndim}, y ndim {y_plot.ndim}")

        if topo_plot.shape != z_plot.shape and topo_plot.T.shape == z_plot.shape:
            topo_plot = topo_plot.T

        self.time_map_figure.clear()
        ax = self.time_map_figure.add_subplot(111)
        im = ax.pcolormesh(
            x_plot,
            y_plot,
            z_plot,
            shading="auto",
            cmap={"depth": "Blues", "velocity": "magma", "pressure": "inferno"}.get(kind, "viridis"),
        )
        self.time_map_figure.colorbar(im, ax=ax, label=kind)
        try:
            ax.contour(x_plot, y_plot, topo_plot, levels=12, colors="black", alpha=0.25, linewidths=0.35)
        except ValueError:
            # Keep map display even if contour grid metadata is inconsistent.
            pass
        ax.set_title(f"{kind.capitalize()} at t={frame_data.time:.3f} s (frame {frame_data.frame_no:04d})")
        ax.set_aspect("equal")
        self.time_map_canvas.draw_idle()

    def draw_selected_time_map(self) -> None:
        frame_no = self._selected_time_frame_no()
        if frame_no is None:
            return
        kind = self.time_kind_combo.currentText().strip().lower()
        self.active_time_kind = kind
        try:
            frame_data = self._load_fgout_frame_cached(frame_no)
            self._draw_time_map(frame_data, kind)
            self.time_map_info.setText(f"Showing {kind} for frame {frame_no:04d} at t={frame_data.time:.3f} s.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Frame load failed", str(exc))

    def export_current_time_map_png(self) -> None:
        frame_no = self._selected_time_frame_no()
        if frame_no is None:
            QMessageBox.warning(self, "No frame", "No fgout frame is selected.")
            return
        self.draw_selected_time_map()

        kind = self.time_kind_combo.currentText().strip().lower()
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export current frame as PNG",
            str(self.state.project_dir / f"{kind}-frame{frame_no:04d}.png"),
            "PNG (*.png)",
        )
        if not selected:
            return
        self.time_map_figure.savefig(selected, dpi=300)
        self.time_map_info.setText(f"Exported current frame to {selected}.")

    def export_all_time_maps_png(self) -> None:
        if not self.fgout_frames:
            QMessageBox.warning(self, "No frames", "No fgout frames available. Load results first.")
            return
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "Select output directory for all PNG frames",
            str(self.state.project_dir),
        )
        if not target_dir:
            return

        out_dir = Path(target_dir)
        kind = self.time_kind_combo.currentText().strip().lower()
        original_index = self.time_frame_combo.currentIndex()

        saved_count = 0
        for index, (frame_no, _) in enumerate(self.fgout_frames):
            try:
                frame_data = self._load_fgout_frame_cached(frame_no)
                self._draw_time_map(frame_data, kind)
                output_file = out_dir / f"{kind}-frame{frame_no:04d}.png"
                self.time_map_figure.savefig(output_file, dpi=300)
                saved_count += 1
                self.time_map_info.setText(f"Exporting PNG frames: {index + 1}/{len(self.fgout_frames)}")
                QApplication.processEvents()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Export warning", f"Failed on frame {frame_no:04d}: {exc}")
                break

        if 0 <= original_index < self.time_frame_combo.count():
            self.time_frame_combo.setCurrentIndex(original_index)
            self.draw_selected_time_map()

        self.time_map_info.setText(f"Exported {saved_count} frame(s) to {out_dir}.")

    def show_map_or_prompt(self, kind: str) -> None:
        if kind in self.loaded_rasters:
            self.draw_map(kind)
            return
        self.load_raster(kind)

    def load_raster(self, kind: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, f"Load {kind} raster", str(self.state.project_dir), "ASCII (*.asc)")
        if not selected:
            return
        raster = read_ascii_raster(Path(selected))
        self.loaded_rasters[kind] = (raster.x, raster.y, raster.z)
        self.draw_map(kind)

    def draw_map(self, kind: str) -> None:
        if kind not in self.loaded_rasters:
            return
        self.active_kind = kind

        self.map_figure.clear()
        ax = self.map_figure.add_subplot(111)
        x, y, z = self.loaded_rasters[kind]
        im = ax.pcolormesh(
            x,
            y,
            z,
            shading="auto",
            cmap={"depth": "Blues", "velocity": "magma", "pressure": "inferno"}.get(kind, "viridis"),
        )
        self.map_figure.colorbar(im, ax=ax, label=kind)

        if self.result_topography is not None:
            tx, ty, tz = self.result_topography
            ax.contour(tx, ty, tz, levels=12, colors="black", alpha=0.25, linewidths=0.35)
        elif self.state.dem_path and self.state.dem_path.exists():
            dem = read_ascii_raster(self.state.dem_path)
            gy, gx = np.gradient(np.nan_to_num(dem.z, nan=np.nanmean(dem.z)))
            hs = np.sqrt(gx**2 + gy**2)
            ax.contour(dem.x, dem.y, hs, levels=6, colors="black", alpha=0.25, linewidths=0.4)

        title = f"Maximum {kind}"
        if self.current_result_dir is not None:
            title = f"{title} ({self.current_result_dir.name})"
        ax.set_title(title)
        ax.set_aspect("equal")
        self.map_canvas.draw_idle()

    def export_selected_raster(self) -> None:
        if not self.loaded_rasters:
            QMessageBox.information(self, "No raster", "Load results or a raster first.")
            return
        key = self.active_kind or list(self.loaded_rasters.keys())[-1]
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export raster",
            str(self.state.project_dir / f"{key}-max-export.asc"),
            "ASCII (*.asc)",
        )
        if not selected:
            return
        x, y, z = self.loaded_rasters[key]
        ncols = z.shape[1]
        nrows = z.shape[0]
        if x.shape[0] > 1:
            cellsize = float(np.median(np.diff(x)))
        elif y.shape[0] > 1:
            cellsize = float(np.median(np.diff(y)))
        else:
            cellsize = 1.0
        header = [
            f"ncols {ncols}",
            f"nrows {nrows}",
            f"xllcorner {x[0]}",
            f"yllcorner {y[0]}",
            f"cellsize {cellsize}",
            "NODATA_value -9999",
        ]
        arr = np.where(np.isnan(z), -9999, z[::-1, :])
        with open(selected, "w", encoding="utf-8") as handle:
            handle.write("\n".join(header) + "\n")
            np.savetxt(handle, arr, fmt="%.4f")

    def load_profile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Load profile file", str(self.state.project_dir), "Text (*.txt *.dat)")
        if not selected:
            return
        data = np.loadtxt(selected)
        if data.ndim == 1 or data.shape[1] < 2:
            QMessageBox.warning(self, "Invalid file", "Profile file must have at least two columns.")
            return
        self.profile_figure.clear()
        ax = self.profile_figure.add_subplot(111)
        ax.plot(data[:, 0], data[:, 1], lw=1.5)
        ax.set_xlabel("Distance")
        ax.set_ylabel("Value")
        ax.grid(True, alpha=0.3)
        self.profile_canvas.draw_idle()

    def _default_profile_path(self) -> Path | None:
        if self.state.profile_path and self.state.profile_path.exists():
            return self.state.profile_path
        candidate = self.state.project_dir / "profil.shp"
        return candidate if candidate.exists() else None

    def _resolve_profile_frame_source(self, silent: bool = False):
        if gpd is None:
            if not silent:
                QMessageBox.warning(self, "Missing dependency", "geopandas is required to compute profile data.")
            return None

        if self.profile_vector is not None and len(self.profile_vector) > 0:
            return self.profile_vector, "drawn profiles"

        profile_path = self._default_profile_path()
        if profile_path is None:
            if not silent:
                QMessageBox.warning(
                    self,
                    "Missing profile",
                    "No drawn profiles are available and no saved profile shapefile was found.",
                )
            return None

        try:
            frame = gpd.read_file(profile_path)
        except Exception as exc:  # noqa: BLE001
            if not silent:
                self.profile_status.setText(f"Profile load failed: {exc}")
                QMessageBox.critical(self, "Profile error", str(exc))
            return None

        return frame, str(profile_path)

    def _extract_profile_coord_sets(self, frame) -> list[np.ndarray]:
        coord_sets: list[np.ndarray] = []
        if frame is None or len(frame) == 0:
            return coord_sets

        for geom in frame.geometry:
            if geom is None or geom.is_empty:
                continue

            if geom.geom_type == "LineString":
                coords = np.asarray(geom.coords, dtype=float)
                if coords.ndim == 2 and coords.shape[0] >= 2:
                    coord_sets.append(coords)
                continue

            if geom.geom_type == "MultiLineString":
                for line in geom.geoms:
                    coords = np.asarray(line.coords, dtype=float)
                    if coords.ndim == 2 and coords.shape[0] >= 2:
                        coord_sets.append(coords)

        return coord_sets

    def _sample_polyline(self, profile_coords: np.ndarray, num_points: int = 1000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        segments = np.diff(profile_coords, axis=0)
        lengths = np.sqrt(np.sum(segments**2, axis=1))
        cumulative = np.insert(np.cumsum(lengths), 0, 0.0)
        total_length = cumulative[-1]
        sample_distances = np.linspace(0.0, total_length, num_points)

        sample_points = []
        for dist in sample_distances:
            idx = np.searchsorted(cumulative, dist, side="right") - 1
            idx = min(max(0, idx), len(segments) - 1)
            segment_start = cumulative[idx]
            if lengths[idx] <= 0:
                point = profile_coords[idx]
            else:
                frac = (dist - segment_start) / lengths[idx]
                point = profile_coords[idx] + frac * segments[idx]
            sample_points.append(point)
        sample_points_arr = np.asarray(sample_points, dtype=float)
        return sample_distances, sample_points_arr[:, 0], sample_points_arr[:, 1]

    def _sample_regular_grid(self, x: np.ndarray, y: np.ndarray, z: np.ndarray, xq: np.ndarray, yq: np.ndarray) -> np.ndarray:
        if x.size < 2 or y.size < 2:
            return np.full_like(xq, np.nan, dtype=float)

        ix = np.searchsorted(x, xq, side="right") - 1
        iy = np.searchsorted(y, yq, side="right") - 1
        ix = np.clip(ix, 0, x.size - 2)
        iy = np.clip(iy, 0, y.size - 2)

        x1 = x[ix]
        x2 = x[ix + 1]
        y1 = y[iy]
        y2 = y[iy + 1]
        tx = np.where(x2 != x1, (xq - x1) / (x2 - x1), 0.0)
        ty = np.where(y2 != y1, (yq - y1) / (y2 - y1), 0.0)

        z11 = z[iy, ix]
        z21 = z[iy, ix + 1]
        z12 = z[iy + 1, ix]
        z22 = z[iy + 1, ix + 1]
        sampled = (
            (1 - tx) * (1 - ty) * z11
            + tx * (1 - ty) * z21
            + (1 - tx) * ty * z12
            + tx * ty * z22
        )
        return sampled

    def _coerce_profile_frame_to_grid_crs(self, frame):
        if gpd is None or frame is None or len(frame) == 0:
            return frame
        if frame.crs is None:
            return frame

        try:
            x, y, _ = self.loaded_rasters["depth"]
        except KeyError:
            return frame

        x_min = float(np.nanmin(x)) if np.size(x) else np.nan
        x_max = float(np.nanmax(x)) if np.size(x) else np.nan
        y_min = float(np.nanmin(y)) if np.size(y) else np.nan
        y_max = float(np.nanmax(y)) if np.size(y) else np.nan

        grid_is_geo = (
            np.isfinite([x_min, x_max, y_min, y_max]).all()
            and -180.0 <= x_min <= 180.0
            and -180.0 <= x_max <= 180.0
            and -90.0 <= y_min <= 90.0
            and -90.0 <= y_max <= 90.0
        )
        target_crs = "EPSG:4326" if grid_is_geo else self._effective_dem_crs()

        if target_crs and str(frame.crs).upper() != str(target_crs).upper():
            return frame.to_crs(target_crs)
        return frame

    def _compute_profile_series_from_frame(self, frame) -> list[dict[str, np.ndarray]]:
        if gpd is None:
            raise ValueError("geopandas is required to compute profiles from shapefiles.")
        if "depth" not in self.loaded_rasters or "velocity" not in self.loaded_rasters or "pressure" not in self.loaded_rasters:
            raise ValueError("Load simulation results first.")

        frame_for_plot = self._coerce_profile_frame_to_grid_crs(frame)
        coord_sets = self._extract_profile_coord_sets(frame_for_plot)
        if not coord_sets:
            raise ValueError("No valid polyline found in profile data.")

        x, y, depth = self.loaded_rasters["depth"]
        _, _, velocity = self.loaded_rasters["velocity"]

        dem_extent = None
        config_path = self.state.project_dir / "AVAC_configuration.yaml"
        if config_path.exists():
            config_data = read_yaml(config_path)
            dem_extent = config_data.get("dem_extent")
        x_profile, y_profile = derive_notebook_profile_axes(x, y, dem_extent)

        rho = float(self.state.parameters.get("rheology", {}).get("rho", 300.0))
        pressure_notebook = derive_notebook_pressure_field(depth, velocity, rho)

        profile_series: list[dict[str, np.ndarray]] = []
        for coords in coord_sets:
            distance, xq, yq = self._sample_polyline(coords, num_points=1000)
            depth_profile = self._sample_regular_grid(x_profile, y_profile, depth, xq, yq)
            velocity_profile = self._sample_regular_grid(x_profile, y_profile, velocity, xq, yq)
            pressure_profile = self._sample_regular_grid(x_profile, y_profile, pressure_notebook, xq, yq)
            profile_series.append(
                {
                    "distance": distance,
                    "x": xq,
                    "y": yq,
                    "velocity": velocity_profile,
                    "pressure": pressure_profile,
                    "depth": depth_profile,
                }
            )
        return profile_series

    def compute_profiles_from_frame(self, frame, source_label: str, silent: bool = False) -> None:
        try:
            profile_series = self._compute_profile_series_from_frame(frame)
        except Exception as exc:  # noqa: BLE001
            if not silent:
                self.profile_status.setText(f"Profile plotting failed: {exc}")
                QMessageBox.critical(self, "Profile error", str(exc))
            return

        self.last_profile_series = profile_series
        self.last_profile_source = source_label

        overlay_mode = bool(getattr(self, "profile_overlay_checkbox", None) and self.profile_overlay_checkbox.isChecked())
        cmap = cm.get_cmap("tab10")
        self.profile_figure.clear()

        if overlay_mode:
            ax1 = self.profile_figure.add_subplot(311)
            ax2 = self.profile_figure.add_subplot(312, sharex=ax1)
            ax3 = self.profile_figure.add_subplot(313, sharex=ax1)

            for idx, series in enumerate(profile_series):
                color = cmap(idx % 10)
                label = f"P{idx + 1}"
                ax1.plot(series["distance"], series["velocity"], lw=1.2, color=color, label=label)
                ax2.plot(series["distance"], series["depth"], lw=1.2, color=color, label=label)
                ax3.plot(series["distance"], series["pressure"], lw=1.2, color=color, label=label)

            ax1.set_ylabel("Velocity (m/s)")
            ax1.grid(True, alpha=0.3)
            ax2.set_ylabel("Depth (m)")
            ax2.grid(True, alpha=0.3)
            ax3.set_ylabel("Pressure (kPa)")
            ax3.set_xlabel("Distance along profile (m)")
            ax3.grid(True, alpha=0.3)

            if len(profile_series) > 1:
                ax1.legend(loc="best", fontsize=8, ncols=min(4, len(profile_series)))
        else:
            n_profiles = len(profile_series)
            axes = self.profile_figure.subplots(n_profiles, 3, squeeze=False)
            titles = ["Velocity (m/s)", "Depth (m)", "Pressure (kPa)"]
            for col, title in enumerate(titles):
                axes[0, col].set_title(title)

            for idx, series in enumerate(profile_series):
                color = cmap(idx % 10)
                label = f"P{idx + 1}"
                ax_v = axes[idx, 0]
                ax_d = axes[idx, 1]
                ax_p = axes[idx, 2]

                ax_v.plot(series["distance"], series["velocity"], lw=1.2, color=color)
                ax_d.plot(series["distance"], series["depth"], lw=1.2, color=color)
                ax_p.plot(series["distance"], series["pressure"], lw=1.2, color=color)

                ax_v.set_ylabel(f"{label}\nVel")
                ax_d.set_ylabel("Depth")
                ax_p.set_ylabel("Press")

                ax_v.grid(True, alpha=0.3)
                ax_d.grid(True, alpha=0.3)
                ax_p.grid(True, alpha=0.3)

            for col in range(3):
                axes[-1, col].set_xlabel("Distance along profile (m)")

        self.profile_canvas.draw_idle()
        mode_label = "overlay mode" if overlay_mode else "separate-profile mode"
        self.profile_status.setText(f"Plotted {len(profile_series)} profile(s) from {source_label} ({mode_label}).")

    def compute_profiles_from_shapefile(self, silent: bool = False) -> None:
        if gpd is None:
            if not silent:
                QMessageBox.warning(self, "Missing dependency", "geopandas is required to compute profiles from shapefiles.")
            return

        profile_path = self._default_profile_path()
        if profile_path is None:
            if not silent:
                QMessageBox.warning(self, "Missing profile", "No profile shapefile found (expected profil.shp).")
            return

        try:
            frame = gpd.read_file(profile_path)
        except Exception as exc:  # noqa: BLE001
            if not silent:
                self.profile_status.setText(f"Profile load failed: {exc}")
                QMessageBox.critical(self, "Profile error", str(exc))
            return

        self.compute_profiles_from_frame(frame, source_label=str(profile_path), silent=silent)

    @staticmethod
    def _process_environment_from_dict(mapping: dict[str, str]) -> QProcessEnvironment:
        env = QProcessEnvironment()
        for key, value in mapping.items():
            env.insert(str(key), str(value))
        return env

    def _selected_mp4_path(self) -> Path | None:
        path_text = self.animation_path.text().strip()
        if not path_text or path_text == "No MP4 selected":
            return None
        candidate = Path(path_text)
        return candidate if candidate.exists() and candidate.suffix.lower() == ".mp4" else None

    def _set_animation_path(self, path: Path) -> None:
        self.animation_path.setText(str(path))

    def _resolve_result_dir_for_animation(self) -> Path | None:
        if self.current_result_dir is not None and self.current_result_dir.exists():
            return self.current_result_dir
        configured = self.state.parameters.get("computation", {}).get("output_directory", "_output")
        return latest_result_directory(self.state.project_dir, configured_output_dir=configured)

    def generate_animation(self) -> None:
        if self.animation_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "Animation running", "Animation generation is already running.")
            return

        result_dir = self._resolve_result_dir_for_animation()
        if result_dir is None:
            QMessageBox.warning(self, "Missing results", "No result directory found. Run a simulation first.")
            return
        if not any(result_dir.glob("fgout*.t*")):
            QMessageBox.warning(self, "Missing fgout", f"No fgout time files found in:\n{result_dir}")
            return

        script_path = self.state.project_dir / "make_fgout_animation.py"
        if not script_path.exists():
            QMessageBox.warning(self, "Missing script", f"Animation script not found:\n{script_path}")
            return

        variable = self.animation_variable.currentText().strip().lower()
        fps = int(self.animation_fps.value())
        prefix = (self.state.project_dir / f"AVAC-animation-for-{variable}").resolve()
        self._pending_animation_prefix = prefix
        self._animation_was_stopped = False

        self.animation_log.clear()
        self.animation_log.append(f"Generating animation for '{variable}' at {fps} FPS")
        self.animation_log.append(f"Using result directory: {result_dir}")
        self.animation_status.setText("Animation generation in progress...")
        self.animation_generate_btn.setEnabled(False)
        self.animation_stop_btn.setEnabled(True)

        env = build_local_claw_env(
            os.environ.copy(),
            self.state.project_dir,
            python_executable=sys.executable,
        )
        self.animation_process.setWorkingDirectory(str(self.state.project_dir))
        self.animation_process.setProcessEnvironment(self._process_environment_from_dict(env))
        args = [
            str(script_path),
            "--variable",
            variable,
            "--fps",
            str(fps),
            "--outdir",
            str(result_dir),
            "--output-prefix",
            str(prefix),
        ]
        self.animation_process.start(sys.executable, args)
        if not self.animation_process.waitForStarted(3000):
            self.animation_generate_btn.setEnabled(True)
            self.animation_stop_btn.setEnabled(False)
            self.animation_status.setText("Failed to start animation process.")
            QMessageBox.critical(self, "Start failed", "Could not start animation generation process.")

    def stop_animation_generation(self) -> None:
        if self.animation_process.state() == QProcess.ProcessState.NotRunning:
            return
        self._animation_was_stopped = True
        self.animation_process.kill()
        self.animation_status.setText("Animation generation stopped.")
        self.animation_generate_btn.setEnabled(True)
        self.animation_stop_btn.setEnabled(False)

    def _read_animation_stdout(self) -> None:
        text = bytes(self.animation_process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        if text:
            self.animation_log.insertPlainText(text)
            self.animation_log.ensureCursorVisible()

    def _read_animation_stderr(self) -> None:
        text = bytes(self.animation_process.readAllStandardError()).decode("utf-8", errors="ignore")
        if text:
            self.animation_log.insertPlainText(text)
            self.animation_log.ensureCursorVisible()

    def _on_animation_finished(self, exit_code: int, _exit_status) -> None:
        self.animation_generate_btn.setEnabled(True)
        self.animation_stop_btn.setEnabled(False)

        log_path = self.state.project_dir / "animation.log"
        log_path.write_text(self.animation_log.toPlainText(), encoding="utf-8")

        if self._animation_was_stopped:
            self.animation_status.setText("Animation generation stopped.")
            return

        if exit_code != 0:
            self.animation_status.setText(f"Animation failed (exit code {exit_code}).")
            QMessageBox.critical(self, "Animation failed", f"Animation process failed. See:\n{log_path}")
            return

        prefix = self._pending_animation_prefix
        if prefix is None:
            self.animation_status.setText("Animation completed.")
            return

        mp4_path = prefix.with_suffix(".mp4")
        html_path = prefix.with_suffix(".html")
        if mp4_path.exists():
            self._set_animation_path(mp4_path)
            self.animation_status.setText(f"Animation ready: {mp4_path.name}")
            if html_path.exists():
                self.animation_log.append(f"HTML generated: {html_path.name}")
        else:
            self.animation_status.setText("Animation completed, but no output file was found.")
            QMessageBox.warning(self, "Missing output", f"No animation file found for prefix:\n{prefix}")

    def open_animation(self) -> None:
        mp4_path = self._selected_mp4_path()
        if mp4_path is None:
            QMessageBox.information(self, "No MP4", "No MP4 animation is available.")
            return
        if self._open_in_default_player(mp4_path):
            return
        QMessageBox.warning(
            self,
            "Open failed",
            "Could not find a system launcher for this MP4.\n"
            f"File: {mp4_path}",
        )

    @staticmethod
    def _is_wsl() -> bool:
        if os.name != "posix":
            return False
        try:
            return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            return False

    def _open_in_default_player(self, path: Path) -> bool:
        if self._is_wsl():
            try:
                win_path = subprocess.run(
                    ["wslpath", "-w", str(path)],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                if win_path:
                    escaped = win_path.replace("'", "''")
                    subprocess.Popen(
                        ["powershell.exe", "-NoProfile", "-Command", f"Start-Process -FilePath '{escaped}'"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
            except OSError:
                pass
            except subprocess.SubprocessError:
                pass

        url = QUrl.fromLocalFile(str(path))
        if QDesktopServices.openUrl(url):
            return True

        launchers = [["xdg-open", str(path)], ["gio", "open", str(path)]]
        if self._is_wsl():
            launchers.insert(0, ["wslview", str(path)])

        for launcher in launchers:
            try:
                result = subprocess.run(
                    launcher,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=8,
                )
                if result.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
            except (OSError, subprocess.SubprocessError):
                continue

        return False
