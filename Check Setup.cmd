@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Mira's Python environment is missing. Run "Setup Mira.cmd" first.
    pause
    exit /b 1
)
pushd "%~dp0"
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" -m companion.doctor --engines
set "mira_result=%errorlevel%"
popd
echo.
pause
exit /b %mira_result%
