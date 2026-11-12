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

# ---------- 忙状态检查：在途任务会变成 PROCESS_INTERRUPTED ----------
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not $Force -and (Test-Path $py)) {
    $probe = @'
import sqlite3, sys
from pathlib import Path
data = Path(sys.argv[1]) / "app.db"
if not data.is_file():
    print("none")
    raise SystemExit(0)
con = sqlite3.connect(data)
busy = con.execute("select count(*) from videos where status in ('queued','transcribing','indexing')").fetchone()[0]
rag = 0
try:
    rag = con.execute("select count(*) from rag_indexes where status in ('pending','building')").fetchone()[0]
except sqlite3.Error:
    rag = 0
print(f"{busy} {rag}")
'@
    $state = (& $py -c $probe $root) -join ""
    $parts = $state.Trim() -split "\s+"
    $busy = [int]$parts[0]
    $ragBusy = if ($parts.Count -gt 1) { [int]$parts[1] } else { 0 }
    if ($busy -gt 0 -or $ragBusy -gt 0) {
        Write-Warning ("still busy: {0} video task(s), {1} RAG index task(s)." -f $busy, $ragBusy)
        Write-Warning "stopping now will mark in-flight work as PROCESS_INTERRUPTED on next start. Use -Force to stop anyway."
        return
    }
}

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
