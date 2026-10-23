@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup Mira.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\setup_live2d.py
if errorlevel 1 (
  pause
  exit /b 1
)
pause
