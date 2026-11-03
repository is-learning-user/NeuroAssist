@echo off
setlocal
cd /d "%~dp0\PythonServer"
if not exist ".venv\Scripts\python.exe" (echo Run SETUP_WINDOWS.bat first & pause & exit /b 1)
".venv\Scripts\python.exe" -m pytest -q tests/test_pipeline.py tests/test_streaming.py tests/test_demo_server.py
pause
