@echo off
rem Double-click to start everything. Add -Ngrok or -Beat after the name when you run it from a terminal.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-all.ps1" %*
pause
