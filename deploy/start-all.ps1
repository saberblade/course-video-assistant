# course-video-assistant deployment scripts (SYS)
# start-all.ps1 - start backend + vite dev server together, then open the browser.
#
# Usage (from repo root):
#   .\start.cmd
#   or: powershell -ExecutionPolicy Bypass -File deploy\start-all.ps1
#
# Contract notes:
#   - backend runs in its own console window (uvicorn, 1 worker, port from .env.local)
#   - vite dev server runs in its own console window on 5173, hot reload enabled
#   - a port that is already serving is left untouched instead of being killed
#   - readiness is verified against /api/health; a failure is reported, never faked

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
$envLocal = Join-Path $root ".env.local"
$distIndex = Join-Path $root "frontend\dist\index.html"

# ---------- 1) preconditions ----------
if (-not (Test-Path $py)) {
    throw "找不到虚拟环境：$py`n请先按 README 创建 .venv 并安装依赖。"
}
if (-not (Test-Path $envLocal)) {
    throw "找不到 .env.local`n请执行：Copy-Item .env.example .env.local ，再填入真实配置。"
}

# ---------- 2) port from config ----------
$appPort = 8000
Get-Content $envLocal -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -match "^APP_PORT=(\d+)\s*$") { $appPort = [int]$Matches[1] }
}
$webPort = 5173

function Test-PortBusy([int]$port) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
}

# ---------- 3) proxy env de-duplication ----------
# 本机同时存在 http_proxy/HTTP_PROXY 这类大小写重复的变量时，Windows PowerShell 5.1
# 的 Start-Process 复制环境变量会报「已添加项」。先按小写重建一份再启动。
foreach ($proxyName in 'http_proxy', 'https_proxy', 'no_proxy') {
    $proxyValue = [Environment]::GetEnvironmentVariable($proxyName, 'Process')
    if ($null -ne $proxyValue) {
        [Environment]::SetEnvironmentVariable($proxyName, $null, 'Process')
        [Environment]::SetEnvironmentVariable($proxyName, $proxyValue, 'Process')
    }
}

Write-Host ""
Write-Host "========== 课程视频复盘助手 ==========" -ForegroundColor Cyan
Write-Host "项目目录：$root`n"

# ---------- 4) backend ----------
if (Test-PortBusy $appPort) {
    Write-Host "[1/2] 后端已在 $appPort 运行，跳过启动。" -ForegroundColor Yellow
} else {
    $uvArgs = @("-X", "utf8", "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
                "--host", "127.0.0.1", "--port", "$appPort", "--workers", "1")
    Start-Process -FilePath $py -ArgumentList $uvArgs -WorkingDirectory $root | Out-Null
    Write-Host "[1/2] 后端启动中（新窗口）… 端口 $appPort" -ForegroundColor Green
}

# ---------- 5) frontend ----------
if (Test-PortBusy $webPort) {
    Write-Host "[2/2] 前端已在 $webPort 运行，跳过启动。" -ForegroundColor Yellow
} else {
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "npm.cmd --prefix frontend run dev" -WorkingDirectory $root | Out-Null
    Write-Host "[2/2] 前端启动中（新窗口）… 端口 $webPort" -ForegroundColor Green
}

# ---------- 6) wait for readiness ----------
Write-Host -NoNewline "`n等待后端就绪 "

$backendOk = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $wc = New-Object System.Net.WebClient
        $wc.Proxy = $null
        $body = $wc.DownloadString("http://127.0.0.1:$appPort/api/health")
        if ($body -match '"status"\s*:\s*"ok"') { $backendOk = $true; break }
    } catch {
        # 后端还在加载模型，继续等
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 1
}
Write-Host ""

$frontOk = $false
for ($i = 0; $i -lt 40; $i++) {
    if (Test-PortBusy $webPort) { $frontOk = $true; break }
    Start-Sleep -Milliseconds 500
}

# ---------- 7) summary ----------
Write-Host ""
if ($backendOk) {
    Write-Host "后端  就绪   http://127.0.0.1:$appPort/api/health" -ForegroundColor Green
} else {
    Write-Host "后端  60 秒内未就绪，请查看「后端」那个新窗口里的报错。" -ForegroundColor Red
}
if ($frontOk) {
    Write-Host "前端  就绪   http://127.0.0.1:$webPort/" -ForegroundColor Green
} else {
    Write-Host "前端  未就绪，请查看「前端」那个新窗口里的报错。" -ForegroundColor Red
}

if ($frontOk) {
    Start-Process "http://127.0.0.1:$webPort/" | Out-Null
    Write-Host "`n已在浏览器打开页面。"
}

if (-not (Test-Path $distIndex)) {
    Write-Host "`n提示：frontend\dist 不存在，8000 端口只有接口没有界面；" -ForegroundColor Yellow
    Write-Host "      要用单端口演示请先执行 npm.cmd --prefix frontend run build" -ForegroundColor Yellow
}

Write-Host "`n关闭：运行 .\stop.cmd ，或直接关掉新开的两个窗口。" -ForegroundColor Cyan
Write-Host ""

if (-not ($backendOk -and $frontOk)) { exit 1 }
