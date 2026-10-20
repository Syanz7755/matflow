<#
Regenerate and verify deterministic teaching-lab fixtures and prompt cases.
This is offline: it never calls Jev, LiteLLM, or an external tool-search service.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    uv run python tests\tools\generate_teaching_lab_suite.py
    uv run python tests\tools\verify_teaching_lab_suite.py --check
} finally {
    Pop-Location
}
