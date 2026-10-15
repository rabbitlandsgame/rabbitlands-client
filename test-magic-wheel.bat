@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run-magic-prototype.ps1" -Mode wheel %*
if errorlevel 1 pause
