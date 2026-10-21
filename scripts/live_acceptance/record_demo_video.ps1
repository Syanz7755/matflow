<#
.SYNOPSIS
  Record the MatFlow WebUI walkthrough video (mp4) against the real demo stack.

.DESCRIPTION
  Uses the sibling frontend checkout's Playwright (video capture at 1440x900, 25 fps),
  drives one continuous walkthrough of the demo script — import, build, connect, bind,
  review+save, run, human review, result, edge edit, QE archive replay, Chinese routing,
  narrow viewport — with burned-in chapter captions, a title card and a painted pointer.
  Nothing is sped up: the pacing is the real interaction on the real backend.

  Then converts video.webm to H.264 mp4 (faststart) and reports duration/size.

.PARAMETER Frontend
  Path to the matflow-frontend checkout (defaults to the sibling directory).

.EXAMPLE
  pwsh -File scripts/live_acceptance/record_demo_video.ps1
#>
[CmdletBinding()]
param(
    [string]$Frontend,
    [string]$OutFile
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Frontend) { $Frontend = Join-Path (Split-Path -Parent $repo) 'matflow-frontend' }
if (-not $OutFile) { $OutFile = Join-Path $repo 'docs/acceptance/2026-10-20-live/demo-tutorial/video/matflow-walkthrough.mp4' }

$spec = Join-Path $Frontend 'demos/matflow-walkthrough.demo.spec.mjs'
$config = Join-Path $Frontend 'demos/walkthrough.config.mjs'
foreach ($required in @($spec, $config)) {
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

$outDir = Join-Path $Frontend 'demos/.demo-video/out'
if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force }

Push-Location $Frontend
try {
    Write-Host '· recording the walkthrough (about 40 s of screen time)' -ForegroundColor Cyan
    & npx.cmd playwright test --config $config --grep 'MatFlow WebUI walkthrough'
    if ($LASTEXITCODE -ne 0) { throw 'the walkthrough spec failed; see the Playwright output above' }
} finally {
    Pop-Location
}

$webm = Get-ChildItem $outDir -Recurse -Filter 'video.webm' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $webm) { throw "no video.webm under $outDir" }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null
Write-Host '· encoding mp4' -ForegroundColor Cyan
& ffmpeg -v error -y -i $webm.FullName -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -movflags +faststart -an $OutFile
if ($LASTEXITCODE -ne 0) { throw 'ffmpeg failed' }

$probe = (ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -show_entries format=duration,size -of default=noprint_wrappers=1 $OutFile) -join ' '
Write-Host ''
Write-Host "video: $OutFile" -ForegroundColor Green
Write-Host "  $probe"
