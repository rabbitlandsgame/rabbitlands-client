param([string]$GodotPath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $GodotPath) {
    $candidates = @(
        (Join-Path $projectRoot 'godot-client/Godot_v4.7.2-stable_win64.exe'),
        (Join-Path $env:USERPROFILE 'Downloads/godot47/Godot_v4.7.2-stable_win64_console.exe')
    )
    $installed = Get-Command godot -ErrorAction SilentlyContinue
    if ($installed) { $candidates += $installed.Source }
    $GodotPath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $GodotPath) { throw 'Godot was not found. Pass -GodotPath with your Godot 4.7.2 executable.' }
Write-Host 'Opening Rabbit Lands with a disposable local test character. Use Mount pony, then Gallop. Close the game to stop the test server.'
python (Join-Path $PSScriptRoot 'test_moor_pony_in_game.py') --godot $GodotPath
exit $LASTEXITCODE
