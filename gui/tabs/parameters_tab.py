from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from gui.services import read_ascii_raster, read_yaml, write_yaml
from gui.state import AppState, DEFAULT_PARAMETERS

try:
    import geopandas as gpd
    from matplotlib.path import Path as MplPath
except Exception:  # noqa: BLE001
    gpd = None
    MplPath = None


class ParametersTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.widgets: dict[str, QWidget] = {}

        root = QVBoxLayout(self)
        top_row = QHBoxLayout()

        self.toolbox = QToolBox()
        self.toolbox.addItem(self._build_release_group(), "Release")
        self.toolbox.addItem(self._build_rheology_group(), "Rheology")
        self.toolbox.addItem(self._build_computation_group(), "Computation")
        self.toolbox.addItem(self._build_output_group(), "Output")

        top_row.addWidget(self.toolbox, 2)

        preview_box = QGroupBox("Initial depth preview")
        preview_layout = QVBoxLayout(preview_box)
        self.figure = Figure(figsize=(5, 4), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        preview_layout.addWidget(self.canvas)

        top_row.addWidget(preview_box, 3)
        root.addLayout(top_row)

        io_row = QHBoxLayout()
        load_btn = QPushButton("Load YAML")
        save_btn = QPushButton("Save as YAML")
        validate_btn = QPushButton("Validate")

        load_btn.clicked.connect(self.load_yaml)
        save_btn.clicked.connect(self.save_yaml)
        validate_btn.clicked.connect(self.validate)

        io_row.addWidget(load_btn)
        io_row.addWidget(save_btn)
        io_row.addWidget(validate_btn)
        io_row.addStretch(1)

        root.addLayout(io_row)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        root.addWidget(self.validation_label)

        self.state.changed.connect(self.pull_from_state)
        self.pull_from_state()

    def _register(self, key: str, widget: QWidget) -> QWidget:
        self.widgets[key] = widget
        return widget

    def _build_release_group(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)

        d0 = self._register("release.d0", QDoubleSpinBox())
        d0.setRange(0.0, 10.0)
        d0.setSingleStep(0.05)
        d0.valueChanged.connect(self.push_to_state)

        theta = self._register("release.theta_cr", QDoubleSpinBox())
        theta.setRange(0.0, 60.0)
        theta.setSingleStep(0.5)
        theta.valueChanged.connect(self.push_to_state)

        grad = self._register("release.gradient_hypso", QDoubleSpinBox())
        grad.setRange(0.0, 0.2)
        grad.setSingleStep(0.005)
        grad.valueChanged.connect(self.push_to_state)

        zref = self._register("release.z_ref", QSpinBox())
        zref.setRange(0, 9000)
        zref.valueChanged.connect(self.push_to_state)

        period = self._register("release.period_return", QComboBox())
        period.addItems(["100", "300"])
        period.currentTextChanged.connect(self.push_to_state)

        corr_slope = self._register("release.correction_slope", QCheckBox("Enable slope correction"))
        corr_slope.stateChanged.connect(self.push_to_state)

        corr_elev = self._register("release.correction_elevation", QCheckBox("Enable elevation correction"))
        corr_elev.stateChanged.connect(self.push_to_state)

        form.addRow("d0 [m]", d0)
        form.addRow("theta_cr [deg]", theta)
        form.addRow("gradient_hypso", grad)
        form.addRow("z_ref [m]", zref)
        form.addRow("Return period", period)
        form.addRow(corr_slope)
        form.addRow(corr_elev)
        return container

    def _build_rheology_group(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)

        model = self._register("rheology.model", QComboBox())
        model.addItems(["Voellmy", "Coulomb"])
        model.currentTextChanged.connect(self.push_to_state)

        mu = self._register("rheology.mu", QDoubleSpinBox())
        mu.setRange(0.05, 0.5)
        mu.setSingleStep(0.01)
        mu.valueChanged.connect(self.push_to_state)

        xi = self._register("rheology.xi", QSpinBox())
        xi.setRange(100, 20000)
        xi.valueChanged.connect(self.push_to_state)

        rho = self._register("rheology.rho", QSpinBox())
        rho.setRange(100, 1200)
        rho.valueChanged.connect(self.push_to_state)

        ucr = self._register("rheology.u_cr", QDoubleSpinBox())
        ucr.setRange(0.0, 1.0)
        ucr.setSingleStep(0.01)
        ucr.valueChanged.connect(self.push_to_state)

        beta = self._register("rheology.beta", QDoubleSpinBox())
        beta.setRange(0.0, 1.5)
        beta.setSingleStep(0.05)
        beta.valueChanged.connect(self.push_to_state)

        for label, key in [("Model", model), ("mu", mu), ("xi", xi), ("rho", rho), ("u_cr", ucr), ("beta", beta)]:
            form.addRow(label, key)
        return container

    def _build_computation_group(self) -> QWidget:
        container = QWidget()
        layout = QGridLayout(container)

        tmax = self._register("computation.t_max", QSpinBox())
        tmax.setRange(1, 10000)
        tmax.valueChanged.connect(self.push_to_state)

        nbs = self._register("computation.nb_simul", QSpinBox())
        nbs.setRange(1, 100000)
        nbs.valueChanged.connect(self.push_to_state)

        cfl_target = self._register("computation.cfl_target", QDoubleSpinBox())
        cfl_target.setRange(0.1, 1.0)
        cfl_target.setSingleStep(0.05)
        cfl_target.valueChanged.connect(self.push_to_state)

        cfl_max = self._register("computation.cfl_max", QDoubleSpinBox())
        cfl_max.setRange(0.1, 1.0)
        cfl_max.setSingleStep(0.05)
        cfl_max.valueChanged.connect(self.push_to_state)

        refinement = self._register("computation.refinement", QSpinBox())
        refinement.setRange(1, 6)
        refinement.valueChanged.connect(self.push_to_state)

        boundary = self._register("computation.boundary", QComboBox())
        boundary.addItems(["wall", "extrap", "user"])
        boundary.currentTextChanged.connect(self.push_to_state)

        runtime = QLabel("Estimated runtime: n/a")
        self.widgets["computation.runtime_estimate"] = runtime

        pairs = [
            ("t_max", tmax),
            ("nb_simul", nbs),
            ("cfl_target", cfl_target),
            ("cfl_max", cfl_max),
            ("refinement", refinement),
            ("boundary", boundary),
        ]
        for idx, (label, widget) in enumerate(pairs):
            layout.addWidget(QLabel(label), idx, 0)
            layout.addWidget(widget, idx, 1)
        layout.addWidget(runtime, len(pairs), 0, 1, 2)
        return container

    def _build_output_group(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)

        fmt = self._register("output.output_format", QComboBox())
        fmt.addItems(["binary32", "binary64", "ascii"])
        fmt.currentTextChanged.connect(self.push_to_state)

        delta = self._register("output.delta_t", QDoubleSpinBox())
        delta.setRange(0.1, 10000)
        delta.setSingleStep(0.1)
        delta.valueChanged.connect(self.push_to_state)

        anim_var = self._register("animation.variable", QComboBox())
        anim_var.addItems(["depth", "velocity", "pressure"])
        anim_var.currentTextChanged.connect(self.push_to_state)

        n_out = self._register("animation.n_out", QSpinBox())
        n_out.setRange(1, 5000)
        n_out.valueChanged.connect(self.push_to_state)

        form.addRow("output format", fmt)
        form.addRow("delta_t", delta)
        form.addRow("animation variable", anim_var)
        form.addRow("animation frames", n_out)
        return container

    def pull_from_state(self) -> None:
        params = deepcopy(DEFAULT_PARAMETERS)
        params.update(self.state.parameters)
        self.state.parameters = params

        def set_value(key: str, value):
            widget = self.widgets[key]
            block = widget.blockSignals(True)
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(value), Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            widget.blockSignals(block)

        for group, values in self.state.parameters.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    full = f"{group}.{key}"
                    if full in self.widgets:
                        set_value(full, value)

        self.update_runtime_estimate()
        self.draw_initial_preview()

    def push_to_state(self, *_args) -> None:
        params = deepcopy(self.state.parameters)
        for full_key, widget in self.widgets.items():
            if full_key.endswith("runtime_estimate"):
                continue
            group, key = full_key.split(".", 1)
            params.setdefault(group, {})
            if isinstance(widget, QDoubleSpinBox):
                params[group][key] = float(widget.value())
            elif isinstance(widget, QSpinBox):
                params[group][key] = int(widget.value())
            elif isinstance(widget, QCheckBox):
                params[group][key] = bool(widget.isChecked())
            elif isinstance(widget, QComboBox):
                text = widget.currentText()
                params[group][key] = int(text) if key == "period_return" else text
        self.state.update_parameters(params)
        self.update_runtime_estimate()
        self.draw_initial_preview()

    def update_runtime_estimate(self) -> None:
        comp = self.state.parameters.get("computation", {})
        ncols = self.state.dem_metadata.get("ncols", 1000)
        nrows = self.state.dem_metadata.get("nrows", 1000)
        t_max = comp.get("t_max", 90)
        refinement = comp.get("refinement", 1)
        proxy = (ncols * nrows * t_max * refinement) / 2.5e7
        self.widgets["computation.runtime_estimate"].setText(f"Estimated runtime (rough): {proxy:0.1f} minutes")

    def load_yaml(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Load AVAC yaml", str(self.state.project_dir), "YAML (*.yaml *.yml)")
        if not selected:
            return
        try:
            loaded = read_yaml(Path(selected))
            self.state.update_parameters(loaded)
            self.pull_from_state()
            self.validation_label.setText(f"Loaded: {selected}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Load failed", str(exc))

    def save_yaml(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "Save AVAC yaml", str(self.state.project_dir / "AVAC_parameters.yaml"), "YAML (*.yaml)")
        if not selected:
            return
        self.push_to_state()
        write_yaml(Path(selected), self.state.parameters)
        self.validation_label.setText(f"Saved: {selected}")

    def validate(self) -> None:
        issues: list[str] = []
        p = self.state.parameters
        if p["computation"]["cfl_target"] > p["computation"]["cfl_max"]:
            issues.append("cfl_target must be <= cfl_max")
        if p["output"]["delta_t"] > p["computation"]["t_max"]:
            issues.append("output.delta_t should be <= computation.t_max")
        if p["rheology"]["model"] not in {"Voellmy", "Coulomb"}:
            issues.append("rheology.model must be Voellmy or Coulomb")

        if issues:
            self.validation_label.setStyleSheet("color: #b71c1c;")
            self.validation_label.setText("Validation issues:\n- " + "\n- ".join(issues))
        else:
            self.validation_label.setStyleSheet("color: #1b5e20;")
            self.validation_label.setText("Validation passed.")

    def draw_initial_preview(self) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_title("Initial depth estimate")

        dem = self.state.dem_path
        shp = self.state.starting_areas_path
        if not dem or not dem.exists() or gpd is None or MplPath is None or not shp or not shp.exists():
            ax.text(0.5, 0.5, "Select DEM and shapefile to preview initial depth", ha="center", va="center", transform=ax.transAxes)
            self.canvas.draw_idle()
            return

        raster = read_ascii_raster(dem)
        x, y, z = raster.x, raster.y, raster.z
        xx, yy = np.meshgrid(x, y)
        initial = np.zeros_like(z, dtype=float)

        polys = gpd.read_file(shp)
        d0 = float(self.state.parameters["release"]["d0"])
        theta_cr = float(self.state.parameters["release"]["theta_cr"])
        grad = float(self.state.parameters["release"]["gradient_hypso"])
        z_ref = float(self.state.parameters["release"]["z_ref"])
        corr_elev = bool(self.state.parameters["release"]["correction_elevation"])

        gy, gx = np.gradient(np.nan_to_num(z, nan=np.nanmean(z)))
        slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

        pts = np.vstack([xx.ravel(), yy.ravel()]).T
        for geom in polys.geometry:
            if geom is None:
                continue
            if geom.geom_type != "Polygon":
                continue
            poly = MplPath(np.array(geom.exterior.coords))
            mask = poly.contains_points(pts).reshape(z.shape)
            depth = np.where(slope > theta_cr, d0, 0.0)
            if corr_elev:
                depth = depth + np.maximum((z - z_ref) * grad / 100.0, 0.0)
            initial = np.maximum(initial, np.where(mask, depth, 0.0))

        masked = np.ma.masked_where(initial <= 0.0, initial)
        im = ax.pcolormesh(x, y, masked, cmap="Blues", shading="auto")
        self.figure.colorbar(im, ax=ax, label="Initial depth [m]")
        ax.set_aspect("equal")
        self.canvas.draw_idle()
