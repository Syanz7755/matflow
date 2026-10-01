<#
Runs data-driven Jev and LLM contract/application tests.

Offline contract and safety tests are always included. Live model tests are
opt-in and discover models, endpoints, thresholds, tools, prompts, fixtures,
and expected results from the project configuration and scenario manifests.
#>
[CmdletBinding()]
param(
    [switch]$OnlineJev,
    [switch]$OnlineLlm
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $projectRoot
try {
    $env:MATFLOW_RUN_JEV_APPLICATION_TESTS = if ($OnlineJev) { '1' } else { '0' }
    $env:MATFLOW_RUN_LLM_APPLICATION_TESTS = if ($OnlineLlm) { '1' } else { '0' }
    $env:MATFLOW_SCENARIO_REPORT_DIR = Join-Path $projectRoot 'examples\reports\configured_scenarios'
    & uv run --group dev python -m unittest `
        tests.test_jev_decision_behavior `
        tests.test_llm_gateway_behavior `
        tests.test_model_service_startup `
        tests.test_model_services_config `
        tests.test_litellm_config `
        tests.test_model_application_scenarios `
        tests.test_scenario_config `
        tests.test_analysis_recipes `
        tests.test_tool_recipe_lifecycle `
        tests.test_tool_recipe_repair `
        tests.test_configured_scenario_runner `
        tests.test_configured_online_scenarios `
        -v
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
