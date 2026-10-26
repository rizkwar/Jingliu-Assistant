@echo off
setlocal
cd /d "%~dp0.."
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is needed for this separate development preview.
  pause
  exit /b 1
)
node dev\preview_head_motion.mjs --open
if errorlevel 1 pause
