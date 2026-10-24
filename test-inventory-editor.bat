@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "RL_INVENTORY_ROOT=%~dp0godot-client"
set "RL_INVENTORY_PROJECT=%RL_INVENTORY_ROOT%"
if not exist "%RL_INVENTORY_PROJECT%\prototypes\inventory_editor_preview.gd" (
  echo Inventory preview files were not found beside this launcher.
  pause
  exit /b 1
)
set "RL_INVENTORY_ENGINE=%RL_INVENTORY_ROOT%\Godot_v4.7.2-stable_win64.exe"
if not exist "%RL_INVENTORY_ENGINE%" (
  echo Godot 4.7.2 is required beside the client project.
  pause
  exit /b 1
)
set "APPDATA=%RL_INVENTORY_ROOT%\test-artifacts\inventory-designs\interactive-profile"
set "LOCALAPPDATA=%APPDATA%"
if not exist "%APPDATA%" mkdir "%APPDATA%"
echo Rabbit Lands inventory sandbox: offline sample items; no login or server connection.
echo Inventory and HUD preview settings are saved in their own profile.
start "" /wait "%RL_INVENTORY_ENGINE%" --path "%RL_INVENTORY_PROJECT%" --rendering-method gl_compatibility --script res://prototypes/inventory_editor_preview.gd -- --offline-hud-preview
endlocal
