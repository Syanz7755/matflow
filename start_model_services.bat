@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

rem The project configuration declares both the local Jev gateway and the
rem online-API LiteLLM gateway. No credential value is accepted or displayed here.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_model_services.ps1" -ConfigPath "%~dp0config\model_services.json"
if errorlevel 1 (
  echo.
  echo [MatFlow] One or more model services could not be started.
  pause
  exit /b 1
)

echo [MatFlow] All configured model services are ready.
