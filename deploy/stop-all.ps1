# course-video-assistant deployment scripts (SYS)
# stop-all.ps1 - stop both the backend service and the vite dev server.
#
# Usage (from repo root):
#   .\stop.cmd
#   or: powershell -ExecutionPolicy Bypass -File deploy\stop-all.ps1 [-Force]
#
# Contract notes:
#   - backend is matched by its exact uvicorn command line, never by image name,
#     so unrelated python.exe processes (anaconda etc.) are left alone
#   - frontend is matched by the process that owns port 5173 *and* whose command
#     line contains vite; anything else on that port is reported and skipped
#   - an in-flight transcription becomes PROCESS_INTERRUPTED, so the script refuses
#     to stop while the queue is busy unless -Force is given

param(
    [switch]$Force
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ---------- 0) queue guard ----------
$py = Join-Path $root ".venv\Scripts\python.exe"
$dbPath = Join-Path $root "data\app.db"
if ((Test-Path $py) -and (Test-Path $dbPath)) {
    $probe = @"
import sqlite3
c = sqlite3.connect('file:data/app.db?mode=ro', uri=True)
n = c.execute("select count(*) from videos where status in ('queued','transcribing','indexing')").fetchone()[0]
c.close()
print(n)
"@
    try {
        $unfinished = (& $py -c $probe 2>$null | Select-Object -Last 1)
        if ($null -ne $unfinished -and [int]$unfinished -gt 0) {
            if (-not $Force) {
                Write-Host ("队列里还有 {0} 个未完成任务，停止会让它们变成 PROCESS_INTERRUPTED。" -f $unfinished) -ForegroundColor Red
                Write-Host "等任务跑完再关；确实要强行关闭请加 -Force：" -ForegroundColor Red
                Write-Host "  powershell -ExecutionPolicy Bypass -File deploy\stop-all.ps1 -Force" -ForegroundColor Red
                exit 1
            }
            Write-Warning "队列里还有 $unfinished 个未完成任务，按 -Force 继续关闭。"
        }
    } catch {
        Write-Warning "无法读取任务队列，跳过检查。"
    }
}

Write-Host "`n========== 关闭课程视频复盘助手 ==========`n" -ForegroundColor Cyan

$stopped = 0

# ---------- 1) backend ----------
$targets = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match "uvicorn.{0,40}app\.main:app" -and $_.CommandLine -match "--app-dir.{0,10}backend" }

if ($targets) {
    foreach ($proc in $targets) {
        Write-Host ("停止后端 PID {0}" -f $proc.ProcessId)
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        $stopped++
    }
} else {
    Write-Host "后端：没有在运行。"
}

# ---------- 2) frontend ----------
$viteConns = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue
if ($viteConns) {
    foreach ($procId in ($viteConns.OwningProcess | Sort-Object -Unique)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -match "vite") {
            Write-Host ("停止前端 PID {0}" -f $procId)
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $stopped++
        } else {
            Write-Warning ("端口 5173 上的进程 PID {0} 不是 vite，跳过。" -f $procId)
        }
    }
} else {
    Write-Host "前端：没有在运行。"
}

# ---------- 3) verify ----------
Start-Sleep -Seconds 2

$portLine = @()
foreach ($p in 8000, 5173) {
    if (Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue) {
        $portLine += $p
    }
}

Write-Host ""
if ($portLine.Count -eq 0) {
    Write-Host ("端口已全部释放（共停止 {0} 个进程）。" -f $stopped) -ForegroundColor Green
} else {
    Write-Host ("以下端口仍在监听：{0}" -f ($portLine -join ", ")) -ForegroundColor Yellow
    Write-Host "可能不是本项目进程，请用 netstat -ano 确认后再处理。"
}
Write-Host ""