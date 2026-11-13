param([ValidateRange(1, 10000)][int]$Keep = 7)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = if ($env:COURSE_PYTHON) { $env:COURSE_PYTHON } else { Join-Path $root '.venv\Scripts\python.exe' }
& $py -X utf8 (Join-Path $root 'scripts\operations.py') backup --keep $Keep
if ($LASTEXITCODE -ne 0) { throw 'Backup failed; see the diagnostic above.' }
