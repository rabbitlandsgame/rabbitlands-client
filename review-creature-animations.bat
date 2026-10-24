@echo off
setlocal
cd /d "%~dp0"
if exist "C:\Python\Python313\python.exe" (
  "C:\Python\Python313\python.exe" -B "tools\asset-authoring\creature_review.py" --root "%~dp0." --open
) else (
  py -3 -B "tools\asset-authoring\creature_review.py" --root "%~dp0." --open
)
if errorlevel 1 pause
endlocal
