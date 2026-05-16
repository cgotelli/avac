from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_minimal_avac_run_produces_output() -> None:
    if os.environ.get("AVAC_RUN_INTEGRATION") != "1":
        pytest.skip("Set AVAC_RUN_INTEGRATION=1 to run heavy end-to-end AVAC test")

    root = Path(__file__).resolve().parent.parent
    if platform.system().lower().startswith("win"):
        pytest.skip("Native Windows make/gfortran flow is expected through WSL")
    if shutil.which("make") is None:
        pytest.skip("make is not available")
    if shutil.which("gfortran") is None:
        pytest.skip("gfortran is not available")
    if not (root / "Makefile").exists():
        pytest.skip("Makefile not found; extract AVAC files first")

    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "2")

    subprocess.run(["make", "clean"], cwd=root, env=env, check=False, timeout=120)
    run = subprocess.run(["make", ".output"], cwd=root, env=env, check=False, timeout=1800, capture_output=True, text=True)
    if run.returncode != 0:
        pytest.fail(f"AVAC run failed with exit code {run.returncode}\nSTDOUT:\n{run.stdout}\nSTDERR:\n{run.stderr}")

    output_dir = root / "_output"
    assert output_dir.exists(), "_output directory was not created"
    frames = list(output_dir.glob("fort.q*"))
    assert len(frames) > 0, "No output frames were produced"
