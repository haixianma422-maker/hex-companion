@echo off
cd /d "%~dp0"
py -3.13 -m venv .venv
if errorlevel 1 (
  echo Python 3.13 is required. Install it and try again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
echo Setup complete. Open start_demo.cmd to launch.
pause
