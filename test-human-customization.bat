@echo off
setlocal
title Rabbit Lands - Human Customization Preview
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0godot-client\tools\human_customization_preview.ps1" %*
if errorlevel 1 (
    echo.
    echo The preview could not start. The explanation is above.
    pause
    exit /b 1
)
endlocal
