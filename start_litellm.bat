@echo off
rem Backward-compatible alias: the unified launcher starts LiteLLM and Jev.
call "%~dp0start_model_services.bat"
exit /b %errorlevel%
