#Requires -Version 7.0
<#
.SYNOPSIS
  One script to run MatFlow locally: start / stop / restart / status / logs.

.DESCRIPTION
  Starts the whole local stack and keeps it manageable:

    1. two LiteLLM gateways           127.0.0.1:4078 (SJTU catalogue) and :4080 (DeepSeek official)
    2. the MatFlow backend            127.0.0.1:8000
    3. the sibling WebUI dev server   127.0.0.1:5173

  Unlike a one-shot launcher this one is idempotent and re-runnable:
    - services that are already healthy are reused, not restarted
    - stale processes left on our ports by an earlier run are reclaimed, but ONLY when their
      command line is recognisably ours (uvicorn backend.main:app / vite / litellm);
      anything else on the port aborts with a clear message instead of being killed
    - every started process is written to .tmp/live/matflow-launcher.json so `stop` only
      stops what this script started
    - each service logs to .tmp/live/<name>.{out,err}.log; `logs` tails them
    - a start that fails a health check prints the failing log tail and rolls back

  Credentials are read from the Windows *User* environment scope into this process only and
  are never printed or written:
    SJTU_ZHIYUAN_API_KEY, LITELLM_DEFAULT_API_KEY, DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE

.PARAMETER Command
  start (default) | stop | restart | status | logs | open | help

.EXAMPLE
  pwsh -File scripts\matflow.ps1                     # start everything (idempotent)
  pwsh -File scripts\matflow.ps1 status              # ports, health, save, model
  pwsh -File scripts\matflow.ps1 restart             # stop what we started, start again
  pwsh -File scripts\matflow.ps1 logs -Tail 40       # tail every service log
  pwsh -File scripts\matflow.ps1 stop                # stop the stack

.EXAMPLE
  pwsh -File scripts\matflow.ps1 start -Save demo-2 -NoBrowser -InstallDeps
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs', 'open', 'help')]
    [string]$Command = 'start',

    [switch]$NoBrowser,
    [switch]$SkipWebUI,
    [switch]$SkipDeepSeek,
    [switch]$NoReclaim,
    [switch]$InstallDeps,
    [switch]$Detach,
    [string]$Save = 'live-demo',
    [string]$LlmConfig = 'config\llm-deepseek.json',
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$SjtPort = 4078,
    [int]$DeepSeekPort = 4080,
    [string]$Frontend,
    [int]$Tail = 30,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repo '.tmp/live'
$stateFile = Join-Path $logDir 'matflow-launcher.json'
if (-not $Frontend) { $Frontend = Join-Path (Split-Path -Parent $repo) 'matflow-frontend' }
$webuiDir = Join-Path $Frontend 'apps/webui'
$python = Join-Path $repo '.venv\Scripts\python.exe'
$script:started = @()

function Step([string]$text) { Write-Host "· $text" -ForegroundColor Cyan }
function Ok([string]$text) { Write-Host "  $text" -ForegroundColor Green }
function Note([string]$text) { Write-Host "  $text" -ForegroundColor DarkGray }
function Warn([string]$text) { Write-Host "  $text" -ForegroundColor Yellow }
function Die([string]$text) { Write-Host "x $text" -ForegroundColor Red; exit 1 }

function Test-Port([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Get-PortPid([int]$port) {
    $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $connection) { return $null }
    return [int]$connection.OwningProcess
}

function Get-ProcessCommandLine([int]$processId) {
    try { return (Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction Stop).CommandLine } catch { return $null }
}

function Test-Health([string]$url, [int]$seconds = 3) {
    try {
        $response = Invoke-WebRequest -Uri $url -TimeoutSec $seconds -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Wait-Health([string]$url, [string]$label, [int]$seconds = $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Health $url 2) { Ok "$label ready: $url"; return $true }
        Start-Sleep -Milliseconds 700
    }
    Warn "$label did not answer $url within ${seconds}s"
    return $false
}

function Import-UserSecret([string]$name) {
    if ([Environment]::GetEnvironmentVariable($name)) { return $true }
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    if (-not $value) { return $false }
    [Environment]::SetEnvironmentVariable($name, $value)
    return $true
}

function Read-State {
    if (-not (Test-Path $stateFile)) { return @() }
    try {
        $raw = Get-Content $stateFile -Raw | ConvertFrom-Json
        if (-not $raw) { return @() }
        return @($raw)
    } catch { return @() }
}

function Write-State([array]$entries) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    if (-not $entries -or $entries.Count -eq 0) { Remove-Item $stateFile -Force -ErrorAction SilentlyContinue; return }
    $entries | ConvertTo-Json -Depth 4 | Set-Content $stateFile -Encoding utf8
}

