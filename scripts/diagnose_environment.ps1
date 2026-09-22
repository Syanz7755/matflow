<#
Read-only MatFlow environment diagnostics. uv is the default runtime manager.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Write-Host "MatFlow environment diagnostics" -ForegroundColor Cyan
Write-Host "Project: $projectRoot"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found on PATH. Install it from https://docs.astral.sh/uv/getting-started/installation/ and retry."
}

Write-Host "uv: $(& uv --version)"

Push-Location $projectRoot
try {
    if (Test-Path '.venv') { Write-Host 'uv virtual environment: OK' } else { Write-Warning 'uv virtual environment missing. Run: uv sync' }
    & uv run python -c "import fastapi,numpy,pandas; print('Python packages: OK')"
    if (Test-Path 'frontend/node_modules') { Write-Host 'Frontend packages: OK' } else { Write-Warning 'Frontend packages missing. Run: uv run matflow install-frontend' }
    if (Get-Command node -ErrorAction SilentlyContinue) { Write-Host "Node: $(& node --version)" } else { Write-Warning 'Node.js missing. Install Node.js 22 or later.' }
    & uv run matflow diagnose
} finally { Pop-Location }
