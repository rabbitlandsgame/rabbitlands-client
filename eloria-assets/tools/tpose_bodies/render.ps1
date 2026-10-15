param(
    [string]$Slug = 'luminous_female',
    [string]$Prefix = 'approved',
    [switch]$Cycles,
    [switch]$Quick,
    [switch]$WithGear
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$buildRoot = Join-Path $taskRoot 'tpose-body-build'
$jobs = @()
if ($Quick) {
    $jobs += @{Name='walk'; Clip='Walk'; Angle='gameplay'; Hair='no'; Tints='no'; Head='0'; Gear='no'}
    $jobs += @{Name='appearance'; Clip='Idle_Subtle'; Angle='front'; Hair='no'; Tints='yes'; Head='3'; Gear='no'}
    $jobs += @{Name='hair'; Clip='Idle_Subtle'; Angle='side'; Hair='yes'; Tints='no'; Head='0'; Gear='no'}
    if ($WithGear) { $jobs += @{Name='gear'; Clip='Walk'; Angle='gameplay'; Hair='yes'; Tints='no'; Head='0'; Gear='yes'} }
} else {
    foreach ($clip in @('Idle_Subtle','Walk','Jog','Fighting_Idle','Run_Female')) {
        $jobs += @{Name=$clip; Clip=$clip; Angle='gameplay'; Hair='yes'; Tints='no'; Head='0'; Gear='no'}
    }
    $jobs += @{Name='side'; Clip='Walk'; Angle='side'; Hair='yes'; Tints='no'; Head='0'; Gear='no'}
    $jobs += @{Name='tints'; Clip='Walk'; Angle='front'; Hair='no'; Tints='yes'; Head='3'; Gear='no'}
    $jobs += @{Name='gear'; Clip='Walk'; Angle='gameplay'; Hair='yes'; Tints='no'; Head='0'; Gear='yes'}
}
foreach ($job in $jobs) {
    $name = "$Prefix`_$Slug`_$($job.Name)"
    $outputPath = "$buildRoot/preview/$name.png"
    $argsList = @('--path', "$taskRoot/godot-client", '--script', 'res://tests/tpose_body_preview.gd',
        '--log-file', "$buildRoot/preview/$name-engine.log", '--', '--model', "$buildRoot/out/$Slug.glb",
        '--out', $outputPath, '--slug', $Slug, '--library', "$buildRoot/out/Universal_Animation_Library.glb",
        '--clip', $job.Clip, '--angle', $job.Angle, '--hair', $job.Hair, '--tints', $job.Tints, '--head', $job.Head, '--gear', $job.Gear)
    if (Test-Path -LiteralPath "$buildRoot/out/$Slug.hair-fit.json") {
        $argsList += @('--hair-fit', "$buildRoot/out/$Slug.hair-fit.json")
    }
    if ($Cycles -and $job.Name -eq $job.Clip) { $argsList += @('--cycle', 'yes') }
    $process = Start-Process -FilePath 'godot' -ArgumentList $argsList -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput "$buildRoot/preview/$name.log" -RedirectStandardError "$buildRoot/preview/$name.err"
    if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath "$outputPath.json")) { throw "Capture failed: $name" }
    Write-Output $outputPath
}
