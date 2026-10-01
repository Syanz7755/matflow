[CmdletBinding()]
param(
    [switch]$OnlineJev,
    [switch]$OnlineLlm
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$reportDir = Join-Path $projectRoot 'examples\reports\configured_scenarios'
$env:MATFLOW_RUN_JEV_APPLICATION_TESTS = if ($OnlineJev) { '1' } else { '0' }
$env:MATFLOW_RUN_LLM_APPLICATION_TESTS = if ($OnlineLlm) { '1' } else { '0' }
$env:MATFLOW_SCENARIO_REPORT_DIR = $reportDir
Push-Location $projectRoot
try {
    & uv run --group dev python scripts/run_configured_scenarios.py
    $offlineExit = $LASTEXITCODE
    $onlineExit = 0
    if ($OnlineJev -or $OnlineLlm) {
        & uv run --group dev python -m unittest tests.test_configured_online_scenarios -v
        $onlineExit = $LASTEXITCODE
    }
    if ($offlineExit -ne 0 -or $onlineExit -ne 0) { exit 1 }
    exit 0
} finally {
    Pop-Location
}
