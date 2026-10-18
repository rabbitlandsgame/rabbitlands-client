@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run-moor-pony-game.ps1" %*
if errorlevel 1 pause
