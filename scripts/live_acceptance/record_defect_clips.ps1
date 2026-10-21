<#
.SYNOPSIS
  Re-record the demo-table / known-defect clips (2026-10-20 acceptance).

.DESCRIPTION
  Drives the recording-pr-demos recorder (playdemo) against the REAL demo stack
  (backend :8000, WebUI :5173, real LLM routing). Each clip is one Playwright test
  that acts for 3-8 s in real time (no playback speed-up) with a burned-in Chinese
  caption; defect clips use an amber caption.

  Prerequisites: scripts/start_demo.ps1 is running (empty workspace), ffmpeg on PATH,
  and <frontend>/demos/{playdemo.mjs,matflow-defects.demo.spec.mjs}.

.PARAMETER Only
  Record a single clip by its test name, e.g. -Only defect2-type-gate.

.EXAMPLE
  pwsh -File scripts/live_acceptance/record_defect_clips.ps1
  pwsh -File scripts/live_acceptance/record_defect_clips.ps1 -Only demo1-gate
#>
[CmdletBinding()]
param(
    [string]$Only,
    [string]$Frontend,
    [string]$OutDir
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Frontend) { $Frontend = Join-Path (Split-Path -Parent $repo) 'matflow-frontend' }
if (-not $OutDir) { $OutDir = Join-Path $repo 'docs/acceptance/2026-10-20-live/defects/clips' }

$spec = Join-Path $Frontend 'demos/matflow-defects.demo.spec.mjs'
$recorder = Join-Path $Frontend 'demos/playdemo.mjs'
foreach ($required in @($spec, $recorder)) {
    if (-not (Test-Path $required)) { throw "missing: $required" }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw 'ffmpeg is not on PATH.' }
if (-not (Test-Path (Join-Path $Frontend 'node_modules/@playwright/test/package.json'))) {
    throw "run npm install in $Frontend first"
}
try {
    $health = (Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -TimeoutSec 5 -UseBasicParsing).StatusCode
    if ($health -ne 200) { throw "WebUI answered $health" }
} catch {
    throw 'the demo stack is not up; run scripts/start_demo.ps1 first (WebUI on 127.0.0.1:5173).'
}

$clips = @(
    'demo1-build-nyquist',
    'demo1-gate',
    'demo1-continue-nyquist',
    'demo2-qe-replay',
    'demo2-qe-values',
    'demo3-route',
    'demo3-capability-gap',
    'defect1-skip-review',
    'defect2-type-gate',
    'defect3-compound'
)
if ($Only) {
    if ($clips -notcontains $Only) { throw "unknown clip '$Only'. Known: $($clips -join ', ')" }
    $clips = @($Only)
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Push-Location $Frontend
try {
    foreach ($clip in $clips) {
        $target = Join-Path $OutDir "$clip.gif"
        Write-Host "· recording $clip" -ForegroundColor Cyan
        $log = node $recorder record $spec --test $clip --out $target --width 960 --fps 20 --max-seconds 8 2>&1
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $target)) {
            $log | Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
            throw "recording failed for $clip"
        }
        $probe = (ffprobe -v error -show_entries format=duration,size -of csv=p=0 $target) -split ','
        Write-Host ("  {0}  {1:N2}s  {2:N0} KB" -f $clip, [double]$probe[0], ([double]$probe[1] / 1KB)) -ForegroundColor DarkGray
    }
} finally {
    Pop-Location
}
Write-Host "done: $($clips.Count) clip(s) in $OutDir" -ForegroundColor Green
