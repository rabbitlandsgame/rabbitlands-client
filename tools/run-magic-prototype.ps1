param(
    [ValidateSet('prepared', 'aimed', 'wheel')][string]$Mode = 'wheel',
    [ValidateSet('baseline', 'quick', 'orbit')][string]$WheelVariant = 'baseline',
    [switch]$Live,
    [switch]$Check,
    [switch]$PlainTcp,
    [string]$GodotPath = '',
    [string]$Server = '',
    [int]$Port = 2001
)
$ErrorActionPreference = 'Stop'
if ($Live -and $WheelVariant -eq 'orbit') { throw 'Orbit is a practice comparison. The live client uses the Quick ring.' }
$prototypeRoot = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $prototypeRoot 'godot-client'
$assetSource = Join-Path (Split-Path -Parent $prototypeRoot) 'rabbitlands-client'

if (-not $GodotPath) {
    $candidates = @(
        (Join-Path $projectPath 'Godot_v4.7.2-stable_win64_console.exe'),
        (Join-Path $projectPath 'Godot_v4.7.2-stable_win64.exe'),
        (Join-Path $env:USERPROFILE 'Downloads/godot47/Godot_v4.7.2-stable_win64_console.exe'),
        (Join-Path $env:USERPROFILE 'Downloads/Godot_v4.7.2-stable_win64.exe/Godot_v4.7.2-stable_win64_console.exe')
    )
    $installed = Get-Command godot -ErrorAction SilentlyContinue
    if ($installed) { $candidates += $installed.Source }
    $GodotPath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $GodotPath -or -not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) {
    throw 'Godot 4.7.2 was not found. Run this script with -GodotPath pointing to the Godot executable.'
}
$engineVersion = (& $GodotPath --version | Out-String).Trim()
if ($engineVersion -notmatch '^4\.7\.2\.') { throw "Expected Godot 4.7.2; found $engineVersion" }

if ([IO.Path]::GetFullPath($assetSource) -ne [IO.Path]::GetFullPath($prototypeRoot)) {
# The local worktree reuses the main checkout's imported artwork. Do not run
# the editor/importer over the shared assets. A full checkout can import its
# own assets normally before running this launcher.
foreach ($link in @(
    @{ Destination = (Join-Path $projectPath 'assets'); Source = (Join-Path $assetSource 'godot-client/assets') },
    @{ Destination = (Join-Path $prototypeRoot 'eloria-assets'); Source = (Join-Path $assetSource 'eloria-assets') },
    @{ Destination = (Join-Path $projectPath '.godot/imported'); Source = (Join-Path $assetSource 'godot-client/.godot/imported') }
)) {
    if (-not (Test-Path -LiteralPath $link.Destination)) {
        if (-not (Test-Path -LiteralPath $link.Source)) { throw "Required assets missing: $($link.Source)" }
        New-Item -ItemType Directory -Path (Split-Path -Parent $link.Destination) -Force | Out-Null
        New-Item -ItemType Junction -Path $link.Destination -Target $link.Source | Out-Null
    }
}
foreach ($cache in @('global_script_class_cache.cfg', 'uid_cache.bin', '.gdignore')) {
    $destination = Join-Path $projectPath ".godot/$cache"
    $source = Join-Path $assetSource "godot-client/.godot/$cache"
    if (-not (Test-Path -LiteralPath $destination) -and (Test-Path -LiteralPath $source)) {
        Copy-Item -LiteralPath $source -Destination $destination
    }
}
$translation = Join-Path $projectPath 'data/i18n/strings.en.translation'
if (-not (Test-Path -LiteralPath $translation)) {
    Copy-Item -LiteralPath (Join-Path $assetSource 'godot-client/data/i18n/strings.en.translation') -Destination $translation
}
}
$artifactPath = Join-Path $projectPath 'test-artifacts/magic-casting'
New-Item -ItemType Directory -Path $artifactPath -Force | Out-Null
$launchLog = Join-Path $artifactPath $(if ($WheelVariant -eq 'baseline') { "launch-$Mode.log" } else { "launch-$Mode-$WheelVariant.log" })
$launchArguments = @('--path', $projectPath, '--log-file', $launchLog)
if ($Check) {
    $launchArguments += @('--headless', '--script', 'res://tests/test_magic_casting_prototype.gd', '--quit-after', '1200')
} elseif (-not $Live) {
    $launchArguments += 'res://src/dev/magic_practice.tscn'
}
$launchArguments += @('--', "--magic-mode=$Mode", "--wheel-variant=$WheelVariant")
if ($PlainTcp) {
    $launchArguments += '--dev-plain-tcp'
    if (-not $PSBoundParameters.ContainsKey('Port')) { $Port = 2000 }
}
if ($Server) { $launchArguments += "--server=$Server" }
if ($Server -or $PSBoundParameters.ContainsKey('Port')) { $launchArguments += "--port=$Port" }
Write-Host "Magic casting prototype: $Mode"
Write-Host $(if ($Live) { 'Live client: log in through the normal login screen.' } else { 'Offline practice: simulated outcomes; no login required.' })
$savedAppData = $env:APPDATA
$savedLocalAppData = $env:LOCALAPPDATA
try {
    if (-not $Live -or $Check) {
        $practiceProfile = Join-Path $artifactPath 'offline-profile'
        New-Item -ItemType Directory -Path $practiceProfile -Force | Out-Null
        $env:APPDATA = $practiceProfile
        $env:LOCALAPPDATA = $practiceProfile
    }
    & $GodotPath @launchArguments
    $engineExit = $LASTEXITCODE
    if ($Check) {
        $logText = Get-Content -LiteralPath $launchLog -Raw
        if ($logText -notmatch 'magic casting prototype: PASS' -or $logText -match 'SCRIPT ERROR|FAIL:') { exit 1 }
        if ($WheelVariant -ne 'baseline') {
            $trialLog = Join-Path $artifactPath "trials-$WheelVariant.log"
            & $GodotPath --headless --path $projectPath --script res://tests/test_magic_wheel_trials.gd --log-file $trialLog --quit-after 1200
            $engineExit = $LASTEXITCODE
            $trialText = Get-Content -LiteralPath $trialLog -Raw
            if ($trialText -notmatch 'magic wheel trials: PASS' -or $trialText -match 'SCRIPT ERROR|FAIL:') { exit 1 }
        }
    }
} finally {
    $env:APPDATA = $savedAppData
    $env:LOCALAPPDATA = $savedLocalAppData
}
exit $engineExit
