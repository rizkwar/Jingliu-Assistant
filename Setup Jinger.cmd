@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-Jinger.ps1"
set "jinger_result=%errorlevel%"
echo.
pause
exit /b %jinger_result%
