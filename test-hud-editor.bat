@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Rabbit Lands - HUD test
set "RL_HUD_CHECK=0"
if /i "%~1"=="--check" set "RL_HUD_CHECK=1"

rem One launcher, no companion script. It can also be copied to the desktop.
set "RL_HUD_PROJECT=%~dp0godot-client"
if exist "%RL_HUD_PROJECT%\project.godot" goto project_found
set "RL_HUD_PROJECT=%~dp0"
if exist "%RL_HUD_PROJECT%project.godot" goto project_found
set "RL_HUD_PROJECT=C:\rabbitlands\rabbitlands-client\godot-client"
if exist "%RL_HUD_PROJECT%\project.godot" goto project_found
echo Rabbit Lands client source was not found.
echo Keep this file in rabbitlands-client, or keep the client at C:\rabbitlands\rabbitlands-client.
goto failed

:project_found
for %%P in ("%RL_HUD_PROJECT%\.") do set "RL_HUD_PROJECT=%%~fP"
set "RL_HUD_ENGINE=%RL_HUD_PROJECT%\Godot_v4.7.2-stable_win64.exe"
if exist "%RL_HUD_ENGINE%" goto engine_found
set "RL_HUD_ENGINE=%RL_HUD_PROJECT%\Godot_v4.7.2-stable_win64_console.exe"
if exist "%RL_HUD_ENGINE%" goto engine_found
echo Godot 4.7.2 was not found beside the client.
echo Expected: %RL_HUD_PROJECT%\Godot_v4.7.2-stable_win64.exe
goto failed

:engine_found
set "RL_HUD_CHECK=0"
set "RL_HUD_FLAGS=--script res://prototypes/hud_editor_preview.gd -- --offline-hud-preview"
set "RL_HUD_FOLDER=%RL_HUD_PROJECT%\test-artifacts\hud-editor-local"
if /i "%~1"=="--help" goto help
if /i "%~1"=="--check" goto check_mode
if /i "%~1"=="--compatibility" goto compatibility_mode
if not "%~1"=="" goto help
goto client_mode

:compatibility_mode
set "RL_HUD_FLAGS=--rendering-method gl_compatibility --script res://prototypes/hud_editor_preview.gd -- --offline-hud-preview"

:client_mode
set "RL_HUD_PROFILE=%RL_HUD_FOLDER%\profile"
set "RL_HUD_LOG=%RL_HUD_FOLDER%\client.log"
echo.
echo Rabbit Lands - HUD editor test
echo.
echo This opens a LOCAL-ONLY Landfall sandbox with sample characters and game data.
echo No login or server is needed. Game connections and sends are disabled.
echo Use the floating sandbox box to add/remove sample party members.
echo Pick a preset there and choose Edit HUD, or press Ctrl+O, HUD, Edit HUD.
echo Try Current HUD and all five concept presets.
echo Drag HUD parts to move them. Drag a side handle to change width or height.
echo Resize near another window edge to align it; cyan guides show the snap.
echo Hold Shift to resize freely, or turn off Snap resize edges in Layout.
echo Resizing menu, spell and item areas reflows their rows and columns.
echo Dock to screen edges or join windows with Start, Center, End or Stretch.
echo Click curved meters directly to edit their resource, shape and color.
echo Connected parts move as a group. Hold Alt while dragging to detach.
echo Drag the editor title if it covers the part you want to change.
echo Undo and Redo are available. Restore default resets a built-in preset.
echo Look controls HUD backgrounds, borders, labels and icons.
echo Look offers circular map frames, map names, direction spacing and north arrowheads.
echo Option 2 contains your refined lower bars, party layout and round brass minimap.
echo Option 1 has a continuous Heritage rail; Blank HUD panel edits its filler.
echo Resource meters grow or reflow so enabled entries stay visible at the bottom.
echo Look includes separate background and border opacity controls.
echo Each option keeps its own edits when switching; Done ^& save retains them.
echo Escape leaves the party roster open; its own close control still works.
echo Options includes resource order/colors, player details and clock display.
echo Quick spell/item counts are available on every editor tab for those bars.
echo Docked panels share their outer frame when backgrounds/borders are enabled.
echo Use Save as new and Done ^& save to keep a custom preset.
echo.
echo Your HUD test settings are kept in a separate profile and survive reopening.
echo Your normal client settings are not changed.
echo.
goto launch

:check_mode
set "RL_HUD_CHECK=1"
set "RL_HUD_FLAGS=--headless --script res://tests/test_hud_presets.gd -- --offline-hud-preview"
set "RL_HUD_PROFILE=%RL_HUD_FOLDER%\verification-profile"
set "RL_HUD_LOG=%RL_HUD_FOLDER%\launcher-check.log"
echo Checking the live HUD controls, custom presets, chat, and saved settings...

:launch
if not exist "%RL_HUD_PROFILE%\" mkdir "%RL_HUD_PROFILE%"
if not exist "%RL_HUD_PROFILE%\" goto failed
rem These changes apply only to this launcher and the client it starts.
set "APPDATA=%RL_HUD_PROFILE%"
set "LOCALAPPDATA=%RL_HUD_PROFILE%"
pushd "%RL_HUD_PROJECT%"
if errorlevel 1 goto failed
start "" /wait "%RL_HUD_ENGINE%" --path "%RL_HUD_PROJECT%" --log-file "%RL_HUD_LOG%" %RL_HUD_FLAGS%
set "RL_HUD_RESULT=%ERRORLEVEL%"
popd
if not "%RL_HUD_RESULT%"=="0" goto client_failed
if "%RL_HUD_CHECK%"=="1" (
  findstr /b /c:"SCRIPT ERROR:" /c:"ERROR:" "%RL_HUD_LOG%" >nul
  if not errorlevel 1 (
    set "RL_HUD_RESULT=1"
    goto client_failed
  )
)
if "%RL_HUD_CHECK%"=="1" echo HUD checks completed successfully.
exit /b 0

:client_failed
echo.
echo The HUD test closed with error %RL_HUD_RESULT%.
echo Details: %RL_HUD_LOG%
if "%RL_HUD_CHECK%"=="1" exit /b %RL_HUD_RESULT%
pause
exit /b %RL_HUD_RESULT%

:failed
echo.
echo The HUD test could not start.
if "%RL_HUD_CHECK%"=="1" exit /b 1
pause
exit /b 1

:help
echo.
echo Double-click this file to run the local-only Rabbit Lands HUD sandbox.
echo Optional: test-hud-editor.bat --compatibility  ^(OpenGL graphics fallback^)
echo Optional: test-hud-editor.bat --check          ^(automated HUD checks^)
echo.
exit /b 0
