@echo off
cd /d "%~dp0.."
python eloria-assets\tools\preview_tortoise_corrective_repair.py --variant bake-v2
if errorlevel 1 pause
