@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo [MatFlow] uv was not found on PATH.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test_teaching_lab_suite.ps1"
if errorlevel 1 (
  echo.
  echo [MatFlow] Teaching-lab suite acceptance failed.
  pause
  exit /b 1
)

echo [MatFlow] Teaching-lab suite acceptance passed.
