@echo off
setlocal
cd /d "%~dp0.."
python eloria-assets\tools\preview_creature_sampling.py --actor crystalback_tortoise --fps 30 %*
if errorlevel 1 pause
