@echo off
rem Double-click launcher for the MatFlow live demo. It delegates to
rem scripts/start_demo.ps1, which starts the model gateways, the backend and
rem the WebUI from the sibling frontend repository.
setlocal
cd /d "%~dp0"
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_demo.ps1" %*
if errorlevel 1 pause
