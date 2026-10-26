@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0..\.."
where node >nul 2>nul
if errorlevel 1 (
    echo Node.js is missing. Install it before running the standalone rig viewer.
    pause
    exit /b 1
)
node dev\rig\preview_inochi_avatar.mjs --open
if errorlevel 1 pause
