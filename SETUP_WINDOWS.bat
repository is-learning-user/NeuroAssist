@echo off
setlocal
cd /d "%~dp0"
echo === NeuroAssist: Python environment setup ===
where py >nul 2>&1
if not errorlevel 1 (py -3.12 -V >nul 2>&1 && (set "PY=py -3.12") || set "PY=py -3") else (set "PY=python")
%PY% -m venv "PythonServer\.venv"
if errorlevel 1 goto fail
"PythonServer\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail
"PythonServer\.venv\Scripts\python.exe" -m pip install -r "PythonServer\requirements.txt"
if errorlevel 1 goto fail
echo.
echo Environment created. Run START_SERVER.bat, then open UnityProject in Unity Hub.
pause
exit /b 0
:fail
echo Setup failed. Check Python and Internet connection.
pause
exit /b 1
