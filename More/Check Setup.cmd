@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0..\.venv\Scripts\python.exe" (
    echo Jinger's Python environment is missing. Run "Setup Jinger.cmd" first.
    pause
    exit /b 1
)
pushd "%~dp0.."
if errorlevel 1 exit /b 1
"%~dp0..\.venv\Scripts\python.exe" -m companion.app.doctor --engines
set "jinger_result=%errorlevel%"
popd
echo.
pause
exit /b %jinger_result%
