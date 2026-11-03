@echo off
setlocal
cd /d "%~dp0\PythonServer"
set "OMP_NUM_THREADS=1"
set "OPENBLAS_NUM_THREADS=1"
set "MKL_NUM_THREADS=1"
set "NUMEXPR_NUM_THREADS=1"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. Run SETUP_WINDOWS.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.serve_demo --seconds 40
if errorlevel 1 echo Server stopped with error. Verify Python environment and data files.
pause