function Stop-Tree([int]$processId) {
    if (-not $processId) { return }
    try { & taskkill /PID $processId /T /F 2>&1 | Out-Null } catch { }
}

function Start-Logged([string]$file, [string]$arguments, [string]$label, [string]$workingDirectory, [hashtable]$extraEnv = @{}) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $out = Join-Path $logDir "$label.out.log"
    $err = Join-Path $logDir "$label.err.log"
    Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
    $environment = @{}
    foreach ($key in $extraEnv.Keys) { $environment[$key] = $extraEnv[$key] }
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $workingDirectory `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -Environment $environment
    $script:started += [pscustomobject]@{ label = $label; pid = $process.Id; out = $out; err = $err }
    Note "started $label (pid $($process.Id))"
    return $process
}

function Update-StartedPid([string]$label, [int]$port) {
    # venv python and npm spawn child processes; record the real listener so status and stop are accurate
    for ($i = 0; $i -lt 20; $i++) {
        $listener = Get-PortPid $port
        if ($listener) {
            foreach ($entry in $script:started) { if ($entry.label -eq $label) { $entry.pid = $listener } }
            return
        }
        Start-Sleep -Milliseconds 250
    }
}
function Reclaim-Port([int]$port, [string]$label, [string[]]$patterns) {
    if (-not (Test-Port $port)) { return }
    $processId = Get-PortPid $port
    $commandLine = Get-ProcessCommandLine $processId
    $owned = $false
    foreach ($pattern in $patterns) { if ($commandLine -and $commandLine -like $pattern) { $owned = $true } }
    if (-not $owned) {
        Die "port $port ($label) is held by pid $processId that does not look like MatFlow:`n    $commandLine`n  Stop it yourself, or pick another port with -${label}Port."
    }
    if ($NoReclaim) { Die "port $port ($label) is held by a stale MatFlow process (pid $processId). Re-run without -NoReclaim to replace it." }
    Warn "reclaiming port $port ($label) from stale pid $processId"
    Stop-Tree $processId
    for ($i = 0; $i -lt 20; $i++) { if (-not (Test-Port $port)) { return }; Start-Sleep -Milliseconds 250 }
    Die "port $port ($label) is still busy after killing pid $processId"
}

function Show-LogTail([string]$label) {
    foreach ($suffix in 'err', 'out') {
        $path = Join-Path $logDir "$label.$suffix.log"
        if ((Test-Path $path) -and (Get-Item $path).Length -gt 0) {
            Write-Host "  --- $label.$suffix.log (tail) ---" -ForegroundColor DarkYellow
            Get-Content $path -Tail 12 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
        }
    }
}

function Assert-Prerequisites {
    Step 'checking prerequisites'
    foreach ($tool in 'uv', 'node', 'npm') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Die "$tool was not found on PATH." }
    }
    if (-not (Test-Path (Join-Path $repo 'config/litellm.yaml'))) { Die 'config/litellm.yaml is missing (SJTU gateway config).' }
    if (-not $SkipDeepSeek -and -not (Test-Path (Join-Path $repo 'config/litellm-deepseek.yaml'))) { Die 'config/litellm-deepseek.yaml is missing (DeepSeek gateway config).' }
    if (-not (Test-Path (Join-Path $repo $LlmConfig))) { Die "agent config $LlmConfig is missing (the backend needs it to route)." }
    if (-not (Test-Path $python)) {
        if (-not $InstallDeps) { Die "backend virtualenv missing at $python. Run 'uv sync' first, or re-run with -InstallDeps." }
        Step 'creating the backend virtualenv (uv sync)'
        Push-Location $repo
        try { & uv sync; if ($LASTEXITCODE -ne 0) { Die 'uv sync failed' } } finally { Pop-Location }
    }
    if (-not $SkipWebUI) {
        if (-not (Test-Path (Join-Path $Frontend 'package.json'))) { Die "frontend checkout missing at $Frontend (expected a sibling matflow-frontend)." }
        if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
            if (-not $InstallDeps) { Die "frontend dependencies missing ($Frontend\node_modules). Run 'npm install' there, or re-run with -InstallDeps." }
            Step 'installing frontend dependencies (npm install)'
            Push-Location $Frontend
            try { & npm install; if ($LASTEXITCODE -ne 0) { Die 'npm install failed' } } finally { Pop-Location }
        }
    }
    $haveSjt = Import-UserSecret 'SJTU_ZHIYUAN_API_KEY'
    $haveCaller = Import-UserSecret 'LITELLM_DEFAULT_API_KEY'
    $haveDeepSeek = Import-UserSecret 'DEEPSEEK_API_KEY_MATFLOW_EXCLUSIVE'
    if (-not $haveSjt) { Die 'SJTU_ZHIYUAN_API_KEY is not set in the Windows User environment scope.' }
    if (-not $haveCaller) { Die 'LITELLM_DEFAULT_API_KEY is not set in the Windows User environment scope.' }
    Ok ("credentials: SJTU yes | caller yes | DeepSeek exclusive {0}" -f $(if ($haveDeepSeek) { 'yes' } else { 'no (gateway 4080 will be skipped)' }))
    return $haveDeepSeek
}

function Start-Stack {
    $haveDeepSeek = Assert-Prerequisites
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    Step 'SJTU model gateway (4078)'
    if (Test-Health "http://127.0.0.1:$SjtPort/health/readiness") {
        Ok "already healthy on $SjtPort (reused)"
    } else {
        Reclaim-Port $SjtPort 'Sjt' @('*litellm*')
        Start-Logged 'uv' "run litellm --config config/litellm.yaml --host 127.0.0.1 --port $SjtPort" 'sjt-gateway' $repo | Out-Null
        if (-not (Wait-Health "http://127.0.0.1:$SjtPort/health/readiness" 'SJTU gateway' 180)) { Show-LogTail 'sjt-gateway'; throw 'SJTU gateway failed to start' }
        Update-StartedPid 'sjt-gateway' $SjtPort
    }

    Step 'DeepSeek official gateway (4080)'
    if ($SkipDeepSeek -or -not $haveDeepSeek) {
        Note 'skipped (no exclusive key or -SkipDeepSeek)'
    } elseif (Test-Health "http://127.0.0.1:$DeepSeekPort/health/readiness") {
        Ok "already healthy on $DeepSeekPort (reused)"
    } else {
        Reclaim-Port $DeepSeekPort 'DeepSeek' @('*litellm*')
        Start-Logged 'uv' "run litellm --config config/litellm-deepseek.yaml --host 127.0.0.1 --port $DeepSeekPort" 'deepseek-gateway' $repo | Out-Null
        if (-not (Wait-Health "http://127.0.0.1:$DeepSeekPort/health/readiness" 'DeepSeek gateway' 180)) { Show-LogTail 'deepseek-gateway'; throw 'DeepSeek gateway failed to start' }
        Update-StartedPid 'deepseek-gateway' $DeepSeekPort
    }

    Step "MatFlow backend ($BackendPort)"
    if (Test-Health "http://127.0.0.1:$BackendPort/api/capabilities") {
        Ok "already healthy on $BackendPort (reused)"
    } else {
        Reclaim-Port $BackendPort 'Backend' @('*uvicorn*backend.main:app*', '*backend.main:app*')
        $env:MATFLOW_CORS_ORIGINS = "http://127.0.0.1:$FrontendPort"
        $env:MATFLOW_SAVE = $Save
        $env:MATFLOW_LLM_CONFIG = $LlmConfig
        Start-Logged $python "-m uvicorn backend.main:app --host 127.0.0.1 --port $BackendPort" 'backend' $repo @{
            MATFLOW_CORS_ORIGINS = $env:MATFLOW_CORS_ORIGINS
            MATFLOW_SAVE = $Save
            MATFLOW_LLM_CONFIG = $LlmConfig
        } | Out-Null
        if (-not (Wait-Health "http://127.0.0.1:$BackendPort/api/capabilities" 'backend')) { Show-LogTail 'backend'; throw 'backend failed to start' }
        Update-StartedPid 'backend' $BackendPort
    }

    if (-not $SkipWebUI) {
        Step "WebUI dev server ($FrontendPort)"
        if (Test-Health "http://127.0.0.1:$FrontendPort/") {
            Ok "already healthy on $FrontendPort (reused)"
        } else {
            Reclaim-Port $FrontendPort 'Frontend' @('*vite*', '*npm*run*dev*', '*npm-cli.js*dev*')
            $api = "http://127.0.0.1:$BackendPort/api"
            $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
            if (-not $npmCmd) { $npmCmd = (Get-Command npm -ErrorAction SilentlyContinue).Source }
            if (-not $npmCmd) { Die 'npm was not found on PATH.' }
            Start-Logged $npmCmd "run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort" 'webui' $webuiDir @{
                VITE_MATFLOW_API_URL = $api
            } | Out-Null
            if (-not (Wait-Health "http://127.0.0.1:$FrontendPort/" 'WebUI')) { Show-LogTail 'webui'; throw 'WebUI failed to start' }
            Update-StartedPid 'webui' $FrontendPort
        }
    }

    # State always reflects the real listeners, so a service that was reused keeps an accurate pid.
    $metaFile = Join-Path $logDir 'matflow-launcher.meta.json'
    [ordered]@{ started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); save = $Save; llm_config = $LlmConfig; backend_port = $BackendPort; frontend_port = $FrontendPort } | ConvertTo-Json | Set-Content $metaFile -Encoding utf8
    $entries = @()
    foreach ($pair in @(@('sjt-gateway', $SjtPort), @('deepseek-gateway', $DeepSeekPort), @('backend', $BackendPort), @('webui', $FrontendPort))) {
        $listener = Get-PortPid $pair[1]
        if ($listener) {
            $entries += [pscustomobject]@{
                label = $pair[0]
                pid   = $listener
                out   = (Join-Path $logDir "$($pair[0]).out.log")
                err   = (Join-Path $logDir "$($pair[0]).err.log")
            }
        }
    }
    Write-State $entries

    Step 'ready'
    Ok "WebUI   http://127.0.0.1:$FrontendPort"
    Ok "API     http://127.0.0.1:$BackendPort/api     docs: http://127.0.0.1:$BackendPort/docs"
    if (-not $SkipDeepSeek -and $haveDeepSeek) { Ok "models  DeepSeek official gateway :$DeepSeekPort, SJTU catalogue :$SjtPort" } else { Ok "models  SJTU catalogue :$SjtPort" }
    Note "save='$Save'  llm config='$LlmConfig'  state='$stateFile'"
    Note "stop with: pwsh -File scripts\matflow.ps1 stop"
    if (-not $NoBrowser -and -not $SkipWebUI) {
        Start-Process "http://127.0.0.1:$FrontendPort" | Out-Null
        Note 'browser opened'
    }
}

function Stop-Stack {
    $state = Read-State
    if (-not $state.Count) {
        Step 'no launcher state; freeing any MatFlow-looking processes on the known ports'
    } else {
        foreach ($entry in $state) {
            Step "stopping $($entry.label) (pid $($entry.pid))"
            Stop-Tree ([int]$entry.pid)
            $script:started = @()
        }
    }
    foreach ($port in @($SjtPort, $DeepSeekPort, $BackendPort, $FrontendPort)) {
        if (-not (Test-Port $port)) { continue }
        $processId = Get-PortPid $port
        $commandLine = Get-ProcessCommandLine $processId
        if ($commandLine -and ($commandLine -like '*uvicorn*backend.main*' -or $commandLine -like '*vite*' -or $commandLine -like '*litellm*')) {
            Warn "freeing remaining $port (pid $processId)"
            Stop-Tree $processId
        } else {
            Warn "port $port is still held by an unrelated process (pid $processId); leaving it alone"
        }
    }
    Write-State @()
    Start-Sleep -Milliseconds 500
    $left = @($SjtPort, $DeepSeekPort, $BackendPort, $FrontendPort | Where-Object { Test-Port $_ })
    if ($left.Count) { Die "still listening: $($left -join ', ')" }
    Ok 'stack stopped'
}

function Show-Status {
    Step 'MatFlow local stack'
    $rows = @(
        @{ label = 'SJTU gateway'; port = $SjtPort; url = "http://127.0.0.1:$SjtPort/health/readiness" },
        @{ label = 'DeepSeek gateway'; port = $DeepSeekPort; url = "http://127.0.0.1:$DeepSeekPort/health/readiness" },
        @{ label = 'backend'; port = $BackendPort; url = "http://127.0.0.1:$BackendPort/api/capabilities" },
        @{ label = 'WebUI'; port = $FrontendPort; url = "http://127.0.0.1:$FrontendPort/" }
    )
    $healthy = 0
    foreach ($row in $rows) {
        $listening = Test-Port $row.port
        $alive = $listening -and (Test-Health $row.url)
        if ($alive) { $healthy += 1 }
        $processId = if ($listening) { Get-PortPid $row.port } else { $null }
        $mark = if ($alive) { 'UP  ' } elseif ($listening) { 'PORT' } else { 'DOWN' }
        Write-Host ("  [{0}] {1,-18} :{2,-5} pid={3,-7} {4}" -f $mark, $row.label, $row.port, $processId, $row.url)
    }
    $state = Read-State
    if ($state.Count) { Note "launcher-started: $(($state | ForEach-Object { "$($_.label):$($_.pid)" }) -join ', ')" } else { Note 'launcher has no recorded processes (services may be reused or started elsewhere)' }
    $metaFile = Join-Path $logDir 'matflow-launcher.meta.json'
    if (Test-Path $metaFile) { try { $meta = Get-Content $metaFile -Raw | ConvertFrom-Json; Note "launcher meta: save='$($meta.save)' llm='$($meta.llm_config)' started=$($meta.started_at)" } catch { } }
    if (Test-Health "http://127.0.0.1:$BackendPort/api/capabilities") {
        try {
            $settings = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/settings" -TimeoutSec 5
            $agent = $settings.agent
            Ok "model=$($agent.model)  base_url=$($agent.base_url)  temperature=$($agent.temperature)"
        } catch { Warn 'could not read /api/settings' }
        try {
            $state2 = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/state" -TimeoutSec 5
            $graph = $state2.state
            Note "workspace: graph v$($graph.version), $($graph.nodes.Count) nodes, $($graph.edges.Count) edges"
        } catch { }
    }
    if ($healthy -eq $rows.Count -or ($SkipWebUI -and $healthy -eq ($rows.Count - 1))) { Write-Host '  all required services healthy' -ForegroundColor Green; return 0 }
    Write-Host '  not everything is up; run: pwsh -File scripts\matflow.ps1 start' -ForegroundColor Yellow
    return 1
}

function Show-Logs {
    foreach ($name in 'sjt-gateway', 'deepseek-gateway', 'backend', 'webui') {
        $path = Join-Path $logDir "$name.out.log"
        if (-not (Test-Path $path)) { continue }
        Write-Host "=== $name (last $Tail lines) ===" -ForegroundColor Cyan
        Get-Content $path -Tail $Tail | ForEach-Object { Write-Host $_ }
        $err = Join-Path $logDir "$name.err.log"
        if ((Test-Path $err) -and (Get-Item $err).Length -gt 0) {
            Write-Host "--- $name.err.log (last 8) ---" -ForegroundColor DarkYellow
            Get-Content $err -Tail 8 | ForEach-Object { Write-Host $_ -ForegroundColor DarkYellow }
        }
    }
}

function Invoke-Detached([string]$launchCommand) {
    # Start a detached copy of this script so the caller's console/pipe is not held open by the
    # long-lived service processes. Used when `start` is driven from a script or CI step.
    $arguments = @(
        '-NoProfile', '-File', $PSCommandPath, $launchCommand,
        '-BackendPort', "$BackendPort", '-FrontendPort', "$FrontendPort",
        '-SjtPort', "$SjtPort", '-DeepSeekPort', "$DeepSeekPort",
        '-Save', $Save, '-LlmConfig', $LlmConfig, '-TimeoutSeconds', "$TimeoutSeconds"
    )
    foreach ($flag in 'NoBrowser', 'SkipWebUI', 'SkipDeepSeek', 'NoReclaim', 'InstallDeps') {
        if ((Get-Variable $flag -ValueOnly)) { $arguments += "-$flag" }
    }
    if ($Frontend) { $arguments += @('-Frontend', $Frontend) }
    $quoted = ($arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
    $env:MATFLOW_LAUNCHER_DETACHED = '1'
    Start-Process -FilePath 'cmd.exe' -ArgumentList "/c start `"`" /min pwsh $quoted" -WindowStyle Hidden | Out-Null
    Write-Host "  detached launcher started (it keeps running after this command returns)" -ForegroundColor Green
    Write-Host "  follow it with: pwsh -File scripts\matflow.ps1 status   |   logs: pwsh -File scripts\matflow.ps1 logs" -ForegroundColor DarkGray
}
try {
    switch ($Command) {
        'help' {
            Get-Help $PSCommandPath -Detailed
        }
        'start' { if ($Detach -and -not $env:MATFLOW_LAUNCHER_DETACHED) { Invoke-Detached 'start' } else { Start-Stack } }
        'stop' { Stop-Stack }
        'restart' { if ($Detach -and -not $env:MATFLOW_LAUNCHER_DETACHED) { Invoke-Detached 'restart' } else { Stop-Stack; Start-Stack } }
        'status' { exit (Show-Status) }
        'logs' { Show-Logs }
        'open' {
            if (-not (Test-Health "http://127.0.0.1:$FrontendPort/")) { Die "WebUI is not up on $FrontendPort; run start first." }
            Start-Process "http://127.0.0.1:$FrontendPort" | Out-Null
            Ok "opened http://127.0.0.1:$FrontendPort"
        }
    }
} catch {
    Warn "failed: $($_.Exception.Message)"
    if ($script:started.Count) {
        Step 'rolling back the processes this run started'
        foreach ($entry in $script:started) { Stop-Tree ([int]$entry.pid) }
        Write-State @()
    }
    exit 1
}
