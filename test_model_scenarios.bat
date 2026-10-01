@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test_model_scenarios.ps1" %*
if errorlevel 1 (
  echo.
  echo [MatFlow] Model scenario verification failed.
  exit /b 1
)

echo [MatFlow] Model scenario verification passed.
