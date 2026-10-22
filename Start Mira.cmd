@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Mira's Python environment is missing. Run "Setup Mira.cmd" first.
    pause
    exit /b 1
)
start "" /d "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch_mira.pyw"
exit /b %errorlevel%
