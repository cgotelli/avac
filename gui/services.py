from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from gui.state import EnvironmentStatus


@dataclass
class RasterData:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    metadata: dict[str, Any]


def read_ascii_raster(path: Path) -> RasterData:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    header = lines[:12]

    meta: dict[str, float] = {}
    for line in header:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        if key in {"ncols", "nrows", "xllcorner", "yllcorner", "xllcenter", "yllcenter", "cellsize", "nodata_value", "north", "south", "east", "west", "rows", "cols"}:
            try:
                meta[key] = float(parts[1])
            except ValueError:
                continue

    skip_header = 0
    for idx, line in enumerate(lines):
        token = line.strip().split()
        if not token:
            continue
        try:
            float(token[0])
            skip_header = idx
            break
        except ValueError:
            continue

    grid = np.genfromtxt(path, skip_header=skip_header)
    if grid.ndim == 1:
        grid = np.atleast_2d(grid)

    nodata = meta.get("nodata_value", -9999)
    grid = np.where(np.isclose(grid, nodata), np.nan, grid)

    if "west" in meta and "east" in meta and "rows" in meta and "cols" in meta:
        xmin, xmax = meta["west"], meta["east"]
        ymin, ymax = meta["south"], meta["north"]
        nrows, ncols = int(meta["rows"]), int(meta["cols"])
    else:
        ncols = int(meta.get("ncols", grid.shape[1]))
        nrows = int(meta.get("nrows", grid.shape[0]))
        cellsize = float(meta.get("cellsize", 1.0))
        if "xllcenter" in meta:
            xmin = float(meta["xllcenter"] - cellsize / 2)
            ymin = float(meta["yllcenter"] - cellsize / 2)
        else:
            xmin = float(meta.get("xllcorner", 0.0))
            ymin = float(meta.get("yllcorner", 0.0))
        xmax = xmin + ncols * cellsize
        ymax = ymin + nrows * cellsize

    x = np.linspace(xmin, xmax, ncols)
    y = np.linspace(ymin, ymax, nrows)
    z = grid[::-1, :]

    metadata = {
        "xmin": xmin,
        "xmax": xmax,
        "ymin": ymin,
        "ymax": ymax,
        "ncols": ncols,
        "nrows": nrows,
        "cellsize": float((xmax - xmin) / max(ncols, 1)),
    }
    return RasterData(x=x, y=y, z=z, metadata=metadata)


def read_yaml(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def check_environment(project_dir: Path) -> EnvironmentStatus:
    status = EnvironmentStatus()
    status.python_path = sys.executable
    gfortran = shutil.which("gfortran")
    status.gfortran_found = bool(gfortran)
    status.gfortran_path = gfortran or ""

    claw_env = Path(project_dir) / ".vendor" / "clawpack-src"
    installed_claw = shutil.which("clawutil")
    status.clawpack_ready = claw_env.exists() or bool(installed_claw)
    status.claw_path = str(claw_env) if claw_env.exists() else (installed_claw or "")

    status.avac_files_extracted = (Path(project_dir) / "Makefile").exists() and (Path(project_dir) / "setrun.py").exists()
    if not status.gfortran_found:
        status.notes.append("gfortran not found in PATH")
    if not status.clawpack_ready:
        status.notes.append("Clawpack not detected; run local setup")
    if not status.avac_files_extracted:
        status.notes.append("AVAC solver files not extracted in project folder")
    return status


def extract_avac_files(archive: Path, target_dir: Path) -> None:
    archive = Path(archive)
    target_dir = Path(target_dir)
    if not archive.exists():
        raise FileNotFoundError(f"Missing archive: {archive}")
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            member_path = (target_dir / member.name).resolve()
            if not str(member_path).startswith(str(target_dir.resolve())):
                raise RuntimeError(f"Unsafe tar entry blocked: {member.name}")
        tar.extractall(path=target_dir)


def install_clawpack_from_zip(zip_path: Path, project_dir: Path, timeout: int = 3600) -> tuple[int, str]:
    """Install clawpack from the bundled zip into project-local vendor source.

    The default timeout is 3600 seconds because editable installation and build
    steps can be lengthy on first run (compile + dependency resolution). If the
    timeout is exceeded, subprocess.run raises TimeoutExpired to signal that setup
    did not finish within the expected bound.
    Set AVAC_CLAW_INSTALL_TIMEOUT to override timeout without changing code.
    Args:
        timeout: Installation timeout in seconds.

    Returns:
        tuple[int, str]: (return_code, combined_stdout_stderr_log)
    """
    effective_timeout = int(os.environ.get("AVAC_CLAW_INSTALL_TIMEOUT", timeout))

    zip_path = Path(zip_path)
    project_dir = Path(project_dir)
    vendor = project_dir / ".vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    src_root = vendor / "clawpack-src"

    if not src_root.exists():
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                member_path = (vendor / member.filename).resolve()
                if not str(member_path).startswith(str(vendor.resolve())):
                    raise RuntimeError(f"Unsafe zip entry blocked: {member.filename}")
            zf.extractall(vendor)
        extracted = [d for d in vendor.iterdir() if d.is_dir() and d.name.startswith("clawpack-")]
        if not extracted:
            raise RuntimeError("Cannot find extracted clawpack source directory")
        extracted[0].rename(src_root)

    cmd = [sys.executable, "-m", "pip", "install", "-e", str(src_root)]
    proc = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, timeout=effective_timeout, check=False)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode, output


def count_output_frames(project_dir: Path, output_dir: str = "_output") -> int:
    base = Path(project_dir) / output_dir
    if not base.exists():
        return 0
    return len(list(base.glob("fort.q*")))
