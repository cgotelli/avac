#!/usr/bin/env python3
"""Desktop entrypoint for AVAC GUI."""

import os
import platform
import re
import subprocess
from pathlib import Path


def _is_wsl_linux() -> bool:
    if platform.system().lower() != "linux":
        return False
    try:
        marker = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8", errors="ignore").lower()
        if "microsoft" in marker:
            return True
    except OSError:
        pass
    try:
        marker = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        return "microsoft" in marker
    except OSError:
        return False


def _windows_to_linux_path(path_value: str) -> str | None:
    if not path_value:
        return None
    raw = str(path_value).strip().strip('"').strip("'")
    if not raw:
        return None
    try:
        proc = subprocess.run(
            ["wslpath", "-u", raw],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        converted = ""
    else:
        converted = proc.stdout.strip()
    if converted:
        return converted

    # Fallback if `wslpath` is unavailable or failed in this distro.
    drive_match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if drive_match:
        drive = drive_match.group(1).lower()
        remainder = drive_match.group(2).replace("\\", "/").lstrip("/")
        return f"/mnt/{drive}/{remainder}" if remainder else f"/mnt/{drive}"
    return None


def _windows_user_profile_from_weston_log() -> str | None:
    log_path = Path("/mnt/wslg/weston.log")
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    matches = re.findall(r"WSL2_USER_PROFILE=([^\r\n]+)", text)
    if not matches:
        return None
    value = matches[-1].strip()
    return value or None


def _windows_user_profile_from_windows_shell() -> str | None:
    queries = [
        ["powershell.exe", "-NoProfile", "-Command", "[Environment]::GetFolderPath('UserProfile')"],
        ["cmd.exe", "/c", "echo %USERPROFILE%"],
    ]
    for cmd in queries:
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=6,
            )
        except OSError:
            continue
        if proc.returncode != 0:
            continue
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            continue
        value = lines[-1]
        # Guard against cmd echoing literal token when expansion fails.
        if value == "%USERPROFILE%":
            continue
        return value
    return None


def _candidate_windows_user_profiles() -> list[str]:
    candidates: list[str] = []
    for name in ("WSL2_USER_PROFILE", "USERPROFILE"):
        value = os.environ.get(name, "").strip()
        if value:
            candidates.append(value)
    home_drive = os.environ.get("HOMEDRIVE", "").strip()
    home_path = os.environ.get("HOMEPATH", "").strip()
    if home_drive and home_path:
        candidates.append(f"{home_drive}{home_path}")
    for extra in (_windows_user_profile_from_weston_log(), _windows_user_profile_from_windows_shell()):
        if extra:
            candidates.append(extra)
    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _resolve_wslg_config_paths() -> list[Path]:
    windows_candidates: list[str] = []
    windows_candidates.extend(_candidate_windows_user_profiles())
    windows_candidates.append(r"C:\ProgramData\Microsoft\WSL")

    resolved: list[Path] = []
    seen: set[str] = set()
    for windows_path in windows_candidates:
        if not windows_path:
            continue
        linux_path = _windows_to_linux_path(windows_path)
        if not linux_path:
            continue
        path = Path(linux_path) / ".wslgconfig"
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def _resolve_wslg_user_config_path() -> Path | None:
    # Backward-compatible helper; first candidate is user profile when available.
    paths = _resolve_wslg_config_paths()
    return paths[0] if paths else None


def _write_config_if_changed(config_path: Path) -> bool:
    try:
        current = config_path.read_text(encoding="utf-8-sig", errors="ignore") if config_path.exists() else ""
    except OSError:
        return False
    updated = _merge_wslg_system_distro_env(current)
    if updated == current:
        return False
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(updated, encoding="utf-8")
        return True
    except OSError:
        return False


def _verify_config_contains_expected_values(config_path: Path) -> bool:
    try:
        text = config_path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False
    required_pairs = {
        "WESTON_RDP_COPY_WARNING_TITLE": "false",
        "WESTON_RDP_APPEND_DISTRONAME_TITLE": "false",
    }
    for key, expected in required_pairs.items():
        match = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*(\S+)\s*$", text)
        if not match:
            return False
        if match.group(1).strip().lower() != expected:
            return False
    return True


def _best_config_path_for_message(paths: list[Path]) -> str:
    if not paths:
        return "unknown path"
    # Prefer a user profile location when present.
    for path in paths:
        if "/users/" in str(path).lower():
            return str(path)
    return str(paths[0])


