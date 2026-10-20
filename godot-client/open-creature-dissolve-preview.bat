@echo off
setlocal
cd /d "%~dp0"
set "GODOT=%~dp0Godot_v4.7.2-stable_win64.exe"
if not exist "%GODOT%" set "GODOT=%USERPROFILE%\Downloads\godot47\Godot_v4.7.2-stable_win64_console.exe"
if not exist "%GODOT%" (
    echo Godot 4.7.2 could not be found beside the project or in Downloads\godot47.
    pause
    exit /b 1
)
"%GODOT%" --path "%~dp0." --script res://prototypes/creature_dissolve_preview.gd %*
if errorlevel 1 pause
