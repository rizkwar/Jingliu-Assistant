@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is required for this separate avatar preview.
  pause
  exit /b 1
)
node "%~dp0scripts\preview_mesh_avatar.mjs" --open
if errorlevel 1 pause
