@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-Chatterbox.ps1"
set "chatterbox_result=%errorlevel%"
echo.
pause
exit /b %chatterbox_result%
