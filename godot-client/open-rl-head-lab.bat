@echo off
rem RL head lab: the real client actor wearing the RL head prototype.
rem   open-rl-head-lab.bat [--sex male] [--preset rowan] [--quality medium] [--look game]
rem The editor/user profile is an isolated one under ..\.local\rl-heads\godot-user\lab,
rem so the lab never reads or writes the player's settings. GODOT_EXE overrides
rem the Godot 4.7.2 executable; otherwise the one beside this project, then the
rem primary checkout's (for a worktree), then godot.exe on PATH.
rem Close any GPU-heavy renders first: the laptop GPU handles one at a time.
setlocal
for %%I in ("%~dp0..") do set "CHECKOUT=%%~fI"
set "GODOT=%GODOT_EXE%"
if not defined GODOT set "GODOT=%~dp0Godot_v4.7.2-stable_win64.exe"
if not exist "%GODOT%" set "GODOT=%CHECKOUT%\..\..\rabbitlands-client\godot-client\Godot_v4.7.2-stable_win64.exe"
if not exist "%GODOT%" for %%G in (godot.exe) do set "GODOT=%%~$PATH:G"
if not exist "%GODOT%" (
  echo Godot 4.7.2 was not found. Set GODOT_EXE to its executable.
  pause
  exit /b 1
)
set "PROFILE=%CHECKOUT%\.local\rl-heads\godot-user\lab"
if not exist "%PROFILE%\appdata" mkdir "%PROFILE%\appdata"
if not exist "%PROFILE%\localappdata" mkdir "%PROFILE%\localappdata"
if not exist "%PROFILE%\temp" mkdir "%PROFILE%\temp"
set "APPDATA=%PROFILE%\appdata"
set "LOCALAPPDATA=%PROFILE%\localappdata"
set "TEMP=%PROFILE%\temp"
set "TMP=%PROFILE%\temp"
"%GODOT%" --path "%~dp0." --log-file "%PROFILE%\lab.log" res://prototypes/rl_heads/rl_head_lab.tscn -- %*
if errorlevel 1 pause
