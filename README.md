# AVAC 4.1

AVAC is an avalanche-dynamics model with a desktop GUI workflow.
The GUI is portable: install the GUI environment once, then use it with different project folders.

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

Reboot if Windows asks you to. You can also install it from the [Windows Store](https://apps.microsoft.com/detail/9pdxgncfsczv?hl=en-US&gl=CH).

### Step B: Install system packages in Ubuntu

Open Ubuntu and run:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip gfortran make ninja-build libgl1 libegl1 libxcb-cursor0 libnspr4 libnss3 libxcb-dri3-0 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libxkbfile1 libgbm1 libasound2t64 ffmpeg
```

Important:
- Step B is a **system-level** install (inside your WSL distro), not a repository install.
- If you delete/reclone the repository and restart from Step C, Step B is still required at least once in that distro.
- Safe rule: whenever in doubt, rerun Step B. `apt-get install` is idempotent.

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
python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('PyQt6-WebEngine OK')"
```

If the import command fails with missing shared libraries, rerun Step B:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip gfortran make ninja-build libgl1 libegl1 libxcb-cursor0 libnspr4 libnss3 libxcb-dri3-0 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libxkbfile1 libgbm1 libasound2t64 ffmpeg
```

### Step E: Launch GUI

```bash
python avac_gui.py
```

Every time you open a new terminal, activate the same environment before launching:

```bash
cd /path/to/avac
source env/bin/activate
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

If the GUI says `Leaflet editor is unavailable because PyQt6-WebEngine is not installed`:

```bash
cd /path/to/avac
source env/bin/activate
pip install --upgrade PyQt6-WebEngine
python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('PyQt6-WebEngine OK')"
```

If you get `ImportError: libnspr4.so: cannot open shared object file`:

```bash
sudo apt-get update
sudo apt-get install -y libnspr4 libnss3
cd /path/to/avac
source env/bin/activate
python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('PyQt6-WebEngine OK')"
```

If you get `ImportError: libxkbfile.so... cannot open shared object file`:

```bash
sudo apt-get update
sudo apt-get install -y libxkbfile1
cd /path/to/avac
source env/bin/activate
python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('PyQt6-WebEngine OK')"
```

If apt says `libasound2 has no installation candidate`:

```bash
sudo apt-get update
sudo apt-get install -y libasound2t64
```

(`libasound2t64` is the Ubuntu 24.04 package name.)

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

If the Windows taskbar title shows `[WARN: COPY MODE]` before `AVAC`:

This warning is added by WSLg (not by AVAC).

The GUI now auto-writes the required `.wslgconfig` settings on startup in WSL.  
If this is the first launch on a new machine, run this once and restart WSLg:

```powershell
wsl --shutdown
```

Manual fallback (if needed), from Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\disable_wslg_copy_warning_title.ps1
wsl --shutdown
```

Then launch AVAC again.

If it still appears, run PowerShell as Administrator and apply the system-wide config too:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\disable_wslg_copy_warning_title.ps1 -SystemWide
wsl --shutdown
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

## 7) Windows desktop icon (direct access)

Yes, you can launch AVAC from a Windows icon (without opening WSL manually).

From **Windows PowerShell** in the repository folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_windows_shortcut.ps1
```

This creates an `AVAC GUI` shortcut on your Windows Desktop that launches:
- WSL
- the repo folder
- `env/bin/activate`
- `python avac_gui.py`

## 8) Legacy notebook workflow (optional)

Repository notebooks:

- `AVAC.ipynb`
- `yaml_export.ipynb`

Use this path only if you specifically want the notebook-based workflow.

## 9) Developer/CI (optional)

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
