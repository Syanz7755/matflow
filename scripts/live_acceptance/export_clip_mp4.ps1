<#
.SYNOPSIS
  Export an MP4 beside every recorded demo GIF (and keep both formats in step).

.DESCRIPTION
  The recorder (recording-pr-demos / playdemo) produces GIF only. Some viewers and
  slide decks prefer H.264, so this script converts each accepted GIF to a sibling
  MP4 with the same basename. It never re-runs the UI: the MP4 is derived from the
  already verified recording, so the two files always show the same take.

  Walkthrough videos are recorded natively as 1440x900 webm and converted by
  record_demo_video.ps1; this script skips them.

.PARAMETER Dir
  Directories to scan for *.gif (defaults to the two acceptance clip folders).

.EXAMPLE
  pwsh -File scripts/live_acceptance/export_clip_mp4.ps1
  pwsh -File scripts/live_acceptance/export_clip_mp4.ps1 -Dir docs/acceptance/2026-10-20-live/defects/clips
#>
[CmdletBinding()]
param(
    [string[]]$Dir
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Dir) {
    $Dir = @(
        (Join-Path $repo 'docs/acceptance/2026-10-20-live/demo-tutorial/clips'),
        (Join-Path $repo 'docs/acceptance/2026-10-20-live/defects/clips')
    )
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw 'ffmpeg is not on PATH.' }

$total = 0
foreach ($folder in $Dir) {
    if (-not (Test-Path $folder)) { Write-Host "skip missing $folder" -ForegroundColor DarkGray; continue }
    foreach ($gif in Get-ChildItem $folder -Filter '*.gif' | Sort-Object Name) {
        $mp4 = [System.IO.Path]::ChangeExtension($gif.FullName, '.mp4')
        $stale = (-not (Test-Path $mp4)) -or ((Get-Item $mp4).LastWriteTime -lt $gif.LastWriteTime)
        if ($stale) {
            & ffmpeg -v error -y -i $gif.FullName -c:v libx264 -preset medium -crf 20 `
                -pix_fmt yuv420p -movflags +faststart -an $mp4
            if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed for $($gif.Name)" }
        }
        $probe = (ffprobe -v error -show_entries format=duration,size -of csv=p=0 $mp4) -split ','
        Write-Host ("  {0,-32} {1,5:N2}s {2,7:N0} KB  {3}" -f $gif.Name, [double]$probe[0], ([double]$probe[1] / 1KB), $(if ($stale) { 'converted' } else { 'up to date' })) -ForegroundColor DarkGray
        $total += 1
    }
}
Write-Host "mp4 beside every gif: $total file(s)" -ForegroundColor Green
