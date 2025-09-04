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


# Caveat
The main problem is usually the compiler parameters. Check lines 24 and 25 of Makefile and change if needed:
	FFLAGS ?= -O2 -fopenmp
	OMP_NUM_THREADS = 8


# History of changes
Last update 30 Aug 2025
* change of qinit_module.f90
* change of AVAC.ipynb: inclusion of a profile for plotting cross-sections

