# avac 4.1
This is the new version of AVAC, an avalanche-dynamics model.

AVAC 4 needs Clawpack version 5.13 (AVAC is unlikely to work with earlier clawpack versions). See the related page https://www.clawpack.org/installing.html. It also needs a number of standard python scripts (numpy, matplotlib, IPython, etc.) whose installation is not a problem and a jupyter environnement (provided by an Integrated development environment such as Anaconda or Visual Studio Code).

See the jupyter notebook for installation. The notebook detects whether clawpack is installed and up-to-date. If not, please see https://www.clawpack.org/installing.html

The folder contains two jupyter notebooks:
* AVAC.ipynb: installs and runs AVAC. It offers several possibilities for plotting the results and exporting them.
* yaml_export.ipynb: contains all the parameters required by AVAC to run. These parameters include the names of the topographic files, the rheological parameters, the computation parameters... All these parameters are defined in a dictionary, which is then exported to a yaml file that will be read by setrun.py and AVAC.ipynb.

The folder contains two datasets for the sake of illustration:
* a raster file (topography)
* shapefile (position and limits of the starting areas)
Change with your own files if needed.

An optional file (`profil.shp`) is provided for plotting cross-sections.

## Caveat
The main problem is usually the compiler parameters. Check lines 24 and 25 of Makefile and change if needed:

	FFLAGS ?= -O2 -fopenmp
	OMP_NUM_THREADS = 8


## History of changes
Last update 30 Aug 2025
* change of qinit_module.f90
* change of AVAC.ipynb: inclusion of a profile for plotting cross-sections


## AVAC Desktop GUI (new)

A cross-platform desktop GUI is now included to replace the notebook-driven flow with a guided workflow.

### Features implemented

- 5-tab workflow:
  1. **Project Setup**: project folder selection, environment checks, AVAC file extraction, shared Clawpack install
  2. **Input Data & Shapes**: DEM and shapefile selection, metadata validation, map preview, plus embedded shape editing with Leaflet
  3. **Parameters**: grouped release/rheology/computation/output controls, YAML load/save, validation, initial depth preview
  4. **Run Simulation**: run `make clean && make .output`, stream logs live, stop run, monitor progress
  5. **Results & Analysis**: max maps, time maps, profile drawing/plotting/export, and animation export/playback

- Portability helpers:
  - `scripts/bootstrap_local_env.sh`
  - `environment.yml`
  - `launch.bat` (Windows -> WSL launcher)
  - `Dockerfile`

### New machine setup (Windows + WSL)

This repository is designed to run on Windows laptops through WSL (Ubuntu).
For GUI display, use Windows 11 (WSLg included) or Windows 10 with an external X server.

1. Install WSL2 + Ubuntu:
   ```powershell
   wsl --install -d Ubuntu
   ```
2. Open Ubuntu and install system dependencies:
   ```bash
   sudo apt-get update
   sudo apt-get install -y git python3 python3-venv python3-pip gfortran make ninja-build libgl1 libegl1 libxcb-cursor0 ffmpeg
   ```
3. Clone this repository and enter the repo root:
   ```bash
   git clone https://github.com/cgotelli/avac.git
   cd avac
   ```
4. Create Python environment and install GUI requirements:
   ```bash
   python3 -m venv env
   source env/bin/activate
   pip install -r requirements-gui.txt
   ```
5. Launch GUI:
   ```bash
   python avac_gui.py
   ```
6. In **Project Setup**:
   - Select a project folder.
   - Click **Extract AVAC Files to Project** (required for each new project folder).
   - Click **Install Shared Clawpack** (one-time per repository).

After Clawpack is installed once, you can switch project folders without reinstalling Clawpack.
Always launch the GUI from this repository root so bundled setup files (`clawpack-v5.14.0.zip`, `files.tar.gz`) are discoverable.

### First example run (quick validation)

After the GUI opens:

1. Go to **Project Setup**:
   - Click **Select Project Folder** and pick the repository root (`.../avac`).
   - Click **Extract AVAC Files to Project**.
   - Click **Install Shared Clawpack** (first run can take several minutes).
2. In **Project Setup**, click **Load Pralognan Example**.
3. Go to **Run Simulation**:
   - Click **Run AVAC (make .output)** and wait until completion.
4. Go to **Results & Analysis**:
   - Click **Load Last Run Results** and verify maps/frames appear.

### Run the GUI (quick)

From the repository root:

```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements-gui.txt
python avac_gui.py
```

Or use:

```bash
./scripts/bootstrap_local_env.sh
source env/bin/activate
python avac_gui.py
```

### Windows (WSL)

- Install WSL and an Ubuntu distribution
- Open command prompt in the repository folder and run `launch.bat`
- The launcher starts the GUI through WSL Python

If you see QtWebEngine/EGL errors (e.g. `Failed to get system egl display`), AVAC now applies software-rendering defaults automatically on Linux/WSL. If you need to disable this behavior for debugging, run:

```bash
AVAC_DISABLE_QT_COMPAT=1 python avac_gui.py
```

If you need to temporarily disable Leaflet/WebEngine on unstable graphics stacks, use:

```bash
AVAC_DISABLE_WEBENGINE=1 python avac_gui.py
```

If you see `Could not load the Qt platform plugin "xcb"`, launch without forcing xcb:

```bash
unset AVAC_FORCE_XCB
python avac_gui.py
```

If you do want xcb explicitly, install the runtime dependency first:

```bash
sudo apt-get update
sudo apt-get install -y libxcb-cursor0
```

### Notes

- Shared Clawpack setup uses `clawpack-v5.14.0.zip` from this repository and installs to `<repo>/.vendor/clawpack-src` by default.
- AVAC solver files are extracted from `files.tar.gz` into the selected project folder
- Optional override: set `AVAC_CLAW_ROOT=/absolute/path/to/clawpack-src` to force a custom shared location.
- For headless/container runs, adapt Docker settings for display forwarding as needed

### Testing portability (Windows/WSL, Linux, macOS)

Use local tests before each release:

```bash
python -m pip install -r requirements-gui.txt
python -m pip install -r requirements-dev.txt
pytest -q tests
```

Repository CI is configured in `.github/workflows/ci.yml` with a matrix on:

- `ubuntu-latest`
- `windows-latest`
- `macos-latest`

CI runs unit tests with an offscreen Qt backend (`QT_QPA_PLATFORM=offscreen`) and Agg matplotlib backend (`MPLBACKEND=Agg`) to validate core GUI-related services without a display.

### Optional end-to-end AVAC integration test

An integration test is available for a full `make .output` run and output verification.

```bash
AVAC_RUN_INTEGRATION=1 pytest -q tests/test_integration_avac_run.py -m integration
```

Notes:

- It is skipped by default (long-running).
- It requires `make`, `gfortran`, extracted AVAC solver files, and a Unix-like runtime (Linux/macOS or WSL).

### Build portable desktop bundles

Local build command:

```bash
python -m pip install -r requirements-gui.txt
python -m pip install -r requirements-build.txt
python scripts/build_desktop_bundle.py
```

The release workflow `.github/workflows/release-bundles.yml` builds bundles on Windows, Linux, and macOS.

- `workflow_dispatch`: build and store artifacts
- `v*` tag push: build bundles and attach zip assets to GitHub Release
