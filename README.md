# AVAC 4.1

AVAC is an avalanche-dynamics model with a desktop GUI workflow.

This README is organized for a **first-time Windows PC with WSL** installation.

## 1) First-time install on Windows + WSL (recommended)

### Prerequisites

- Windows 11 + WSLg (best experience), or Windows 10 + an external X server
- Internet access during setup

### Step A: Install WSL + Ubuntu

In Windows PowerShell:

```powershell
wsl --install -d Ubuntu
```

Reboot if Windows asks you to.

### Step B: Install system packages in Ubuntu

Open Ubuntu and run:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip gfortran make ninja-build libgl1 libegl1 libxcb-cursor0 ffmpeg
```

### Step C: Clone the repository

```bash
git clone https://github.com/cgotelli/avac.git
cd avac
```

### Step D: Create Python environment and install GUI dependencies

```bash
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements-gui.txt
```

### Step E: Launch GUI

```bash
python avac_gui.py
```

## 2) Run the bundled example (validation)

After the GUI opens:

1. Go to **Project Setup**
2. Click **Select Project Folder** and choose the repository root (`.../avac`)
3. Click **Extract AVAC Files to Project**
4. Click **Install Shared Clawpack** (first run may take several minutes)
5. Click **Load Pralognan Example**
6. Go to **Run Simulation** and click **Run AVAC (make .output)**
7. Go to **Results & Analysis** and click **Load Last Run Results**

## 3) Important notes

- Shared Clawpack is installed to `<repo>/.vendor/clawpack-src` by default.
- AVAC solver files are extracted from `files.tar.gz` into the selected project folder.
- Always launch the GUI from the repository root so bundled setup files are found.
- Optional override for shared Clawpack location:
  - `AVAC_CLAW_ROOT=/absolute/path/to/clawpack-src`

## 4) Troubleshooting (WSL/Qt)

If QtWebEngine/EGL fails:

```bash
AVAC_DISABLE_QT_COMPAT=1 python avac_gui.py
```

If embedded Leaflet/WebEngine is unstable:

```bash
AVAC_DISABLE_WEBENGINE=1 python avac_gui.py
```

If Qt reports xcb platform issues:

```bash
unset AVAC_FORCE_XCB
python avac_gui.py
```

## 5) Requirements files

- `requirements-gui.txt`: required for running GUI
- `requirements-dev.txt`: optional, for tests
- `requirements-build.txt`: optional, for desktop bundle packaging

## 6) Optional helper script

Instead of manual `venv` creation:

```bash
./scripts/bootstrap_local_env.sh
source env/bin/activate
python avac_gui.py
```

## 7) Legacy notebook workflow (optional)

Repository notebooks:

- `AVAC.ipynb`
- `yaml_export.ipynb`

Use this path only if you specifically want the notebook-based workflow.

## 8) Developer/CI (optional)

Run tests:

```bash
python -m pip install -r requirements-gui.txt
python -m pip install -r requirements-dev.txt
pytest -q tests
```

Optional integration test:

```bash
AVAC_RUN_INTEGRATION=1 pytest -q tests/test_integration_avac_run.py -m integration
```

Build portable bundles:

```bash
python -m pip install -r requirements-gui.txt
python -m pip install -r requirements-build.txt
python scripts/build_desktop_bundle.py
```

CI workflow file:

- `.github/workflows/ci.yml`
