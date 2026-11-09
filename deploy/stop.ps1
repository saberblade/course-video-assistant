# course-video-assistant deployment scripts (SYS)
# stop.ps1 - stop the local uvicorn service started by deploy\start.ps1.
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File deploy\stop.ps1
#
# Contract notes:
#   - stop only the processes whose command line is this project's uvicorn line,
#     never terminate unrelated python.exe processes
#   - the caller should confirm the queue is empty (no transcribing/indexing task)
#     before stopping; in-flight work becomes PROCESS_INTERRUPTED on next start
#   - this script never edits database rows directly

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$targets = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match "uvicorn.{0,40}app\.main:app" -and $_.CommandLine -match "--app-dir.{0,10}backend" }

if (-not $targets) {
    Write-Host "no matching course-review uvicorn process found; nothing to stop."
    return
}

foreach ($proc in $targets) {
    Write-Host ("stopping PID {0}: {1}" -f $proc.ProcessId, $proc.CommandLine)
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
}

Start-Sleep -Seconds 2
$left = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match "uvicorn.{0,40}app\.main:app" }
if ($left) {
    Write-Warning "some processes still alive; rerun without -Force check or stop them manually:"
    $left | ForEach-Object { Write-Warning ("  PID {0}" -f $_.ProcessId) }
} else {
    Write-Host "all course-review uvicorn processes stopped."
}
