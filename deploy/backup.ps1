# course-video-assistant deployment scripts (SYS)
# backup.ps1 - create a dated backup snapshot for release/rollback (M3/M4 deliverable).
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File deploy\backup.ps1 [-Keep 7]
#
# Contract notes (docs/03_技术方案与接口/03_环境配置与运行部署.md):
#   - the service MUST be stopped before backup (SQLite must be copied while stopped)
#   - copies: data (db/videos/trash), non-secret config sample, lock file, source code
#     (backend/modules/scripts/deploy), frontend build output (dist)
#   - NOT copied: .venv, node_modules, tools (rebuildable binaries), models (too big;
#     path and sha256 are recorded in MANIFEST.txt instead), .env.local (secrets stay local)

param(
    [int]$Keep = 7
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ---------- 1) refuse to back up a running service ----------
$appPort = 8000
if (Test-Path (Join-Path $root ".env.local")) {
    $portLine = (Select-String -Path ".env.local" -Pattern "^APP_PORT=(\d+)\s*$" -ErrorAction SilentlyContinue)
    if ($portLine) { $appPort = [int]$portLine.Matches[0].Groups[1].Value }
}
$busy = Get-NetTCPConnection -LocalPort $appPort -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    throw ("port {0} is listening: stop the service first (deploy\stop.ps1), then back up." -f $appPort)
}

# ---------- 2) destination ----------
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dest = Join-Path (Join-Path $root "backups") $stamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# ---------- 3) copy data ----------
New-Item -ItemType Directory -Force -Path (Join-Path $dest "data") | Out-Null
if (Test-Path (Join-Path $root "data\app.db")) {
    Copy-Item (Join-Path $root "data\app.db") (Join-Path $dest "data\app.db") -Force
} else {
    Write-Warning "missing, skipped: data\app.db"
}
foreach ($dir in @("videos", "trash")) {
    $src = Join-Path $root ("data\" + $dir)
    if (Test-Path $src) {
        robocopy $src (Join-Path $dest ("data\" + $dir)) /E /NFL /NDL /NJH /NJS | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $src (exit $LASTEXITCODE)" }
    } else {
        Write-Warning "missing, skipped: $src"
    }
}

# ---------- 4) copy code and build output ----------
foreach ($dir in @("backend", "modules", "scripts", "deploy")) {
    robocopy (Join-Path $root $dir) (Join-Path $dest $dir) /E /NFL /NDL /NJH /NJS /XD __pycache__ | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $dir (exit $LASTEXITCODE)" }
}
if (Test-Path (Join-Path $root "frontend\dist")) {
    robocopy (Join-Path $root "frontend\dist") (Join-Path $dest "frontend\dist") /E /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for frontend\dist (exit $LASTEXITCODE)" }
}
foreach ($file in @(".env.example", "requirements.lock.txt", "frontend\package.json", "frontend\package-lock.json")) {
    if (Test-Path (Join-Path $root $file)) {
        $target = Join-Path $dest $file
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item (Join-Path $root $file) $target -Force
    }
}

# ---------- 5) manifest with versions and hashes ----------
$py  = Join-Path $root ".venv\Scripts\python.exe"
$nodeExe = Join-Path $root "tools\node22\node.exe"
$manifest = New-Object System.Collections.Generic.List[string]
$manifest.Add("backuproot: $dest")
$manifest.Add("created_utc: " + (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
$manifest.Add("python: " + (& $py --version 2>&1))
try { $manifest.Add("node: " + (& $nodeExe --version)) } catch { $manifest.Add("node: not bundled") }
try { $manifest.Add("git: " + (git -C $root rev-parse HEAD 2>$null)) } catch { $manifest.Add("git: not a repository") }
foreach ($hashPath in @("data\app.db", "requirements.lock.txt", "models\faster-whisper-small\model.bin")) {
    $hashAbs = Join-Path $root $hashPath
    if (Test-Path $hashAbs) {
        $hash = (Get-FileHash -Path $hashAbs -Algorithm SHA256).Hash.ToLower()
        $manifest.Add("sha256 " + $hashPath + " : " + $hash)
    } else {
        $manifest.Add("sha256 " + $hashPath + " : MISSING")
    }
}
$manifest | Out-File -FilePath (Join-Path $dest "MANIFEST.txt") -Encoding utf8
Write-Host "manifest written."

# ---------- 6) rotation ----------
$all = Get-ChildItem (Join-Path $root "backups") -Directory | Sort-Object Name
if ($all.Count -gt $Keep) {
    $toDrop = $all | Select-Object -First ($all.Count - $Keep)
    foreach ($old in $toDrop) {
        Remove-Item $old.FullName -Recurse -Force
        Write-Host "rotated out old backup: $($old.Name)"
    }
}

Write-Host ("backup done -> " + $dest)
