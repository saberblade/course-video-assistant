# course-review M1 sample generator (SYS)
# Purpose:
#   1) synthesize a Chinese lecture clip with Windows TTS (no external network needed)
#   2) mux it into a sample MP4 that matches the release baseline:
#      MP4 container / H.264 video / AAC audio / <=20min / has audio track
#   3) verify the produced file with ffprobe (container, codec, duration)
# Usage (from course-review root):
#   powershell -ExecutionPolicy Bypass -File scripts\make_sample_video.ps1
# Output: data\tmp\sample_lecture.mp4   (do NOT commit; QA/PM may replace it with an authorized real lecture)
# NOTE: this is a pipeline-verification sample. Formal M1 evidence needs an authorized real lecture.
# PS 5.1 quirk: native stdout is decoded with the console codepage (GBK here). ffprobe prints
# UTF-8 JSON that contains the (Chinese) project path, so capturing via & broke parsing.
# Fix: redirect to a file through cmd, then read it back with -Encoding UTF8.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tmp  = Join-Path $root "data\tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

# ---------- tool paths ----------
$ffmpeg = $null
if (Test-Path (Join-Path $root "tools\ffmpeg\ffmpeg.exe")) { $ffmpeg = Join-Path $root "tools\ffmpeg\ffmpeg.exe" }
elseif (Test-Path (Join-Path $root "tools\ffmpeg\bin\ffmpeg.exe")) { $ffmpeg = Join-Path $root "tools\ffmpeg\bin\ffmpeg.exe" }
elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) { $ffmpeg = "ffmpeg" }
if (-not $ffmpeg) { throw "ffmpeg not found under tools\ffmpeg" }
$ffprobe = $ffmpeg.Replace("ffmpeg.exe","ffprobe.exe")

# ---------- 1) TTS -> wav ----------
Write-Host "[1/3] synthesizing Chinese speech via System.Speech ..."
Add-Type -AssemblyName System.Speech
$tts = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $tts.GetInstalledVoices() | Where-Object {
    ($_.VoiceInfo.Culture.Name -like "zh*") -or ($_.VoiceInfo.Name -match "Huihui|Yaoyao|Kangkang|Xiaoxiao")
} | Select-Object -First 1
if ($null -eq $voice) {
    Write-Warning "no Chinese TTS voice installed; using default voice (texts will still be spoken)"
    $voiceName = $null
} else {
    $voiceName = $voice.VoiceInfo.Name
    $tts.SelectVoice($voiceName)
    Write-Host ("  voice used: " + $voiceName)
}

$wav = Join-Path $tmp "sample_speech.wav"
$tts.Rate = 0
$tts.SetOutputToWaveFile($wav, [System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono))

$text = [System.IO.File]::ReadAllText((Join-Path $root "scripts\sample_text.txt"), [System.Text.Encoding]::UTF8)
$tts.Speak($text)
$tts.SetOutputToNull()
$tts.Dispose()
Write-Host ("  wav written: " + $wav + "  size=" + (Get-Item $wav).Length + " bytes")

# ---------- 2) wav -> sample mp4 (h264 + aac, blue card background) ----------
Write-Host "[2/3] encoding MP4 (H.264/AAC) with ffmpeg ..."
$mp4 = Join-Path $tmp "sample_lecture.mp4"
if (Test-Path $mp4) { Remove-Item $mp4 -Force }
$enc = cmd /c "`"$ffmpeg`" -hide_banner -y -f lavfi -i ""color=c=#1a3b6b:s=1280x720:r=15"" -i ""$wav"" -c:v libx264 -preset veryfast -crf 30 -pix_fmt yuv420p -c:a aac -b:a 96k -ar 16000 -shortest ""$mp4"" 2>&1"
if ($LASTEXITCODE -ne 0) { $enc | Select-Object -Last 8; throw "ffmpeg encode failed (exit $LASTEXITCODE)" }
$enc | Select-Object -Last 2
Write-Host ("  mp4 written: " + $mp4 + "  size=" + (Get-Item $mp4).Length + " bytes")

# ---------- 3) ffprobe verification ----------
Write-Host "[3/3] ffprobe verification ..."
$probeJson = Join-Path $tmp "sample_probe.json"
cmd /c "`"$ffprobe`" -v quiet -print_format json -show_format -show_streams ""$mp4"" > ""$probeJson"" 2>nul"
$probe = Get-Content $probeJson -Raw -Encoding UTF8 | ConvertFrom-Json
$v = $probe.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1
$a = $probe.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1
Write-Host ("  container      : " + $probe.format.format_name)
Write-Host ("  size           : " + $probe.format.size + " bytes")
Write-Host ("  duration_sec   : " + $probe.format.duration)
Write-Host ("  video codec    : " + $v.codec_name + " " + ($v.width) + "x" + ($v.height))
Write-Host ("  audio codec    : " + $a.codec_name + "  channels=" + $a.channels)
Write-Host "sample generation DONE -> $mp4"
