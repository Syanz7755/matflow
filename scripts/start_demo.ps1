<#
.SYNOPSIS
  Start the whole MatFlow live demo on this machine with one command.

.DESCRIPTION
  Starts, reusing anything already healthy:
    1. the local LiteLLM gateway for the SJTU model catalogue   (127.0.0.1:4078)
    2. the MatFlow-owned DeepSeek official gateway               (127.0.0.1:4080)
    3. the MatFlow backend                                       (127.0.0.1:8000)
    4. the WebUI dev server for the sibling frontend repository  (127.0.0.1:5173)

  Credentials are read from the Windows *User* environment scope into this
  process only (never printed, never written to disk):
    SJTU_ZHIYUAN_API_KEY            upstream credential for the SJTU gateway
    LITELLM_DEFAULT_API_KEY         caller key for both local gateways
    DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE  DeepSeek official only (optional)

  Press Ctrl+C to stop the processes this script started.  Then open
  http://127.0.0.1:5173 and follow
  docs/acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md.

.EXAMPLE
  pwsh -File scripts/start_demo.ps1
  pwsh -File scripts/start_demo.ps1 -FrontendPort 5175 -SkipDeepSeek
#>
[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$SjtPort = 4078,
    [int]$DeepSeekPort = 4080,
    [string]$Save = 'live-demo',
    [switch]$SkipDeepSeek,
    [switch]$NoWait
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path (Split-Path -Parent $repo) 'matflow-frontend'
$logDir = Join-Path $repo '.tmp/live'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$started = [System.Collections.Generic.List[int]]::new()

function Import-UserSecret([string]$Name) {
    if ([Environment]::GetEnvironmentVariable($Name)) { return $true }
    $value = [Environment]::GetEnvironmentVariable($Name, 'User')
    if (-not $value) { return $false }
    [Environment]::SetEnvironmentVariable($Name, $value)
    return $true
}

function Test-Port([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Test-Health([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200 } catch { return $false }
}

function Wait-Url([string]$Url, [string]$Label, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Health $Url) { Write-Host "  $Label ready: $Url" -ForegroundColor Green; return }
        Start-Sleep -Milliseconds 700
    }
    throw "$Label did not become healthy at $Url within $Seconds s. See $logDir."
}

function Start-Logged([string]$FilePath, [string]$Arguments, [string]$Label, [string]$WorkingDirectory) {
    $safe = $Label -replace '[^A-Za-z0-9_.-]', '-'
    $out = Join-Path $logDir "$safe.out.log"
    $err = Join-Path $logDir "$safe.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory `
        -PassThru -NoNewWindow -RedirectStandardOutput $out -RedirectStandardError $err
    $started.Add($process.Id)
    Write-Host "  started $Label (pid $($process.Id))" -ForegroundColor DarkGray
    return $process
}

function Stop-Started {
    foreach ($id in $started) {
        try { & taskkill /PID $id /T /F *> $null } catch { }
    }
}

try {
    Write-Host 'MatFlow live demo' -ForegroundColor Cyan
    Write-Host '[0/4] credentials from the User environment scope (values are never printed)' -ForegroundColor Cyan
    $haveSjt = Import-UserSecret 'SJTU_ZHIYUAN_API_KEY'
    $haveCaller = Import-UserSecret 'LITELLM_DEFAULT_API_KEY'
    $haveDeepSeek = Import-UserSecret 'DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE'
    if (-not $haveCaller) { throw 'LITELLM_DEFAULT_API_KEY is not configured in the User environment scope.' }
    if (-not $haveSjt) { throw 'SJTU_ZHIYUAN_API_KEY is not configured in the User environment scope.' }
    Write-Host ("  SJTU key: yes | gateway caller key: yes | DeepSeek exclusive key: {0}" -f $(if ($haveDeepSeek) { 'yes' } else { 'no' })) -ForegroundColor DarkGray

    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) { throw 'uv was not found on PATH. Install uv first (https://docs.astral.sh/uv/).' }
    $npx = (Get-Command npx.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npx) { $npx = (Get-Command npx -ErrorAction SilentlyContinue).Source }
    if (-not (Test-Path $frontend)) { throw "Frontend repository not found next to this checkout: $frontend" }

    Write-Host '[1/4] SJTU model gateway' -ForegroundColor Cyan
    if (Test-Health "http://127.0.0.1:$SjtPort/health/readiness") {
        Write-Host "  reusing the gateway already listening on $SjtPort" -ForegroundColor DarkGray
    } else {
        if (Test-Port $SjtPort) { throw "Port $SjtPort is in use but the gateway is not healthy." }
        Start-Logged $uv "run litellm --config config/litellm.yaml --host 127.0.0.1 --port $SjtPort" 'sjt-gateway' $repo | Out-Null
        Wait-Url "http://127.0.0.1:$SjtPort/health/readiness" 'SJTU gateway' 120
    }

    Write-Host '[2/4] DeepSeek official gateway' -ForegroundColor Cyan
    if ($SkipDeepSeek -or -not $haveDeepSeek) {
        Write-Host '  skipped (no exclusive key or -SkipDeepSeek)' -ForegroundColor DarkGray
    } elseif (Test-Health "http://127.0.0.1:$DeepSeekPort/health/readiness") {
        Write-Host "  reusing the gateway already listening on $DeepSeekPort" -ForegroundColor DarkGray
    } else {
        if (Test-Port $DeepSeekPort) { throw "Port $DeepSeekPort is in use but the gateway is not healthy." }
        Start-Logged $uv "run litellm --config config/litellm-deepseek.yaml --host 127.0.0.1 --port $DeepSeekPort" 'deepseek-gateway' $repo | Out-Null
        Wait-Url "http://127.0.0.1:$DeepSeekPort/health/readiness" 'DeepSeek gateway' 120
    }

    Write-Host '[3/4] MatFlow backend' -ForegroundColor Cyan
    if (Test-Health "http://127.0.0.1:$BackendPort/api/capabilities") {
        Write-Host "  reusing the backend already listening on $BackendPort" -ForegroundColor DarkGray
    } else {
        if (Test-Port $BackendPort) { throw "Port $BackendPort is in use but the backend is not healthy." }
        $env:MATFLOW_CORS_ORIGINS = "http://127.0.0.1:$FrontendPort"
        $python = Join-Path $repo '.venv\Scripts\python.exe'
        if (-not (Test-Path $python)) { throw "Backend virtualenv not found at $python. Run: uv sync" }
        Start-Logged $python "-m uvicorn backend.main:app --host 127.0.0.1 --port $BackendPort" 'backend' $repo | Out-Null
        Wait-Url "http://127.0.0.1:$BackendPort/api/capabilities" 'backend' 120
    }
    if ($Save) {
        try {
            $headers = @{ 'Content-Type' = 'application/json' }
            Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/settings" -TimeoutSec 10 -UseBasicParsing -Headers $headers `
                -Method Get *> $null
        } catch { Write-Host "  note: could not read settings (continuing): $($_.Exception.Message)" -ForegroundColor DarkGray }
    }

    Write-Host '[4/4] WebUI dev server' -ForegroundColor Cyan
    if (Test-Health "http://127.0.0.1:$FrontendPort") {
        Write-Host "  reusing the WebUI already listening on $FrontendPort" -ForegroundColor DarkGray
    } else {
        if (Test-Port $FrontendPort) { throw "Port $FrontendPort is in use but the WebUI is not healthy." }
        $env:VITE_MATFLOW_API_URL = "http://127.0.0.1:$BackendPort/api"
        Start-Logged 'cmd.exe' "/c `"`"$npx`" vite --host 127.0.0.1 --port $FrontendPort`"" 'webui' (Join-Path $frontend 'apps/webui') | Out-Null
        Wait-Url "http://127.0.0.1:$FrontendPort" 'WebUI' 120
    }

    Write-Host ''
    Write-Host 'MatFlow live demo is up:' -ForegroundColor Green
    Write-Host "  WebUI      http://127.0.0.1:$FrontendPort"
    Write-Host "  API        http://127.0.0.1:$BackendPort/api"
    Write-Host "  API docs   http://127.0.0.1:$BackendPort/docs"
    Write-Host "  models     http://127.0.0.1:$SjtPort/v1 (SJTU) and http://127.0.0.1:$DeepSeekPort/v1 (DeepSeek official)"
    Write-Host ''
    Write-Host 'Next: open the WebUI and follow docs/acceptance/2026-10-20-live/OPERATOR_RUNBOOK.zhcn.md' -ForegroundColor Cyan
    Write-Host '      (import a dataset, build the EIS workflow, run it, review, continue).' -ForegroundColor Cyan

    if (-not $NoWait) {
        Write-Host ''
        Write-Host 'Press Ctrl+C to stop the processes this script started.' -ForegroundColor DarkGray
        while ($true) { Start-Sleep -Seconds 2 }
    }
} finally {
    Stop-Started
}
