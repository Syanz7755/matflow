@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

rem Backend-only verification: does not start, build, or test the WebUI.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test_backend.ps1"
if errorlevel 1 (
  echo.
  echo [MatFlow] Backend verification failed.
  pause
  exit /b 1
)

echo [MatFlow] Backend verification passed.
