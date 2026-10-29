@echo off
setlocal
cd /d "%~dp0.."
python eloria-assets\tools\preview_foal_240.py %*
if errorlevel 1 pause
