@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Create-Shortcut.ps1"
set "mira_result=%errorlevel%"
echo.
pause
exit /b %mira_result%
