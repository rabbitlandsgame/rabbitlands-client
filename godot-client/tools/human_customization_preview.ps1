[CmdletBinding()]
param(
    [string]$GodotPath = '',
    [switch]$Compatibility,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$clientRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $clientRoot
$previewRoot = Join-Path $repoRoot '.local/validation'
$profileRoot = Join-Path $repoRoot '.local/human-customization-preview'
if ($SmokeTest) { $profileRoot = Join-Path $profileRoot 'smoke-check' }

try {
    if (-not (Test-Path -LiteralPath (Join-Path $previewRoot 'project.godot'))) {
        throw 'The prepared local preview is missing. Ask Codex to rebuild the Human customization preview files.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $previewRoot 'assets/.gdignore'))) {
        throw 'The preview asset guard is missing. Ask Codex to repair the local preview before running it.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $previewRoot '.godot/global_script_class_cache.cfg'))) {
        throw 'The prepared preview cache is missing. Ask Codex to rebuild the local preview.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $previewRoot 'tests/human_customization_lab.gd'))) {
        throw 'The Human workshop script is missing from this preview.'
    }
    $candidates = @($GodotPath, $env:RL_GODOT_EXE,
        (Join-Path $clientRoot 'Godot_v4.7.2-stable_win64_console.exe'),
        (Join-Path $clientRoot 'Godot_v4.7.2-stable_win64.exe'))
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $commonDirectory = & git -C $repoRoot rev-parse --path-format=absolute --git-common-dir 2>$null
        if ($LASTEXITCODE -eq 0 -and $commonDirectory) {
            $primaryRoot = Split-Path -Parent ([string]$commonDirectory).Trim()
            $candidates += Join-Path $primaryRoot 'godot-client/Godot_v4.7.2-stable_win64_console.exe'
            $candidates += Join-Path $primaryRoot 'godot-client/Godot_v4.7.2-stable_win64.exe'
        }
    }
    $executable = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    if (-not $executable) {
        throw 'Godot 4.7.2 could not be found. Run this launcher with -GodotPath followed by the path to the Godot executable.'
    }
    New-Item -ItemType Directory -Path $profileRoot -Force | Out-Null
    $env:APPDATA = Join-Path $profileRoot 'Roaming'
    $env:LOCALAPPDATA = Join-Path $profileRoot 'Local'
    New-Item -ItemType Directory -Path $env:APPDATA, $env:LOCALAPPDATA -Force | Out-Null
    $logPath = Join-Path $profileRoot ('preview-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    $arguments = @('--path', ('"{0}"' -f $previewRoot),
        '--script', 'res://tests/human_customization_lab.gd',
        '--audio-driver', 'Dummy', '--log-file', ('"{0}"' -f $logPath))
    if ($Compatibility) { $arguments += @('--rendering-method', 'gl_compatibility') }
    if ($SmokeTest) { $arguments += @('--position', '-20000,-20000') }
    $arguments += @('--', '--offline-hud-preview')
    if ($SmokeTest) { $arguments += '--smoke-test' }

    Write-Host 'Opening the Rabbit Lands Human workshop...'
    Write-Host 'Choose Human Female or Male, an outfit, and a pose. Drag the character to rotate.'
    Write-Host 'Save preview keeps your choices locally. No account or server connection is needed.'
    Write-Host ('Log: ' + $logPath)
    $windowStyle = if ($SmokeTest) { 'Hidden' } else { 'Normal' }
    $process = Start-Process -FilePath $executable -ArgumentList $arguments -WorkingDirectory $previewRoot -WindowStyle $windowStyle -PassThru
    if ($SmokeTest) {
        if (-not $process.WaitForExit(120000)) {
            Stop-Process -Id $process.Id
            throw 'The preview smoke check did not finish within two minutes. Its log has been preserved.'
        }
    } else {
        $process.WaitForExit()
    }
    if ($process.ExitCode -ne 0) {
        if (Test-Path -LiteralPath $logPath) { Get-Content -LiteralPath $logPath -Tail 35 | Write-Host }
        throw ('The preview exited with an error. Log: ' + $logPath)
    }
    if ($SmokeTest) {
        if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'HUMAN_WORKSHOP_SMOKE: PASS' -Quiet)) {
            throw ('The preview smoke check did not report success. Log: ' + $logPath)
        }
        Write-Host 'Human workshop smoke check passed.'
    }
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
