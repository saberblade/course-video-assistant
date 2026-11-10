@echo off
rem ---------------------------------------------------------------------------
rem  One-click shutdown for the course video review assistant.
rem  Double-click this file, or run  stop.cmd  from the project folder.
rem  Refuses to stop while a video is still being transcribed; use
rem    stop.cmd -Force
rem  to override.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\stop-all.ps1" %*
if errorlevel 1 pause
