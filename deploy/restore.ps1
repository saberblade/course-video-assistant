# course-video-assistant deployment scripts (SYS)
# restore.ps1 - restore the data snapshot and build output made by deploy\backup.ps1.
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File deploy\restore.ps1 backups\<yyyyMMdd_HHmmss>
#
# Contract notes:
#   - stop the current service before restoring (script refuses while port is listening)
#   - this script restores data + frontend/dist only; source code stays with the repo
#   - .env.local (secrets) is never touched: it stays on this machine
#   - after restore, run health and the e2e smoke script; QA records the check

param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ---------- 1) validate backup directory ----------
$backupPath = Join-Path $root $BackupPath
if (-not (Test-Path $backupPath)) {
    throw "backup directory not found: $backupPath"
}
$manifest = Join-Path $backupPath "MANIFEST.txt"
if (-not (Test-Path $manifest)) {
    throw "MANIFEST.txt missing in $backupPath; refuse to restore an untracked snapshot."
}

# ---------- 2) refuse to restore a running service ----------
$appPort = 8000
if (Test-Path (Join-Path $root ".env.local")) {
    $portLine = (Select-String -Path ".env.local" -Pattern "^APP_PORT=(\d+)\s*$" -ErrorAction SilentlyContinue)
    if ($portLine) { $appPort = [int]$portLine.Matches[0].Groups[1].Value }
}
$busy = Get-NetTCPConnection -LocalPort $appPort -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    throw ("port {0} is listening: stop the service first (deploy\stop.ps1)." -f $appPort)
}

# ---------- 3) keep a safety copy of current app.db ----------
$curDb = Join-Path $root "data\app.db"
if (Test-Path $curDb) {
    $pre = Join-Path $root ("backups\pre_restore_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    New-Item -ItemType Directory -Force -Path $pre | Out-Null
    Copy-Item $curDb $pre -Force
    Write-Host ("current app.db saved to " + $pre + " (keep it for failure analysis)")
}

# ---------- 4) restore data directories ----------
$srcData = Join-Path $backupPath "data"
if (Test-Path $srcData) {
    robocopy $srcData (Join-Path $root "data") /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for data (exit $LASTEXITCODE)" }
}

# ---------- 5) restore frontend build output ----------
$srcDist = Join-Path $backupPath "frontend\dist"
if (Test-Path $srcDist) {
    robocopy $srcDist (Join-Path $root "frontend\dist") /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for frontend\dist (exit $LASTEXITCODE)" }
}

Write-Host "restored data and frontend/dist from $BackupPath"
Write-Host "next steps per contract 03:"
Write-Host "  1) deploy\start.ps1"
Write-Host "  2) check GET /api/health and open http://127.0.0.1:8000/"
Write-Host "  3) .venv\Scripts\python.exe -X utf8 scripts\e2e_smoke.py   (full pipeline check)"
Write-Host "  4) QA records the version and evidence; PM decides whether to accept"
