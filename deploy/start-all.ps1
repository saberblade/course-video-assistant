$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = if ($env:COURSE_PYTHON) { $env:COURSE_PYTHON } else { Join-Path $root '.venv\Scripts\python.exe' }
$ops = Join-Path $root 'scripts\operations.py'
$state = (& $py -X utf8 $ops state) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read runtime configuration.' }
if (Get-NetTCPConnection -LocalPort $state.port -State Listen -ErrorAction SilentlyContinue) {
    & $py -X utf8 $ops state --live | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Backend port belongs to another service.' }
} else {
    & (Join-Path $PSScriptRoot 'start.ps1') -NewConsole
}
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $vite)) { throw 'Run npm.cmd --prefix frontend ci first.' }
$existing = @(Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)
if ($existing) {
    foreach ($owner in @($existing | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $command = (Get-CimInstance Win32_Process -Filter "ProcessId=$owner").CommandLine
        if ($command -notmatch [regex]::Escape($vite)) { throw 'Port 5173 belongs to another checkout; left untouched.' }
    }
} else {
    $env:VITE_BACKEND_TARGET = "http://127.0.0.1:$($state.port)"
    $node = (Get-Command node.exe).Source
    Start-Process -FilePath $node -ArgumentList @(('"' + $vite + '"'), '--host', '127.0.0.1', '--port', '5173') -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden | Out-Null
}
Write-Host "Frontend: http://127.0.0.1:5173/  Backend: http://127.0.0.1:$($state.port)/"
Write-Host 'Backend health may return 503 until transcription warmup is complete.'
