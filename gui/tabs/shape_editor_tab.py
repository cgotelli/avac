from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.cm as cm
import numpy as np
from PIL import Image
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from shapely.geometry import box

from gui.services import read_ascii_raster
from gui.shape_services import export_vector, load_vector, save_vector
from gui.state import AppState

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


LEAFLET_EDITOR_HTML = """<!doctype html>
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
  <div class=\"help\">Draw/Edit/Delete starting areas directly on the map.</div>
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
        let demImageLayer = null;
        let demBounds = null;

    map.addLayer(drawLayer);

    const drawControl = new L.Control.Draw({
      draw: {
        polygon: true,
        polyline: false,
        rectangle: true,
        circle: false,
        marker: false,
        circlemarker: false
      },
      edit: { featureGroup: drawLayer }
    });
    map.addControl(drawControl);

    let host = null;

        function isReasonableBounds(b) {
            if (!b || !b.isValid()) {
                return false;
            }
            const spanLat = Math.abs(b.getNorth() - b.getSouth());
            const spanLng = Math.abs(b.getEast() - b.getWest());
            return spanLat > 0 && spanLng > 0 && spanLat < 20 && spanLng < 20;
        }

        function fitToData() {
                        if (demBounds && isReasonableBounds(demBounds)) {
                    map.fitBounds(demBounds, { padding: [0, 0], animate: false });
                return;
      }
                        const b = drawLayer.getBounds();
                        if (isReasonableBounds(b)) {
                    map.fitBounds(b, { padding: [0, 0], animate: false });
                        }
    }

    function emitGeoJsonToHost() {
      if (!host || !host.pushGeoJson) {
        return;
      }
      host.pushGeoJson(JSON.stringify(drawLayer.toGeoJSON()));
    }

    function loadGeoJson(featureCollection) {
      drawLayer.clearLayers();
      if (featureCollection && featureCollection.features) {
        L.geoJSON(featureCollection, {
          style: { color: '#0f766e', weight: 2, fillOpacity: 0.35 },
          onEachFeature: function (feature, layer) {
            if (feature && feature.properties && feature.properties.feature_name) {
              layer.bindTooltip(String(feature.properties.feature_name));
            }
            drawLayer.addLayer(layer);
          }
        });
      }
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

    window.loadGeoJson = loadGeoJson;
        window.loadDemRaster = loadDemRaster;

    map.on(L.Draw.Event.CREATED, function (e) {
      drawLayer.addLayer(e.layer);
      emitGeoJsonToHost();
    });
    map.on(L.Draw.Event.EDITED, emitGeoJsonToHost);
    map.on(L.Draw.Event.DELETED, emitGeoJsonToHost);

        new QWebChannel(qt.webChannelTransport, function (channel) {
      host = channel.objects.bridge;
      setTimeout(function () { map.invalidateSize(); fitToData(); }, 50);
    });
  </script>
</body>
</html>
"""


class LeafletBridge(QObject):
    geojson_received = pyqtSignal(str)

    @pyqtSlot(str)
    def pushGeoJson(self, payload: str) -> None:
        self.geojson_received.emit(payload)


def _empty_frame(crs: Any = "EPSG:4326") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(data={"feature_name": []}, geometry=[], crs=crs)


class ShapeEditorTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.vector: gpd.GeoDataFrame | None = None
        self.current_path: Path | None = None
        self.web_supported = bool(QWebEngineView and QWebChannel)
        self.webengine_disabled = WEBENGINE_DISABLED
        self.leaflet_bridge: LeafletBridge | None = None
        self.web_view: Any | None = None
        self._leaflet_loaded = False

        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.path_label = QLabel("No shapefile loaded")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        load_btn = QPushButton("Load Shapefile")
        save_btn = QPushButton("Save")
        save_as_btn = QPushButton("Save As")
        export_btn = QPushButton("Export GeoJSON")

        load_btn.clicked.connect(self.load_shapefile)
        save_btn.clicked.connect(self.save_current)
        save_as_btn.clicked.connect(self.save_as)
        export_btn.clicked.connect(self.export_current)

        top.addWidget(load_btn)
        top.addWidget(save_btn)
        top.addWidget(save_as_btn)
        top.addWidget(export_btn)
        top.addStretch(1)

        root.addLayout(top)
        root.addWidget(self.path_label)

        if self.web_supported:
            self.web_view = QWebEngineView()
            self.leaflet_bridge = LeafletBridge()
            self.leaflet_bridge.geojson_received.connect(self.apply_geojson_from_leaflet)

            channel = QWebChannel(self.web_view.page())
            channel.registerObject("bridge", self.leaflet_bridge)
            self.web_view.page().setWebChannel(channel)
            self.web_view.loadFinished.connect(self._on_leaflet_loaded)
            self.web_view.setHtml(LEAFLET_EDITOR_HTML)
            root.addWidget(self.web_view, 1)
        else:
            fallback = QWidget()
            fallback_layout = QVBoxLayout(fallback)
            message = "Leaflet editor is unavailable because PyQt6-WebEngine is not installed."
            if self.webengine_disabled:
                message = (
                    "Leaflet editor is disabled by AVAC_DISABLE_WEBENGINE=1 "
                    "for compatibility on this system."
                )
            fallback_layout.addWidget(QLabel(message))
            root.addWidget(fallback, 1)

        self.status = QLabel("Load a shapefile to edit features.")
        root.addWidget(self.status)

        self.state.changed.connect(self.sync_from_state)
        self.sync_from_state()

    def _effective_starting_areas_path(self) -> Path | None:
        if self.state.starting_areas_path and self.state.starting_areas_path.exists():
            return self.state.starting_areas_path
        return None

    def _effective_dem_path(self) -> Path | None:
        if self.state.dem_path and self.state.dem_path.exists():
            return self.state.dem_path
        return None

    def _effective_vector_crs(self) -> Any:
        if self.vector is not None and self.vector.crs is not None:
            return self.vector.crs

        candidate = self._effective_starting_areas_path()
        if candidate is not None:
            try:
                return load_vector(candidate).crs or "EPSG:4326"
            except Exception:  # noqa: BLE001
                return "EPSG:4326"
        return "EPSG:4326"

    def _guess_crs_from_bounds(self, xmin: float, xmax: float, ymin: float, ymax: float) -> str:
        if abs(float(xmin)) > 180.0 or abs(float(xmax)) > 180.0 or abs(float(ymin)) > 90.0 or abs(float(ymax)) > 90.0:
            return "EPSG:2154"
        return "EPSG:4326"

    def _effective_dem_crs(self) -> Any:
        dem = self._effective_dem_path()
        if dem is None:
            return "EPSG:4326"
        try:
            m = read_ascii_raster(dem).metadata
            return self._guess_crs_from_bounds(m.get("xmin", 0.0), m.get("xmax", 0.0), m.get("ymin", 0.0), m.get("ymax", 0.0))
        except Exception:  # noqa: BLE001
            return "EPSG:4326"

    def _effective_project_crs(self) -> Any:
        vector_crs = self._effective_vector_crs()
        dem_crs = self._effective_dem_crs()

        if vector_crs is not None and str(vector_crs).upper() != "EPSG:4326":
            return vector_crs
        if dem_crs is not None and str(dem_crs).upper() != "EPSG:4326":
            return dem_crs
        return vector_crs or dem_crs or "EPSG:4326"

    def _alignment_message(self) -> str:
        dem_path = self._effective_dem_path()
        if dem_path is None or self.vector is None or len(self.vector) == 0:
            return ""

        dem_crs = self._effective_dem_crs()
        vector_crs = self._effective_vector_crs()

        try:
            m = read_ascii_raster(dem_path).metadata
            dem_frame = gpd.GeoDataFrame(
                [{"geometry": box(m["xmin"], m["ymin"], m["xmax"], m["ymax"])}],
                geometry="geometry",
                crs=dem_crs,
            )
            dem_wgs = dem_frame.to_crs("EPSG:4326")

            vec = self.vector
            if vec.crs is None:
                vec = vec.set_crs(self._effective_project_crs(), allow_override=True)
            vec_wgs = vec.to_crs("EPSG:4326")

            dminx, dminy, dmaxx, dmaxy = dem_wgs.total_bounds
            vminx, vminy, vmaxx, vmaxy = vec_wgs.total_bounds
            overlap_x = min(dmaxx, vmaxx) - max(dminx, vminx)
            overlap_y = min(dmaxy, vmaxy) - max(dminy, vminy)

            if overlap_x <= 0 or overlap_y <= 0:
                return f"Warning: DEM ({dem_crs}) and areas ({vector_crs}) appear misaligned after reprojection."
            return f"CRS check OK: DEM {dem_crs}, areas {vector_crs}."
        except Exception:  # noqa: BLE001
            return f"Warning: Could not verify DEM/areas alignment. DEM {dem_crs}, areas {vector_crs}."

    def sync_from_state(self) -> None:
        candidate = self._effective_starting_areas_path()
        if not candidate:
            self.current_path = None
            self.vector = _empty_frame(crs=self._effective_vector_crs())
            self.path_label.setText("No shapefile loaded")
            self.refresh_table_and_map()
            self.status.setText("No starting areas file selected.")
            return

        try:
            self.vector = load_vector(candidate)
            self.current_path = candidate
            self.path_label.setText(str(candidate))
            self.refresh_table_and_map()
            msg = self._alignment_message()
            suffix = f" {msg}" if msg else ""
            self.status.setText(f"Loaded {len(self.vector)} features from state.{suffix}")
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Failed to load starting areas from state: {exc}")

    def load_shapefile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Load shapefile",
            str(self.state.project_dir),
            "Shapefiles (*.shp)",
        )
        if not selected:
            return
        try:
            path = Path(selected)
            self.vector = load_vector(path)
            self.current_path = path
            self.path_label.setText(str(path))
            self.state.set_paths(starting_areas=path)
            self.refresh_table_and_map()
            msg = self._alignment_message()
            suffix = f" {msg}" if msg else ""
            self.status.setText(f"Loaded {len(self.vector)} features.{suffix}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Load failed", str(exc))

    def save_current(self) -> None:
        if self.vector is None or self.current_path is None:
            QMessageBox.warning(self, "No data", "No shapefile loaded.")
            return
        try:
            save_vector(self.vector, self.current_path)
            self.status.setText(f"Saved {self.current_path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))

    def save_as(self) -> None:
        if self.vector is None:
            QMessageBox.warning(self, "No data", "No shapefile loaded.")
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save shapefile as",
            str(self.state.project_dir / "ZA_edited.shp"),
            "Shapefiles (*.shp)",
        )
        if not selected:
            return
        try:
            path = Path(selected)
            save_vector(self.vector, path)
            self.current_path = path
            self.path_label.setText(str(path))
            self.state.set_paths(starting_areas=path)
            self.status.setText(f"Saved {path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))

    def export_current(self) -> None:
        if self.vector is None:
            QMessageBox.warning(self, "No data", "No shapefile loaded.")
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export GeoJSON",
            str(self.state.project_dir / "ZA_edited.geojson"),
            "GeoJSON (*.geojson)",
        )
        if not selected:
            return
        try:
            export_vector(self.vector, Path(selected))
            self.status.setText(f"Exported {selected}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))

    def apply_geojson_from_leaflet(self, payload: str) -> None:
        try:
            parsed = json.loads(payload)
            features = parsed.get("features", []) if isinstance(parsed, dict) else []
            crs = self._effective_project_crs()

            if features:
                updated = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
                if crs is not None and str(crs).upper() != "EPSG:4326":
                    updated = updated.to_crs(crs)
            else:
                updated = _empty_frame(crs=crs)

            if "feature_name" not in updated.columns:
                updated["feature_name"] = [f"feature_{i + 1}" for i in range(len(updated))]

            self.vector = updated.reset_index(drop=True)
            msg = self._alignment_message()
            suffix = f" {msg}" if msg else ""
            self.status.setText(f"Leaflet edit applied ({len(self.vector)} features).{suffix}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Leaflet sync failed", str(exc))

    def _on_leaflet_loaded(self, ok: bool) -> None:
        self._leaflet_loaded = bool(ok)
        if ok:
            self.push_current_layers_to_leaflet()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self.web_view and self._leaflet_loaded:
            # Re-sync once the tab is visible so Leaflet computes fitBounds from real widget size.
            self.push_current_layers_to_leaflet()

    def _run_leaflet_geojson(self, function_name: str, payload_json: str) -> None:
        if not self.web_view or not self._leaflet_loaded:
            return
        script = f"window.{function_name}(JSON.parse({json.dumps(payload_json)}));"
        self.web_view.page().runJavaScript(script)

    def _vector_for_leaflet_json(self) -> str:
        if self.vector is None or len(self.vector) == 0:
            return '{"type":"FeatureCollection","features":[]}'
        frame = self.vector
        if frame.crs is None:
            frame = frame.set_crs(self._effective_project_crs(), allow_override=True)
        if frame.crs is not None and str(frame.crs).upper() != "EPSG:4326":
            frame = frame.to_crs("EPSG:4326")
        return frame.to_json(drop_id=True)

    def _dem_bounds_for_leaflet_json(self) -> str:
        dem_path = self._effective_dem_path()
        if dem_path is None:
            return "{}"

        try:
            raster = read_ascii_raster(dem_path)
            m = raster.metadata
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
            hs = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
            hs = np.clip((hs + 1.0) * 0.5, 0.0, 1.0)

            rgb = np.clip(terrain_rgb * 0.72 + hs[..., None] * 0.28, 0.0, 1.0)

            rgba = np.zeros((z.shape[0], z.shape[1], 4), dtype=np.uint8)
            rgba[..., 0:3] = (rgb * 255.0).astype(np.uint8)
            rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)

            # Leaflet image overlays are anchored from north-west; flip array so DEM is not north/south mirrored.
            rgba = np.flipud(rgba)

            image = Image.fromarray(rgba, mode="RGBA")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            payload_image = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

            dem_crs = self._effective_dem_crs()
            dem_frame = gpd.GeoDataFrame(
                [{"geometry": box(m["xmin"], m["ymin"], m["xmax"], m["ymax"])}],
                geometry="geometry",
                crs=dem_crs,
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

    def push_current_layers_to_leaflet(self) -> None:
        if not self.web_view:
            return
        self._run_leaflet_geojson("loadDemRaster", self._dem_bounds_for_leaflet_json())
        self._run_leaflet_geojson("loadGeoJson", self._vector_for_leaflet_json())

    def refresh_table_and_map(self, select_row: int | None = None) -> None:  # noqa: ARG002
        self.push_current_layers_to_leaflet()
