<# Runs only MatFlow's Python backend contract and integration tests. #>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    & uv run --group dev python -m unittest discover -v
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
