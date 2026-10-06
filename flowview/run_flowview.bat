@echo off
rem FlowView launcher: prints the MatFlow backend flow as Mermaid diagrams or terminal tables.
rem
rem FlowView is a read-only CLI subproject (flowview/). This launcher only:
rem   1. moves to the repository root, so `python -m flowview` resolves without installing;
rem   2. picks the repository virtualenv interpreter when it exists, else `python` on PATH;
rem   3. forwards every argument to `python -m flowview`;
rem   4. propagates FlowView's exit code (0 ok, 1 internal, 2 usage, 3 input/backend problem).
setlocal DisableDelayedExpansion
cd /d "%~dp0.."
set "MATFLOW_ROOT=%CD%"

set "MATFLOW_PY="
if exist "%MATFLOW_ROOT%\.venv\Scripts\python.exe" set "MATFLOW_PY=%MATFLOW_ROOT%\.venv\Scripts\python.exe"
if not defined MATFLOW_PY (
  where python >nul 2>nul
  if not errorlevel 1 set "MATFLOW_PY=python"
)
if not defined MATFLOW_PY (
  echo [MatFlow] FlowView could not find a Python interpreter.
  echo [MatFlow] Looked for "%MATFLOW_ROOT%\.venv\Scripts\python.exe" and for "python" on PATH.
  echo [MatFlow] Install Python 3.11+ or create the repository .venv, then retry.
  echo [MatFlow] Example: .\.venv\Scripts\python.exe -m flowview --help
  exit /b 9009
)

"%MATFLOW_PY%" -m flowview %*
set "MATFLOW_EXIT=%ERRORLEVEL%"

if not "%MATFLOW_EXIT%"=="0" (
  echo [MatFlow] flowview exited with code %MATFLOW_EXIT%.
)
exit /b %MATFLOW_EXIT%
