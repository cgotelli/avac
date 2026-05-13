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

An optional file (profil.shp) is provided for plotting cross-sections.

For the moment, you can select the language (Franch/English) for customizing figure captions. In progress...

## Caveat
The main problem is usually the compiler parameters. Check lines 24 and 25 of Makefile and change if needed:

	FFLAGS ?= -O2 -fopenmp
	OMP_NUM_THREADS = 8


## History of changes
Last update 30 Aug 2025
* change of qinit_module.f90
* change of AVAC.ipynb: inclusion of a profile for plotting cross-sections


## AVAC Desktop GUI (new)

A cross-platform desktop GUI is now included to replace the notebook-driven flow with a guided 5-step workflow.

### Features implemented

- 5-tab wizard:
  1. **Project Setup**: project folder, language, environment checks, AVAC file extraction, local Clawpack install
  2. **Input Data**: DEM and shapefile selection, metadata validation, map preview with hillshade/slope overlays
  3. **Parameters**: grouped release/rheology/computation/output controls, YAML load/save, validation, initial depth preview
  4. **Run Simulation**: run `make clean && make .output`, stream logs live, stop run, monitor progress
  5. **Results & Analysis**: max map display/export, profile loading, statistics, animation file launcher, time-series placeholder

- Portability helpers:
  - `scripts/bootstrap_local_env.sh`
  - `environment.yml`
  - `launch.bat` (Windows -> WSL launcher)
  - `Dockerfile`

### Run the GUI

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

### Notes

- Local Clawpack setup uses `clawpack-v5.14.0.zip` from this repository
- AVAC solver files are extracted from `files.tar.gz` into the selected project folder
- For headless/container runs, adapt Docker settings for display forwarding as needed
