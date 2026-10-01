@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test_configured_scenarios.ps1" %*
exit /b %ERRORLEVEL%
