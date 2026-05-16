#!/usr/bin/env python3
"""Desktop entrypoint for AVAC GUI."""

import os
import platform


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

from gui.app import run


if __name__ == "__main__":
    raise SystemExit(run())
