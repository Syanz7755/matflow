@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MatFlow] uv was not found on PATH.
  echo Install uv, then run this file again.
  pause
  exit /b 1
)

echo [MatFlow] Starting local workspace...
uv run matflow start

if errorlevel 1 (
  echo.
  echo [MatFlow] Startup stopped with an error.
  pause
)
