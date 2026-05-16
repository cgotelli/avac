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
    try:
        proc = subprocess.run(
            ["wslpath", "-u", path_value],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    converted = proc.stdout.strip()
    return converted or None


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
    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _resolve_wslg_user_config_path() -> Path | None:
    for windows_path in _candidate_windows_user_profiles():
        linux_path = _windows_to_linux_path(windows_path)
        if linux_path:
            return Path(linux_path) / ".wslgconfig"
    return None


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
    config_path = _resolve_wslg_user_config_path()
    if config_path is None:
        return
    try:
        current = config_path.read_text(encoding="utf-8-sig", errors="ignore") if config_path.exists() else ""
    except OSError:
        return
    updated = _merge_wslg_system_distro_env(current)
    if updated == current:
        return
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(updated, encoding="utf-8")
    except OSError:
        return

    # WSLg reads config only at startup; tell users what to do once.
    if _current_wslg_copy_warning_enabled() is not False:
        print(
            "[AVAC] Updated WSLg title config. Run 'wsl --shutdown' once, then relaunch AVAC.",
            flush=True,
        )


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
