@echo off
rem Equipment review viewer: the real client actor on a turntable.
rem   review-equipment.bat [--race luminous] [--sex male] [--set "Vanguard"] [--clip Walk] [--review-dir <folder>]
rem Notes and screenshots (F2) go to ..\.local\asset-authoring\working\equipment-review\<session>\
rem Close any GPU-heavy renders first: the laptop GPU handles one at a time.
setlocal
set "GODOT=%GODOT_EXE%"
if not defined GODOT set "GODOT=%~dp0Godot_v4.7.2-stable_win64_console.exe"
if not exist "%GODOT%" set "GODOT=%~dp0Godot_v4.7.2-stable_win64.exe"
if not exist "%GODOT%" for %%G in (godot.exe) do set "GODOT=%%~$PATH:G"
if not defined GODOT (
  echo Install Godot 4.7.2 or set GODOT_EXE to its executable.
  pause
  exit /b 1
)
"%GODOT%" --path "%~dp0." --script "res://tools/equipment_review/equipment_review.gd" -- %*
if errorlevel 1 pause
