# course-review M1 environment check script (SYS)
# Usage (from course-review root): powershell -ExecutionPolicy Bypass -File scripts\env_check.ps1
# Output: console + logs\env_check_latest.txt

$ErrorActionPreference = "Continue"
$lines = @()

function Add-Line($text) { $script:lines += $text; Write-Host $text }

Add-Line "===== course-review environment check ====="
Add-Line ("time: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"))

# Python (venv first)
if (Test-Path ".\.venv\Scripts\python.exe") {
    Add-Line ("python(venv): " + (& .\.venv\Scripts\python.exe --version 2>&1))
} else {
    Add-Line "python(venv): NOT FOUND (.venv missing)"
}

# Node (portable Node 22 bundled with project)
if (Test-Path ".\tools\node22\node.exe") {
    Add-Line ("node22(portable): " + (& .\tools\node22\node.exe --version) + "   npm: " + (& .\tools\node22\npm.cmd --version))
} else {
    Add-Line "node22(portable): NOT FOUND tools\node22"
}

# FFmpeg
$ffmpeg = $null
if (Test-Path ".\tools\ffmpeg\ffmpeg.exe") { $ffmpeg = ".\tools\ffmpeg\ffmpeg.exe" }
elseif (Test-Path ".\tools\ffmpeg\bin\ffmpeg.exe") { $ffmpeg = ".\tools\ffmpeg\bin\ffmpeg.exe" }
elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) { $ffmpeg = "ffmpeg" }
if ($ffmpeg) {
    Add-Line ("ffmpeg: " + ((& $ffmpeg -version 2>&1)[0]))
    $fpp = $ffmpeg.Replace("ffmpeg.exe","ffprobe.exe")
    if (Test-Path $fpp) {
        Add-Line ("ffprobe: " + ((& $fpp -version 2>&1)[0]))
    } else {
        Add-Line "ffprobe: NOT FOUND next to ffmpeg"
    }
} else {
    Add-Line "ffmpeg: NOT FOUND"
}

# Model directory
if (Test-Path ".\models\faster-whisper-small\model.bin") {
    $mb = (Get-Item ".\models\faster-whisper-small\model.bin").Length / 1MB
    Add-Line ("whisper-small: model.bin present, {0:N1} MB" -f $mb)
} else {
    Add-Line "whisper-small: incomplete (model.bin missing)"
}

# Machine info
Add-Line ("os: " + (Get-CimInstance Win32_OperatingSystem).Caption)
Add-Line ("cpu: " + (Get-CimInstance Win32_Processor).Name)
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Add-Line ("ram: " + $ram + " GB")
$d = Get-PSDrive -Name "D" -ErrorAction SilentlyContinue
if ($d) { Add-Line ("disk D free: " + [math]::Round($d.Free / 1GB, 1) + " GB") }

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (Test-Path $edge) {
    Add-Line ("edge: " + (Get-Item $edge).VersionInfo.ProductVersion)
} else {
    $edge2 = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if (Test-Path $edge2) { Add-Line ("edge: " + (Get-Item $edge2).VersionInfo.ProductVersion) }
    else { Add-Line "browser edge: not found at default path (record manually)" }
}

Add-Line "===== end ====="
($script:lines -join "`r`n") | Out-File -FilePath "logs\env_check_latest.txt" -Encoding utf8
Write-Host ""
Write-Host "saved: logs\env_check_latest.txt"
