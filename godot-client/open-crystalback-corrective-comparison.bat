@echo off
cd /d "%~dp0.."
python eloria-assets\tools\preview_tortoise_corrective_repair.py
if errorlevel 1 pause
