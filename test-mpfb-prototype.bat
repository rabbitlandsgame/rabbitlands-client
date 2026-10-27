@echo off
setlocal
cd /d "%~dp0"
set "RL_MPFB_PROTOTYPE_ROOT=%~dp0.local\mpfb-prototype\runtime"
if not exist "%RL_MPFB_PROTOTYPE_ROOT%\male\luminous_male.glb" goto missing
if not exist "%RL_MPFB_PROTOTYPE_ROOT%\female\luminous_female.glb" goto missing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0godot-client\tools\human_customization_preview.ps1" %*
exit /b %errorlevel%
:missing
echo The local MPFB study files have not been built in this worktree.
echo See eloria-assets\tools\mpfb\README.md for the authoring steps.
pause
exit /b 1
