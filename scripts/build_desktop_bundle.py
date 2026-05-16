from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def data_separator() -> str:
    return ";" if platform.system().lower().startswith("win") else ":"


def build_command() -> list[str]:
    sep = data_separator()
    data_files = [
        "README.md",
        "AVAC_parameters.yaml",
        "files.tar.gz",
        "clawpack-v5.14.0.zip",
        "topo1m.asc",
        "ZA.shp",
        "ZA.shx",
        "ZA.dbf",
        "ZA.prj",
        "ZA.cpg",
        "ZA.qix",
        "profil.shp",
        "profil.shx",
        "profil.dbf",
        "profil.prj",
        "profil.cpg",
        "profil.qix",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        "avac-gui",
        "--collect-submodules",
        "matplotlib",
        "--hidden-import",
        "PyQt6.QtSvg",
    ]

    for rel in data_files:
        src = ROOT / rel
        if src.exists():
            cmd.extend(["--add-data", f"{src}{sep}."])

    cmd.append(str(ROOT / "avac_gui.py"))
    return cmd


def main() -> int:
    cmd = build_command()
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
