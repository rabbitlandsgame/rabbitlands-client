@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0play.ps1" %*
set "launchResult=%ERRORLEVEL%"
if not "%launchResult%"=="0" pause
exit /b %launchResult%