def _maybe_print_wslg_restart_hint(config_paths: list[Path]) -> None:
    hint_key = "AVAC_WSLG_TITLE_FIX_HINT_SHOWN"
    if os.environ.get(hint_key, "0") == "1":
        return
    os.environ[hint_key] = "1"
    location = _best_config_path_for_message(config_paths)
    print(
        "[AVAC] WSLg title fix is configured at "
        f"{location}. If [WARN: COPY MODE] is still shown, run 'wsl --shutdown' once and relaunch AVAC.",
        flush=True,
    )


def _try_configure_all_wslg_paths() -> tuple[bool, list[Path], list[Path]]:
    paths = _resolve_wslg_config_paths()
    wrote_paths: list[Path] = []
    verified_paths: list[Path] = []
    for path in paths:
        changed = _write_config_if_changed(path)
        if changed:
            wrote_paths.append(path)
        if _verify_config_contains_expected_values(path):
            verified_paths.append(path)
    return bool(wrote_paths), paths, verified_paths


def _is_wslg_copy_warning_currently_on() -> bool | None:
    return _current_wslg_copy_warning_enabled()


def _merge_wslg_system_distro_env(content: str) -> str:
    lines = content.splitlines()
    section_header = "[system-distro-env]"
    settings = {
        "WESTON_RDP_COPY_WARNING_TITLE": "false",
        "WESTON_RDP_APPEND_DISTRONAME_TITLE": "false",
        # Keep compatibility with older/newer WSLg variants that use DISABLE_* keys.
        "WESTON_RDP_DISABLE_COPY_WARNING_TITLE": "true",
        "WESTON_RDP_DISABLE_APPEND_DISTRONAME_TITLE": "true",
    }

    section_start = None
    for idx, line in enumerate(lines):
        if line.strip().lower() == section_header:
            section_start = idx
            break

    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(section_header)
        section_start = len(lines) - 1

    section_end = len(lines)
    for idx in range(section_start + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_end = idx
            break

    existing_positions: dict[str, int] = {}
    for idx in range(section_start + 1, section_end):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in settings:
            existing_positions[key] = idx

    for key, value in settings.items():
        setting_line = f"{key}={value}"
        position = existing_positions.get(key)
        if position is not None:
            lines[position] = setting_line
        else:
            lines.insert(section_end, setting_line)
            section_end += 1

    return "\n".join(lines).rstrip("\n") + "\n"


def _current_wslg_copy_warning_enabled() -> bool | None:
    log_path = Path("/mnt/wslg/weston.log")
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    matches = re.findall(r"enable_copy_warning_title\s*=\s*([01])", text)
    if not matches:
        return None
    return matches[-1] == "1"


def ensure_wslg_title_defaults() -> None:
    """Apply portable WSLg title defaults per user profile.

    This is machine-agnostic: after cloning on a new PC, first GUI launch will
    write/update the user `.wslgconfig` automatically.
    """
    if os.environ.get("AVAC_DISABLE_WSLG_TITLE_FIX", "0") == "1":
        return
    if not _is_wsl_linux():
        return
    changed, config_paths, verified_paths = _try_configure_all_wslg_paths()
    if not config_paths:
        return
    if not verified_paths and not changed:
        return
    # WSLg reads config only at startup; tell users what to do once.
    if _is_wslg_copy_warning_currently_on() is not False:
        _maybe_print_wslg_restart_hint(verified_paths or config_paths)


def configure_qt_runtime() -> None:
    """Apply portable Qt defaults for Linux/WSL environments.

    This avoids hard failures when EGL/Vulkan/GPU contexts are unavailable,
    especially in WSL/Wayland setups.
    """
    if os.environ.get("AVAC_DISABLE_QT_COMPAT", "0") == "1":
        return

    is_linux = platform.system().lower() == "linux"
    if not is_linux:
        return

    # Keep platform selection conservative: only force xcb when requested.
    if os.environ.get("AVAC_FORCE_XCB", "0") == "1":
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
    os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")

    existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    extra_flags = ["--disable-gpu", "--disable-gpu-compositing"]
    merged = " ".join([existing_flags, *extra_flags]).strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(merged.split())


configure_qt_runtime()
ensure_wslg_title_defaults()

from gui.app import run


if __name__ == "__main__":
    raise SystemExit(run())
