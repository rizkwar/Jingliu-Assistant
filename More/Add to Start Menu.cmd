@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\Create-Shortcut.ps1" -StartMenu
set "jinger_result=%errorlevel%"
echo.
echo Search for "Jingliu" from the taskbar or Start menu to open her.
pause
exit /b %jinger_result%
