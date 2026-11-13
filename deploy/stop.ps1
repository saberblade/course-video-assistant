param([switch]$Force)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = if ($env:COURSE_PYTHON) { $env:COURSE_PYTHON } else { Join-Path $root '.venv\Scripts\python.exe' }
$ops = Join-Path $root 'scripts\operations.py'
$state = (& $py -X utf8 $ops state) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read runtime configuration; nothing stopped.' }
$listeners = @(Get-NetTCPConnection -LocalPort $state.port -State Listen -ErrorAction SilentlyContinue)
if (-not $listeners) { Write-Host 'Service is already stopped.'; return }
$owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($owners.Count -ne 1) { throw 'Ambiguous port ownership; nothing stopped.' }
$target = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])"
$backend = [regex]::Escape((Join-Path $root 'backend'))
if ($target.CommandLine -notmatch 'uvicorn' -or $target.CommandLine -notmatch 'app\.main:app' -or $target.CommandLine -notmatch $backend) {
    throw 'Port belongs to a different command or checkout; nothing stopped.'
}
try {
    & $py -X utf8 $ops drain | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot drain new writes; nothing stopped.' }
    $live = (& $py -X utf8 $ops state --live) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify the live service identity; nothing stopped.' }
    if (-not $Force -and ($live.video_busy -gt 0 -or $live.rag_busy -gt 0 -or $live.question_busy -or $live.assistant_busy)) {
        throw 'Video, RAG or question work is still running. Wait before stopping; use -Force only to interrupt it deliberately.'
    }
    # Restrict cleanup to the verified server and its existing descendants.
    $all = @(Get-CimInstance Win32_Process)
    $descendants = New-Object System.Collections.Generic.List[int]
    $pending = New-Object System.Collections.Generic.Queue[int]
    $pending.Enqueue([int]$target.ProcessId)
    while ($pending.Count -gt 0) {
        $parentId = $pending.Dequeue()
        foreach ($child in @($all | Where-Object { $_.ParentProcessId -eq $parentId })) {
            if (-not $descendants.Contains([int]$child.ProcessId)) {
                $descendants.Add([int]$child.ProcessId)
                $pending.Enqueue([int]$child.ProcessId)
            }
        }
    }
    for ($index = $descendants.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $descendants[$index] -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
    Write-Host "Stopped this checkout on port $($state.port)."
} finally {
    & $py -X utf8 $ops undrain | Out-Null
}
