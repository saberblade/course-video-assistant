# course-video-assistant deployment scripts (SYS)
# start.ps1 - run the FastAPI service on the local presentation machine.
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File deploy\start.ps1              # foreground (Ctrl+C stops)
#   powershell -ExecutionPolicy Bypass -File deploy\start.ps1 -NewConsole  # separate console window
#
# Contract notes (docs/03_技术方案与接口/03_环境配置与运行部署.md):
#   - demo run uses 1 worker, no --reload, default port from .env.local
#   - .env.local is user-managed and never created or modified by this script
#   - errors are raised, not swallowed; the service is not faked as ready

param(
    [switch]$NewConsole
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ---------- 1) python venv ----------
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "venv not found: $py`nRun: py -3.11 -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt"
}

# ---------- 2) config file ----------
$envLocal = Join-Path $root ".env.local"
if (-not (Test-Path $envLocal)) {
    throw ".env.local not found.`nRun: Copy-Item .env.example .env.local then set your real values (keys stay out of git)."
}

# ---------- 3) port from config ----------
$appPort = 8000
Get-Content $envLocal -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match "^APP_PORT=(\d+)\s*$") { $appPort = [int]$Matches[1] }
}

# ---------- 4) tool/model presence ----------
$ffprobeDefault = "ffprobe"
$ffprobeConfigured = (Select-String -Path $envLocal -Pattern "^FFPROBE_BIN=(.+)$" -ErrorAction SilentlyContinue)
if (-not $ffprobeConfigured) {
    Write-Warning "FFPROBE_BIN not set in .env.local; backend expects ffprobe on PATH (tools\ffmpeg\ffprobe.exe works)."
}
$modelDir = Join-Path $root "models\faster-whisper-small"
$modelBin = Join-Path $modelDir "model.bin"
if (-not (Test-Path $modelBin)) {
    Write-Warning "model.bin not found under models\faster-whisper-small; first transcription task will fail with MODEL_NOT_FOUND."
}

# ---------- 5) dist hint ----------
$distIndex = Join-Path $root "frontend\dist\index.html"
if (-not (Test-Path $distIndex)) {
    Write-Warning "frontend/dist/index.html missing: the service will start but same-origin hosting is skipped."
}

# ---------- 5.5) database migration before serving ----------
# 旧库会被自动标记到基线再跑增量迁移，不删库、不重建。
Write-Host "migrate: alembic upgrade head"
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "alembic upgrade head failed (exit $LASTEXITCODE); service not started to avoid serving an old schema."
}
$revision = (& $py -m alembic current) -join " "
Write-Host "schema : $revision"

# ---------- 6) start ----------
Write-Host "python : $py"
Write-Host "config : $envLocal"
Write-Host "port   : $appPort (from APP_PORT)"
Write-Host "health : http://127.0.0.1:$appPort/api/health  (root UI: http://127.0.0.1:$appPort/)"
Write-Host "stop   : deploy\stop.ps1  (wait for empty queue first)"

$uvArgs = @("-X","utf8","-m","uvicorn","app.main:app","--app-dir","backend","--host","127.0.0.1","--port","$appPort","--workers","1")
if ($NewConsole) {
    # 本机同时存在 http_proxy/HTTP_PROXY 这类大小写重复的变量时，PowerShell 5.1 的
    # Start-Process 复制环境变量会报“已添加项”，先按小写重建一份再启动。
    foreach ($proxyName in 'http_proxy', 'https_proxy', 'no_proxy') {
        $proxyValue = [Environment]::GetEnvironmentVariable($proxyName, 'Process')
        if ($null -ne $proxyValue) {
            [Environment]::SetEnvironmentVariable($proxyName, $null, 'Process')
            [Environment]::SetEnvironmentVariable($proxyName, $proxyValue, 'Process')
        }
    }
    Start-Process -FilePath $py -ArgumentList $uvArgs -WorkingDirectory $root
    Write-Host "started in a new console window."
} else {
    & $py @uvArgs
}
