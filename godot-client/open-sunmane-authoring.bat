@echo off
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
"%GODOT%" --editor --path "%~dp0." "res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn" %*
