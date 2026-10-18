@echo off
setlocal
pushd "%~dp0." || exit /b 1
if not exist "Godot_v4.7.2-stable_win64.exe" (
    echo The bundled Godot application is missing from this folder.
    pause
    popd
    exit /b 1
)
set "RL_REVIEW_LOG=%TEMP%\rabbitlands-technique-review.log"
echo Opening the Rabbit Lands combat technique review...
echo Startup log: %RL_REVIEW_LOG%
"Godot_v4.7.2-stable_win64.exe" --path . --rendering-method gl_compatibility --log-file "%RL_REVIEW_LOG%" res://src/dev/technique_showcase.tscn %*
set "RL_REVIEW_EXIT=%ERRORLEVEL%"
if not "%RL_REVIEW_EXIT%"=="0" (
    echo The review could not start. See the startup log above for details.
    pause
)
popd
exit /b %RL_REVIEW_EXIT%
