@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "RL_MIX_CLIENT=%~dp0"
set "RL_MIX_SERVER=%~dp0..\rabbitlands-server"
if not exist "%RL_MIX_SERVER%\tools\mixing_trial.py" (
  echo The rabbitlands-server checkout is required beside rabbitlands-client.
  pause
  exit /b 1
)
echo Rabbit Lands local mixing trial: separate character, storage and settings.
echo Choose a preset in the trial panel or Mixing's More menu.
echo Close the client to stop its private local server.
python "%RL_MIX_SERVER%\tools\mixing_trial.py" --client-root "%RL_MIX_CLIENT%." %*
if errorlevel 1 pause
endlocal
