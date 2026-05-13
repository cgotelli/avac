@echo off
setlocal

where wsl >nul 2>nul
if %errorlevel% neq 0 (
  echo WSL is not installed. Install WSL and run again.
  exit /b 1
)

set REPO_WIN=%~dp0
for /f "delims=" %%i in ('wsl wslpath "%REPO_WIN%"') do set REPO_WSL=%%i

if "%REPO_WSL%"=="" (
  echo Could not convert repository path to WSL path.
  exit /b 1
)

echo Starting AVAC GUI in WSL at %REPO_WSL%
wsl -e bash -lc "cd '%REPO_WSL%' && if [ -f ./env/bin/activate ]; then source ./env/bin/activate; fi && python3 avac_gui.py"

endlocal
