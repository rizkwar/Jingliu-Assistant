@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Jinger's Python environment is missing. Run "Setup Jinger.cmd" first.
    pause
    exit /b 1
)
start "" /d "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch_jinger.pyw"
exit /b %errorlevel%
