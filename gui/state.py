from __future__ import annotations

import platform
import re
from dataclasses import dataclass, field
from copy import deepcopy
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal


DEFAULT_PARAMETERS: dict[str, Any] = {
    "release": {
        "d0": 1.77,
        "correction_slope": True,
        "correction_elevation": True,
        "nu": 0.2,
        "theta_cr": 30,
        "gradient_hypso": 0.03,
        "z_ref": 2000,
    },
    "rheology": {"model": "Voellmy", "rho": 300, "mu": 0.2, "xi": 1800, "u_cr": 0.1, "beta": 1.1},
    "topography": {"dem": "topo1m.asc", "starting_areas": "ZA.shp"},
    "computation": {
        "t_max": 90,
        "nb_simul": 30,
        "dry_limit": 0.01,
        "cfl_target": 0.5,
        "cfl_max": 1,
        "refinement": 1,
        "max_iter": 100000,
        "domain_cell": 2,
        "boundary": "extrap",
        "output_directory": "_output",
    },
    "output": {"delta_t": 1, "output_format": "binary32", "verbosity": 0},
    "animation": {"n_out": 90, "variable": "depth"},
}


@dataclass
class EnvironmentStatus:
    python_ok: bool = True
    webengine_ready: bool = False
    gfortran_found: bool = False
    clawpack_ready: bool = False
    avac_files_extracted: bool = False
    python_path: str = ""
    gfortran_path: str = ""
    claw_path: str = ""
    notes: list[str] = field(default_factory=list)


class AppState(QObject):
    changed = pyqtSignal()

    def __init__(self, project_dir: Path):
        super().__init__()
        self.project_dir = Path(project_dir)
        self.parameters = deepcopy(DEFAULT_PARAMETERS)
        self.dem_path: Path | None = None
        self.starting_areas_path: Path | None = None
        self.profile_path: Path | None = None
        self.dem_metadata: dict[str, Any] = {}
        self.environment = EnvironmentStatus()
        self.last_run_log: Path | None = None

    def update_project_dir(self, value: str | Path) -> None:
        self.project_dir = self._normalize_path(value)
        self.dem_path = None
        self.starting_areas_path = None
        self.profile_path = None
        self.dem_metadata = {}
        self.changed.emit()

    def _normalize_path(self, value: str | Path | None) -> Path | None:
        if value is None:
            return None
        raw = str(value)
        path = Path(raw)
        if platform.system().lower() == "linux":
            # Handle Windows-style paths that can appear in some WSL dialog setups.
            match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
            if match:
                drive = match.group(1).lower()
                rest = match.group(2).replace("\\", "/")
                return Path(f"/mnt/{drive}/{rest}")
        return path

    def update_parameters(self, params: dict[str, Any]) -> None:
        self.parameters = params
        self.changed.emit()

    def set_paths(self, dem: Path | None = None, starting_areas: Path | None = None, profile: Path | None = None) -> None:
        if dem is not None:
            normalized_dem = self._normalize_path(dem)
            if normalized_dem is not None:
                self.dem_path = normalized_dem
                self.parameters.setdefault("topography", {})["dem"] = normalized_dem.name
        if starting_areas is not None:
            normalized_starting = self._normalize_path(starting_areas)
            if normalized_starting is not None:
                self.starting_areas_path = normalized_starting
                self.parameters.setdefault("topography", {})["starting_areas"] = normalized_starting.name
        if profile is not None:
            normalized_profile = self._normalize_path(profile)
            if normalized_profile is not None:
                self.profile_path = normalized_profile
        self.changed.emit()
