param([Parameter(Mandatory = $true)][string]$BackupPath)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = if ($env:COURSE_PYTHON) { $env:COURSE_PYTHON } else { Join-Path $root '.venv\Scripts\python.exe' }
& $py -X utf8 (Join-Path $root 'scripts\operations.py') restore $BackupPath
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; original data were retained or rolled back.' }
