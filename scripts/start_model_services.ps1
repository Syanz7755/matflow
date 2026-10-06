<#
Starts the configured local model processes and waits for their health checks.
No credential values are read, written, or emitted; only environment-variable
names declared in the project configuration are checked.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
# Invoke-WebRequest draws a progress bar. When this script runs with redirected
# or captured output (tests, CI, wrapper launchers) that rendering throws
# HostException "Access is denied ... console output buffer", which the health
# probe below would misread as an unhealthy service and silently skip the
# readiness probe. Progress output must therefore stay off.
$ProgressPreference = 'SilentlyContinue'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $ConfigPath) { $ConfigPath = Join-Path $projectRoot 'config\model_services.json' }
$configFile = (Resolve-Path $ConfigPath).Path
$config = Get-Content -Raw $configFile | ConvertFrom-Json

if ($config.version -ne 1 -or -not $config.services) {
    throw 'model_services.json must declare version 1 and at least one service.'
}

function Resolve-ServicePath([string]$PathValue) {
    if ([IO.Path]::IsPathRooted($PathValue)) { return $PathValue }
    return Join-Path $projectRoot $PathValue
}

function Test-Healthy([string]$HealthUrl) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    } catch {
        return $false
    }
}

function Test-ServiceReady($Service) {
    if (-not (Test-Healthy $Service.health_url)) { return $false }
    if (-not $Service.PSObject.Properties.Name.Contains('readiness_url')) { return $true }
    $headers = @{}
    if ($Service.PSObject.Properties.Name.Contains('readiness_api_key_env')) {
        $credentialName = [string]$Service.readiness_api_key_env
        $credential = [Environment]::GetEnvironmentVariable($credentialName)
        if (-not $credential) { return $false }
        $headers.Authorization = "Bearer $credential"
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Service.readiness_url -Headers $headers -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    } catch {
        return $false
    }
}

function Assert-ServiceConfig($Service) {
    foreach ($field in 'id', 'mode', 'working_directory', 'executable', 'arguments', 'health_url', 'startup_timeout_seconds') {
        if (-not $Service.PSObject.Properties.Name.Contains($field)) {
            throw "Service configuration is missing '$field'."
        }
    }
    $workingDirectory = Resolve-ServicePath $Service.working_directory
    if (-not (Test-Path -LiteralPath $workingDirectory -PathType Container)) {
        throw "[$($Service.id)] Working directory does not exist."
    }
    if ($Service.executable -eq 'uv' -and -not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "[$($Service.id)] uv was not found on PATH."
    }
    if ($Service.executable -eq 'powershell.exe' -and -not (Get-Command powershell.exe -ErrorAction SilentlyContinue)) {
        throw "[$($Service.id)] powershell.exe was not found on PATH."
    }
    foreach ($environmentName in @($Service.required_environment)) {
        if (-not $ValidateOnly -and -not [Environment]::GetEnvironmentVariable([string]$environmentName)) {
            throw "[$($Service.id)] Required environment variable '$environmentName' is unavailable in this session."
        }
    }
    if ($Service.PSObject.Properties.Name.Contains('readiness_api_key_env') -and
        -not $Service.PSObject.Properties.Name.Contains('readiness_url')) {
        throw "[$($Service.id)] readiness_api_key_env requires readiness_url."
    }
}

$enabled = @($config.services | Where-Object { $_.enabled -eq $true })
foreach ($service in $enabled) { Assert-ServiceConfig $service }
if ($ValidateOnly) {
    Write-Host "[MatFlow] Model service configuration is valid for $($enabled.Count) enabled service(s)."
    exit 0
}

$started = @()
try {
    foreach ($service in $enabled) {
        if (Test-ServiceReady $service) {
            Write-Host "[MatFlow] $($service.id) is already ready ($($service.mode))."
            continue
        }
        $workingDirectory = Resolve-ServicePath $service.working_directory
        Write-Host "[MatFlow] Starting $($service.id) ($($service.mode))..."
        $process = Start-Process -FilePath $service.executable -ArgumentList @($service.arguments) -WorkingDirectory $workingDirectory -WindowStyle Hidden -PassThru
        $started += $process
        $deadline = (Get-Date).AddSeconds([int]$service.startup_timeout_seconds)
        while ((Get-Date) -lt $deadline) {
            if (Test-ServiceReady $service) { break }
            if ($process.HasExited) { throw "[$($service.id)] Process exited before its health check passed." }
            Start-Sleep -Milliseconds 500
        }
        if (-not (Test-ServiceReady $service)) {
            throw "[$($service.id)] Readiness check did not pass before timeout."
        }
        Write-Host "[MatFlow] $($service.id) is ready."
    }
} catch {
    foreach ($process in $started) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
    throw
}
