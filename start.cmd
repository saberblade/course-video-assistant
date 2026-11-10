@echo off
rem ---------------------------------------------------------------------------
rem  One-click launcher for the course video review assistant.
rem  Double-click this file, or run  start.cmd  from the project folder.
rem  Backend (8000) and frontend dev server (5173) each get their own window.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\start-all.ps1"
if errorlevel 1 pause
