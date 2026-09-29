<#
Starts MatFlow through uv, the default runtime manager.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found on PATH. Install uv, then run: uv sync"
}
Push-Location $projectRoot
try { & uv run matflow start --ui webui } finally { Pop-Location }
