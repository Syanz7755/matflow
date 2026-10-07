<#
Makes the MatFlow LLM gateway available: reuses a healthy LiteLLM gateway that
already accepts the configured key, or starts one from config/litellm.yaml.

Everything is read from config/llm.json (host, port, key variable, LiteLLM
config). -Port and -ConfigPath override it for one run. No credential value is
ever printed: only environment-variable *names* appear in messages.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = '',
    [int]$Port = 0,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
# Invoke-WebRequest's progress bar throws when output is captured; keep it off.
$ProgressPreference = 'SilentlyContinue'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $ConfigPath) { $ConfigPath = Join-Path $projectRoot 'config\llm.json' }
$config = Get-Content -Raw (Resolve-Path $ConfigPath).Path | ConvertFrom-Json
if ($config.version -ne 1 -or -not $config.gateway) { throw 'config/llm.json must declare version 1 and a gateway.' }

$gateway = $config.gateway
$hostName = [string]$gateway.host
$gatewayPort = if ($Port -gt 0) { $Port } else { [int]$gateway.port }
$keyName = [string]$gateway.api_key_env
$base = "http://${hostName}:$gatewayPort"

function Import-UserVariable([string]$Name) {
    # A variable set with setx (or the Windows dialog) is invisible to shells
    # that were already open. Pull it into this process without displaying it.
    if ([Environment]::GetEnvironmentVariable($Name, 'Process')) { return $true }
    foreach ($scope in 'User', 'Machine') {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        if ($value) { [Environment]::SetEnvironmentVariable($Name, $value, 'Process'); return $true }
    }
    return $false
}

function Get-Status {
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri "$base/health/readiness" -TimeoutSec 3
        if ($health.StatusCode -lt 200 -or $health.StatusCode -ge 300) { return @{ state = 'unhealthy' } }
    } catch {
        return @{ state = 'down' }
    }
    try {
        $headers = @{ Authorization = "Bearer $([Environment]::GetEnvironmentVariable($keyName))" }
        $models = Invoke-RestMethod -Uri "$base/v1/models" -Headers $headers -TimeoutSec 5
        return @{ state = 'ready'; models = @($models.data | ForEach-Object { $_.id }) }
    } catch {
        return @{ state = 'rejects_key' }
    }
}

function Write-Ready($Status) {
    $served = $Status.models
    $missing = @($config.models | Where-Object { $served -notcontains $_ })
    Write-Host "[MatFlow] LLM gateway ready at $base/v1 (models: $($served -join ', '))."
    if ($missing.Count) {
        Write-Warning "config/llm.json lists model(s) the gateway does not serve: $($missing -join ', ')."
    }
}

if (-not (Import-UserVariable $keyName)) {
    throw "Environment variable '$keyName' is not set. Set it (for example: setx $keyName <value>) and run this again."
}

$status = Get-Status
if ($status.state -eq 'ready') { Write-Ready $status; exit 0 }
if ($status.state -eq 'rejects_key') {
    throw "A gateway is running at $base but rejects the key in '$keyName'. Stop it or point config/llm.json at another port."
}
if ($status.state -eq 'unhealthy') { throw "Port $gatewayPort answers but its LiteLLM readiness check fails." }
if ($CheckOnly) { throw "No LLM gateway is running at $base." }

# Start a gateway. The upstream provider key is referenced by config/litellm.yaml.
$litellmConfig = Join-Path $projectRoot ([string]$gateway.litellm_config)
foreach ($name in (Select-String -Path $litellmConfig -Pattern 'os\.environ/([A-Za-z0-9_]+)' -AllMatches).Matches | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique) {
    if (-not (Import-UserVariable $name)) { throw "config/litellm.yaml needs environment variable '$name', which is not set." }
}
$executable = $env:MATFLOW_LITELLM_EXE
$arguments = @('--config', $litellmConfig, '--host', $hostName, '--port', "$gatewayPort")
if (-not $executable) {
    $local = Join-Path $projectRoot '.venv\Scripts\litellm.exe'
    if (Test-Path -LiteralPath $local) { $executable = $local }
    elseif (Get-Command litellm -ErrorAction SilentlyContinue) { $executable = 'litellm' }
    else { $executable = 'uv'; $arguments = @('run', 'litellm') + $arguments }
}

Write-Host "[MatFlow] Starting LiteLLM gateway on $base ..."
$process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
$deadline = (Get-Date).AddSeconds([int]$gateway.startup_timeout_seconds)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) { throw "LiteLLM exited (code $($process.ExitCode)) before it became ready." }
    $status = Get-Status
    if ($status.state -eq 'ready') { Write-Ready $status; exit 0 }
    Start-Sleep -Milliseconds 500
}
if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
throw "LiteLLM did not become ready within $($gateway.startup_timeout_seconds) seconds."
