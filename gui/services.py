from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml

from gui.state import EnvironmentStatus


@dataclass
class RasterData:
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    metadata: dict[str, Any]


@dataclass
class FGMaxResults:
    x: np.ndarray
    y: np.ndarray
    topography: np.ndarray
    depth: np.ndarray
    velocity: np.ndarray
    pressure: np.ndarray
    depth_time: np.ndarray | None = None
    velocity_time: np.ndarray | None = None
    arrival_time: np.ndarray | None = None


@dataclass
class FGoutFrameDescriptor:
    frame_no: int
    time: float


@dataclass
class FGoutFrameData:
    frame_no: int
    time: float
    x: np.ndarray
    y: np.ndarray
    topography: np.ndarray
    depth: np.ndarray
    velocity: np.ndarray
    pressure: np.ndarray


def gui_repo_root() -> Path:
    """Return the AVAC GUI repository root (parent of the gui package)."""
    return Path(__file__).resolve().parents[1]


def resolve_clawpack_source_dir(project_dir: Path | None = None) -> Path:
    """Resolve the Clawpack source directory used by GUI runs.

    Resolution order:
    1) `AVAC_CLAW_ROOT` (explicit override)
    2) shared repo install: `<repo>/.vendor/clawpack-src`
    3) project-local fallback: `<project>/.vendor/clawpack-src`
    4) default target path for first-time install: `<repo>/.vendor/clawpack-src`
    """
    override = os.environ.get("AVAC_CLAW_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    shared = (gui_repo_root() / ".vendor" / "clawpack-src").resolve()
    if shared.exists():
        return shared

    if project_dir is not None:
        local = (Path(project_dir) / ".vendor" / "clawpack-src").resolve()
        if local.exists():
            return local

    return shared


def derive_notebook_profile_axes(
    x: np.ndarray,
    y: np.ndarray,
    dem_extent: Mapping[str, Any] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Build profile interpolation axes using AVAC notebook conventions.

    AVAC.ipynb reconstructs x/y coordinates for profile extraction from
    dem_extent bounds and grid shape with np.linspace(...), instead of using
    fgmax coordinate vectors directly.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size == 0 or y.size == 0:
        return x, y
    if not dem_extent:
        return x, y

    try:
        xmin = float(dem_extent["xmin"])
        xmax = float(dem_extent["xmax"])
        ymin = float(dem_extent["ymin"])
        ymax = float(dem_extent["ymax"])
    except (KeyError, TypeError, ValueError):
        return x, y

    if not np.isfinite([xmin, xmax, ymin, ymax]).all():
        return x, y
    if xmax <= xmin or ymax <= ymin:
        return x, y

    x_axis = np.linspace(xmin, xmax, x.size)
    y_axis = np.linspace(ymin, ymax, y.size)
    return x_axis, y_axis


def derive_notebook_pressure_field(depth: np.ndarray, velocity: np.ndarray, rho: float) -> np.ndarray:
    """Match AVAC.ipynb pressure profile source field generation."""
    depth = np.asarray(depth, dtype=float)
    velocity = np.asarray(velocity, dtype=float)
    velocity_masked = np.ma.masked_where(depth < 0.001, velocity)
    pressure_masked = 0.5 * float(rho) * velocity_masked**2 / 1e3
    return np.asarray(pressure_masked.data, dtype=float)


def read_ascii_raster(path: Path) -> RasterData:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    header = lines[:12]

    meta: dict[str, float] = {}
    for line in header:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        key = parts[0].lower().rstrip(":")
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
        "nodata_value": float(nodata),
    }
    return RasterData(x=x, y=y, z=z, metadata=metadata)


def build_avac_configuration(
    parameters: dict[str, Any],
    dem_metadata: dict[str, Any],
    *,
    topofile: str = "topography.asc",
    initiation_file: str = "init.xyz",
    type_dem: int = 3,
    type_init: int = 1,
) -> dict[str, Any]:
    """Build AVAC_configuration.yaml payload from GUI parameters + DEM metadata."""
    required_dem_keys = ("xmin", "xmax", "ymin", "ymax", "ncols", "nrows", "cellsize")
    missing = [key for key in required_dem_keys if key not in dem_metadata]
    if missing:
        raise ValueError(f"DEM metadata incomplete, missing keys: {', '.join(missing)}")

    return {
        "computation": dict(parameters.get("computation", {})),
        "rheology": dict(parameters.get("rheology", {})),
        "output": dict(parameters.get("output", {})),
        "animation": dict(parameters.get("animation", {})),
        "dem_extent": {
            "xmin": float(dem_metadata["xmin"]),
            "xmax": float(dem_metadata["xmax"]),
            "ymin": float(dem_metadata["ymin"]),
            "ymax": float(dem_metadata["ymax"]),
            "nbx": int(dem_metadata["ncols"]),
            "nby": int(dem_metadata["nrows"]),
            "cell_size": float(dem_metadata["cellsize"]),
            "nodata_value": float(dem_metadata.get("nodata_value", -9999.0)),
        },
        "file_names": {
            "topofile": topofile,
            "initiation_file": initiation_file,
            "type_dem": int(type_dem),
            "type_init": int(type_init),
        },
    }


def write_claw_topography_ascii(path: Path, raster: RasterData, nodata_value: float | None = None) -> None:
    """Write raster to a GeoClaw-compatible topotype-3 ASCII grid."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    z = np.array(raster.z, dtype=float)
    m = raster.metadata
    nrows, ncols = z.shape
    nodata = float(nodata_value if nodata_value is not None else m.get("nodata_value", -9999.0))
    z_out = np.where(np.isfinite(z), z, nodata)

    # ESRI/GeoClaw topotype-3 rows must be written north -> south.
    z_rows_north_to_south = np.flipud(z_out)

    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"ncols {int(ncols)}\n")
        handle.write(f"nrows {int(nrows)}\n")
        handle.write(f"xllcorner {float(m['xmin'])}\n")
        handle.write(f"yllcorner {float(m['ymin'])}\n")
        handle.write(f"cellsize {float(m['cellsize'])}\n")
        handle.write(f"NODATA_value {nodata}\n")
        for row in z_rows_north_to_south:
            handle.write(" ".join(f"{float(value):.10g}" for value in row) + "\n")


def write_claw_qinit_xyz(path: Path, x: np.ndarray, y: np.ndarray, q: np.ndarray) -> None:
    """Write depth field to GeoClaw topotype-1 qinit file (x y value per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    q = np.asarray(q, dtype=float)
    if q.shape != (y.size, x.size):
        raise ValueError(f"q shape {q.shape} does not match (len(y), len(x)) = {(y.size, x.size)}")

    with path.open("w", encoding="utf-8") as handle:
        # qinit_module expects NW -> SE traversal.
        for j in range(y.size - 1, -1, -1):
            yv = y[j]
            for i, xv in enumerate(x):
                value = q[j, i]
                if not np.isfinite(value):
                    value = 0.0
                handle.write(f"{xv:.12g} {yv:.12g} {float(value):.12g}\n")


def read_yaml(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _prepend_search_path(value: str, prefix: str) -> str:
    if not prefix:
        return value
    entries = [entry for entry in value.split(os.pathsep) if entry]
    normalized_prefix = os.path.normcase(os.path.normpath(prefix))
    filtered = [entry for entry in entries if os.path.normcase(os.path.normpath(entry)) != normalized_prefix]
    return os.pathsep.join([prefix, *filtered])


def _append_env_paths(value: str, additions: list[str]) -> str:
    entries = [entry for entry in value.split(os.pathsep) if entry]
    normalized = {os.path.normcase(os.path.normpath(entry)) for entry in entries}
    for item in additions:
        if not item:
            continue
        norm_item = os.path.normcase(os.path.normpath(item))
        if norm_item in normalized:
            continue
        entries.append(item)
        normalized.add(norm_item)
    return os.pathsep.join(entries)


def _discover_installed_clawpack_editable_build_paths() -> list[str]:
    """Find build paths referenced by meson editable Clawpack loaders in this interpreter."""
    build_paths: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"install\(\s*['\"]Clawpack['\"]\s*,\s*\{[^}]*\}\s*,\s*['\"]([^'\"]+)['\"]",
        re.DOTALL,
    )

    for entry in sys.path:
        if not entry:
            continue
        loader = Path(entry) / "_clawpack_editable_loader.py"
        if not loader.exists():
            continue
        try:
            text = loader.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in pattern.finditer(text):
            raw = match.group(1).strip()
            if not raw:
                continue
            resolved = str(Path(raw).expanduser().resolve())
            norm = os.path.normcase(os.path.normpath(resolved))
            if norm in seen:
                continue
            seen.add(norm)
            build_paths.append(resolved)

    return build_paths


def build_local_claw_env(
    base_env: Mapping[str, str] | None,
    project_dir: Path,
    python_executable: str | None = None,
) -> dict[str, str]:
    """Build a run environment that resolves Clawpack from shared/local source."""
    source = os.environ if base_env is None else base_env
    env = {str(key): str(value) for key, value in source.items()}

    claw_root = resolve_clawpack_source_dir(project_dir)
    env["CLAW"] = str(claw_root)

    python_cmd = str(python_executable or sys.executable or "python3")
    env["CLAW_PYTHON"] = python_cmd

    python_bin = ""
    python_path = Path(python_cmd)
    if python_path.is_absolute() or python_path.parent != Path("."):
        python_bin = str(python_path.parent)
    else:
        resolved = shutil.which(python_cmd)
        if resolved:
            python_bin = str(Path(resolved).parent)
    if python_bin:
        env["PATH"] = _prepend_search_path(env.get("PATH", ""), python_bin)

    env["PYTHONPATH"] = _prepend_search_path(env.get("PYTHONPATH", ""), str(claw_root))

    # Avoid meson-python editable rebuild hooks for Clawpack at runtime.
    # The GUI should import Clawpack from source via PYTHONPATH
    # rather than triggering an editable wheel rebuild on each import.
    editable_build_paths: list[str] = []
    build_root = claw_root / "build"
    if build_root.exists():
        editable_build_paths.append(str(build_root))
        for candidate in build_root.iterdir():
            if candidate.is_dir():
                editable_build_paths.append(str(candidate))
    editable_build_paths.extend(_discover_installed_clawpack_editable_build_paths())
    env["MESONPY_EDITABLE_SKIP"] = _append_env_paths(
        env.get("MESONPY_EDITABLE_SKIP", ""),
        editable_build_paths,
    )
    return env


def check_environment(project_dir: Path) -> EnvironmentStatus:
    status = EnvironmentStatus()
    status.python_path = sys.executable
    webengine_error = ""
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView  # noqa: F401

        status.webengine_ready = True
    except Exception as exc:  # noqa: BLE001
        status.webengine_ready = False
        webengine_error = str(exc)

    gfortran = shutil.which("gfortran")
    status.gfortran_found = bool(gfortran)
    status.gfortran_path = gfortran or ""

    claw_env = resolve_clawpack_source_dir(project_dir)
    installed_claw = shutil.which("clawutil")
    status.clawpack_ready = claw_env.exists()
    status.claw_path = str(claw_env)

    status.avac_files_extracted = (Path(project_dir) / "Makefile").exists() and (Path(project_dir) / "setrun.py").exists()
    if not status.gfortran_found:
        status.notes.append("gfortran not found in PATH")
    if not status.clawpack_ready:
        if installed_claw:
            status.notes.append(
                f"System Clawpack detected at {installed_claw}, but GUI runs require shared/local source install at {claw_env}"
            )
        else:
            status.notes.append(f"Clawpack source not detected at {claw_env}; run 'Install Shared Clawpack'")
    else:
        if os.environ.get("AVAC_CLAW_ROOT", "").strip():
            status.notes.append("Using Clawpack source from AVAC_CLAW_ROOT override")
        elif claw_env == (gui_repo_root() / ".vendor" / "clawpack-src").resolve():
            status.notes.append("Using shared Clawpack source from repository .vendor/clawpack-src")
        else:
            status.notes.append("Using project-local fallback Clawpack source")
    if not status.avac_files_extracted:
        status.notes.append("AVAC solver files not extracted in project folder")
    if not status.webengine_ready:
        status.notes.append(
            "PyQt6-WebEngine is unavailable. Install Python deps and Linux runtime libs:\n"
            "  pip install -r requirements-gui.txt\n"
            "  sudo apt-get install -y libnspr4 libnss3"
        )
        if webengine_error:
            status.notes.append(f"PyQt6-WebEngine import error: {webengine_error}")
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
        try:
            tar.extractall(path=target_dir, filter="data")
        except TypeError:
            tar.extractall(path=target_dir)

    # Some archives place AVAC files under a top-level "files/" directory.
    # Promote missing files into project root so setup checks and make commands work.
    required = ("Makefile", "setrun.py")
    if not all((target_dir / name).exists() for name in required):
        nested = target_dir / "files"
        if nested.exists() and nested.is_dir() and all((nested / name).exists() for name in required):
            for child in nested.iterdir():
                destination = target_dir / child.name
                if destination.exists():
                    continue
                if child.is_dir():
                    shutil.copytree(child, destination)
                else:
                    shutil.copy2(child, destination)


def install_clawpack_from_zip(zip_path: Path, project_dir: Path, timeout: int = 3600) -> tuple[int, str]:
    """Install Clawpack from the bundled zip into shared/local source directory.

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
    src_root = resolve_clawpack_source_dir(project_dir)
    vendor = src_root.parent
    vendor.mkdir(parents=True, exist_ok=True)

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


def _parse_fgout_frame_no(path: Path, fgno: int = 1) -> int | None:
    pattern = rf"^fgout{fgno:04d}\.[tb](\d+)$"
    match = re.match(pattern, path.name)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _read_fgout_time_from_t_file(path: Path) -> float:
    try:
        first_line = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        token = first_line.strip().split()[0]
        return float(token)
    except (IndexError, OSError, ValueError):
        return float("nan")


def list_fgout_frames(output_dir: Path, fgno: int = 1) -> list[FGoutFrameDescriptor]:
    output_dir = Path(output_dir)
    if not output_dir.exists() or not output_dir.is_dir():
        return []

    frames: list[FGoutFrameDescriptor] = []
    for t_file in sorted(output_dir.glob(f"fgout{fgno:04d}.t*")):
        frame_no = _parse_fgout_frame_no(t_file, fgno=fgno)
        if frame_no is None:
            continue
        frames.append(FGoutFrameDescriptor(frame_no=frame_no, time=_read_fgout_time_from_t_file(t_file)))
    frames.sort(key=lambda item: item.frame_no)
    return frames


def _import_fgout_tools(project_dir: Path):
    claw_root = resolve_clawpack_source_dir(project_dir)
    if not claw_root.exists():
        raise FileNotFoundError(f"Clawpack source not found: {claw_root}")

    # Ensure in-process imports avoid meson-python editable rebuild hooks.
    editable_build_paths: list[str] = []
    build_root = claw_root / "build"
    if build_root.exists():
        editable_build_paths.append(str(build_root))
        for candidate in build_root.iterdir():
            if candidate.is_dir():
                editable_build_paths.append(str(candidate))
    editable_build_paths.extend(_discover_installed_clawpack_editable_build_paths())
    os.environ["MESONPY_EDITABLE_SKIP"] = _append_env_paths(
        os.environ.get("MESONPY_EDITABLE_SKIP", ""),
        editable_build_paths,
    )
    os.environ["CLAW"] = str(claw_root)

    added = False
    claw_root_str = str(claw_root)
    if claw_root_str not in sys.path:
        sys.path.insert(0, claw_root_str)
        added = True
    try:
        from clawpack.geoclaw import fgout_tools

        return fgout_tools
    finally:
        if added:
            try:
                sys.path.remove(claw_root_str)
            except ValueError:
                pass


def load_fgout_frame(
    output_dir: Path,
    project_dir: Path,
    frame_no: int,
    *,
    rho: float = 300.0,
    fgno: int = 1,
    output_format: str = "binary32",
) -> FGoutFrameData:
    output_dir = Path(output_dir)
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"Result directory does not exist: {output_dir}")

    fgout_tools = _import_fgout_tools(project_dir)
    requested_format = str(output_format).strip().lower()
    fallback_formats = ["binary32", "binary64", "ascii"]
    formats = [requested_format] + [fmt for fmt in fallback_formats if fmt != requested_format]

    fgout = None
    last_error: Exception | None = None
    for fmt in formats:
        try:
            fgout_grid = fgout_tools.FGoutGrid(fgno, str(output_dir), output_format=fmt)
            fgout_grid.read_fgout_grids_data()
            fgout = fgout_grid.read_frame(int(frame_no))
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if fgout is None:
        raise RuntimeError(
            f"Could not load fgout frame {int(frame_no)} from {output_dir} "
            f"using output_format={requested_format}."
        ) from last_error

    depth = np.asarray(np.ma.masked_where(fgout.h < 0.001, fgout.h).filled(0.0), dtype=float)
    velocity = np.asarray(np.ma.masked_where(fgout.h < 0.001, fgout.s).filled(0.0), dtype=float)
    field_shape = depth.shape

    topography = np.asarray(getattr(fgout, "B"), dtype=float)
    if topography.shape != field_shape and topography.T.shape == field_shape:
        topography = topography.T

    x_raw = np.asarray(getattr(fgout, "x"), dtype=float)
    y_raw = np.asarray(getattr(fgout, "y"), dtype=float)
    x: np.ndarray
    y: np.ndarray

    if x_raw.ndim == 1 and y_raw.ndim == 1 and field_shape == (y_raw.size, x_raw.size):
        x, y = x_raw, y_raw
    else:
        x2d = np.asarray(getattr(fgout, "X"), dtype=float)
        y2d = np.asarray(getattr(fgout, "Y"), dtype=float)
        if x2d.shape == field_shape and y2d.shape == field_shape:
            x, y = x2d, y2d
        elif x2d.T.shape == field_shape and y2d.T.shape == field_shape:
            x, y = x2d.T, y2d.T
        elif x_raw.ndim == 1 and y_raw.ndim == 1 and field_shape == (x_raw.size, y_raw.size):
            # Some outputs provide x/y swapped versus array orientation.
            x, y = y_raw, x_raw
            depth = depth.T
            velocity = velocity.T
            if topography.shape != depth.shape and topography.T.shape == depth.shape:
                topography = topography.T
        else:
            x, y = x_raw, y_raw

    pressure = np.asarray(0.5 * float(rho) * velocity * velocity / 1e3, dtype=float)

    return FGoutFrameData(
        frame_no=int(frame_no),
        time=float(getattr(fgout, "t")),
        x=x,
        y=y,
        topography=topography,
        depth=depth,
        velocity=velocity,
        pressure=pressure,
    )


def _fgmax_path_for_directory(output_dir: Path) -> Path | None:
    output_dir = Path(output_dir)
    if not output_dir.exists() or not output_dir.is_dir():
        return None
    direct = output_dir / "fgmax0001.txt"
    if direct.exists():
        return direct
    matches = sorted(output_dir.glob("fgmax*.txt"))
    return matches[0] if matches else None


def _reshape_fgmax_column(
    x_values: np.ndarray,
    y_values: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    x_idx = np.searchsorted(x_axis, x_values)
    y_idx = np.searchsorted(y_axis, y_values)
    grid = np.full((y_axis.size, x_axis.size), np.nan, dtype=float)
    grid[y_idx, x_idx] = values
    return grid


def load_fgmax_results(output_dir: Path, rho: float = 300.0) -> FGMaxResults:
    """Load AVAC/GeoClaw fgmax outputs and derive map fields used in the GUI."""
    fgmax_path = _fgmax_path_for_directory(output_dir)
    if fgmax_path is None:
        raise FileNotFoundError(f"No fgmax*.txt file found in {output_dir}")

    raw = np.loadtxt(fgmax_path)
    if raw.ndim == 1:
        raw = np.atleast_2d(raw)
    if raw.shape[1] < 6:
        raise ValueError(f"Unexpected fgmax file format ({raw.shape[1]} columns): {fgmax_path}")

    raw = np.where(raw <= -1e90, np.nan, raw)
    x_values = np.asarray(raw[:, 0], dtype=float)
    y_values = np.asarray(raw[:, 1], dtype=float)
    x_axis = np.unique(x_values)
    y_axis = np.unique(y_values)
    expected_size = x_axis.size * y_axis.size
    if expected_size != raw.shape[0]:
        raise ValueError(
            f"fgmax grid is not rectangular: {raw.shape[0]} samples, expected {expected_size} "
            f"for {x_axis.size} x {y_axis.size}"
        )

    topography = _reshape_fgmax_column(x_values, y_values, x_axis, y_axis, np.asarray(raw[:, 3], dtype=float))
    depth = _reshape_fgmax_column(x_values, y_values, x_axis, y_axis, np.asarray(raw[:, 4], dtype=float))
    velocity = _reshape_fgmax_column(x_values, y_values, x_axis, y_axis, np.asarray(raw[:, 5], dtype=float))
    depth = np.where(np.isfinite(depth) & (depth > 0.0), depth, 0.0)
    velocity = np.where(np.isfinite(velocity) & (velocity > 0.0), velocity, 0.0)
    pressure = 0.5 * float(rho) * velocity * velocity / 1e3

    depth_time = None
    velocity_time = None
    arrival_time = None
    if raw.shape[1] >= 9:
        depth_time = _reshape_fgmax_column(x_values, y_values, x_axis, y_axis, np.asarray(raw[:, 6], dtype=float))
        velocity_time = _reshape_fgmax_column(x_values, y_values, x_axis, y_axis, np.asarray(raw[:, 7], dtype=float))
        arrival_time = _reshape_fgmax_column(x_values, y_values, x_axis, y_axis, np.asarray(raw[:, 8], dtype=float))

    return FGMaxResults(
        x=x_axis,
        y=y_axis,
        topography=topography,
        depth=depth,
        velocity=velocity,
        pressure=pressure,
        depth_time=depth_time,
        velocity_time=velocity_time,
        arrival_time=arrival_time,
    )


def list_result_directories(project_dir: Path, configured_output_dir: str = "_output") -> list[Path]:
    """List likely AVAC result directories available in a project."""
    project_dir = Path(project_dir)
    candidates: dict[Path, None] = {}

    configured = Path(configured_output_dir)
    configured_path = configured if configured.is_absolute() else project_dir / configured
    candidates[configured_path.resolve()] = None

    for child in project_dir.iterdir():
        try:
            if child.is_dir() and child.name.startswith("_output"):
                candidates[child.resolve()] = None
        except OSError:
            continue

    # Also check one nested level for simulation folders that contain _output*.
    for child in project_dir.iterdir():
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if not is_dir:
            continue
        try:
            nested_iter = list(child.iterdir())
        except OSError:
            continue
        for nested in nested_iter:
            try:
                if nested.is_dir() and nested.name.startswith("_output"):
                    candidates[nested.resolve()] = None
            except OSError:
                continue

    result_dirs: list[Path] = []
    for directory in sorted(candidates.keys()):
        try:
            if directory.exists() and directory.is_dir():
                if _fgmax_path_for_directory(directory) is not None or any(directory.glob("fort.q*")):
                    result_dirs.append(directory)
        except OSError:
            continue
    return result_dirs


def latest_result_directory(project_dir: Path, configured_output_dir: str = "_output") -> Path | None:
    """Pick the most recent result directory containing fgmax or fort.q outputs."""
    result_dirs = list_result_directories(project_dir, configured_output_dir=configured_output_dir)
    if not result_dirs:
        return None

    def score(path: Path) -> float:
        fgmax = _fgmax_path_for_directory(path)
        if fgmax is not None:
            return fgmax.stat().st_mtime
        fort_q = sorted(path.glob("fort.q*"))
        if fort_q:
            return max(item.stat().st_mtime for item in fort_q)
        return path.stat().st_mtime

    return max(result_dirs, key=score)
