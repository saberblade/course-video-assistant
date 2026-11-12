param([switch]$Force)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot 'stop.ps1') -Force:$Force
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
$listeners = @(Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)
foreach ($owner in @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
    if ($process.CommandLine -match [regex]::Escape($vite)) {
        Stop-Process -Id $owner -Force
        Write-Host 'Stopped this checkout frontend.'
    } else {
        Write-Warning 'Unrelated service on port 5173 left untouched.'
    }
}
