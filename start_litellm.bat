@echo off
setlocal DisableDelayedExpansion
cd /d "%~dp0"

rem This launcher only consumes an already-configured Windows environment variable.
rem It never prompts for, prints, or stores the upstream credential.
if not defined SJTU_ZHIYUAN_API_KEY (
  echo [MatFlow] LiteLLM was not started: SJTU_ZHIYUAN_API_KEY is unavailable to this Windows session.
  echo [MatFlow] Set it as a User environment variable, then open a new terminal or sign in again.
  pause
  exit /b 1
)

where uv >nul 2>nul
if errorlevel 1 (
  echo [MatFlow] uv was not found on PATH.
  echo [MatFlow] Install uv, then run this file again.
  pause
  exit /b 1
)

if not exist "config\litellm.yaml" (
  echo [MatFlow] LiteLLM configuration is missing: config\litellm.yaml
  pause
  exit /b 1
)

powershell -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:4000/health/readiness' -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 (
  echo [MatFlow] LiteLLM is already running at http://127.0.0.1:4000.
  pause
  exit /b 0
)

echo [MatFlow] Starting local LiteLLM gateway at http://127.0.0.1:4000 ...
echo [MatFlow] Close this window to stop the gateway.
uv run litellm --config "config\litellm.yaml" --port 4000

if errorlevel 1 (
  echo.
  echo [MatFlow] LiteLLM stopped with an error.
  pause
)
