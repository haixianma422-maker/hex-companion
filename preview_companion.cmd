@echo off
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py" --preview
