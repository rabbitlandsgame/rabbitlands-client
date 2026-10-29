@echo off
setlocal
cd /d "%~dp0.."
python -B eloria-assets\tools\review_creature_runtime_optimization.py --catalog .local\creature-runtime-retrofit\review-catalog.json --reuse-project
if errorlevel 1 pause
