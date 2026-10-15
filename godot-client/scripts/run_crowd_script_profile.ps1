[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GodotPath,
    [string]$Label = 'crowd-primary-all-script-profile-v1',
    [ValidateRange(1000, 30000)][int]$SampleMilliseconds = 5000,
    [ValidateRange(1, 30)][int]$TimeoutMinutes = 10,
    [string]$InterferenceLabel =
        'shared host; unrelated Godot jobs authorized; activity not continuously monitored'
)

$ErrorActionPreference = 'Stop'
(Get-Process -Id $PID).ProcessorAffinity = 15

$clientRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $clientRoot)).Path
$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]+', '-').Trim('-')
if ([string]::IsNullOrWhiteSpace($safeLabel) -or $safeLabel -ne $Label) {
    throw 'Label must already be a nonempty filename-safe value.'
}
$requestedGodot = (Resolve-Path -LiteralPath $GodotPath).Path
$launchGodot = $requestedGodot
if ([IO.Path]::GetFileNameWithoutExtension($requestedGodot) -like '*_console') {
    $direct = Join-Path (Split-Path -Parent $requestedGodot) `
        (([IO.Path]::GetFileNameWithoutExtension($requestedGodot) `
            -replace '_console$', '') + '.exe')
    $launchGodot = (Resolve-Path -LiteralPath $direct).Path
}

$runRoot = Join-Path $clientRoot 'test-artifacts/native-crowd/script-profiler'
$timestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$sessionRoot = Join-Path $runRoot "$safeLabel-$timestamp"
$userRoot = Join-Path $sessionRoot 'user-data'
New-Item -ItemType Directory -Force -Path $sessionRoot, $userRoot | Out-Null

$gitSafe = "safe.directory=$($repositoryRoot.Replace('\', '/'))"
function Invoke-Git([string[]]$Arguments) {
    $result = @(& git -c $gitSafe -C $repositoryRoot @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed."
    }
    return $result
}

$commit = (Invoke-Git @('rev-parse', 'HEAD')).Trim()
$branch = (Invoke-Git @('branch', '--show-current')).Trim()
$sourceRelativePaths = @(
    'godot-client/tests/integration/crowd_benchmarks.gd',
    'godot-client/tests/integration/crowd_benchmark_main.gd',
    'godot-client/tests/integration/crowd_benchmark_main.tscn',
    'godot-client/scripts/run_crowd_script_profile.ps1',
    'godot-client/project.godot',
    'godot-client/src/state/app_state.gd',
    'godot-client/src/app/main.gd',
    'godot-client/src/actors/replicated_actor_3d.gd',
    'godot-client/src/actors/ranger_bow_3d.gd',
    'godot-client/src/actors/cape_cloth.gd',
    'godot-client/src/actors/combat_presentation_3d.gd',
    'godot-client/src/world/world_effect_3d.gd',
    'godot-client/src/world/spell_flight_3d.gd',
    'godot-client/src/world/combat_effect_mesh.gd',
    'godot-client/src/world/animation_gate.gd',
    'godot-client/native/native_crowd/src/native_crowd_reducer.cpp',
    'godot-client/native/native_crowd/src/native_crowd_reducer.h',
    'godot-client/native/native_crowd/src/native_cape_constraint_kernel.cpp',
    'godot-client/native/native_crowd/src/native_cape_constraint_kernel.h',
    'godot-client/native/native_crowd/src/native_spell_flight_geometry.cpp',
    'godot-client/native/native_crowd/src/native_spell_flight_geometry.h',
    'godot-client/native/native_crowd/src/native_world_effect_geometry.cpp',
    'godot-client/native/native_crowd/src/native_world_effect_geometry.h',
    'godot-client/native/native_crowd/src/register_types.cpp',
    'godot-client/native/native_crowd/src/register_types.h',
    'godot-client/native/native_crowd/CMakeLists.txt',
    'godot-client/native/native_crowd/build_profile.json',
    'godot-client/bin/native_crowd.gdextension',
    'godot-client/bin/windows/native_crowd.windows.template_release.x86_64.dll'
)
$sourceHashes = [ordered]@{}
$snapshotCachePath = 'godot-client/src/actors/equipment_registry_snapshot_cache.gd'
if (Test-Path -LiteralPath (Join-Path $repositoryRoot $snapshotCachePath) -PathType Leaf) {
    $sourceRelativePaths += $snapshotCachePath
}
foreach ($relativePath in $sourceRelativePaths) {
    $absolutePath = Join-Path $repositoryRoot $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath -PathType Leaf)) {
        throw "Required profiler source input is missing: $relativePath"
    }
    $sourceHashes[$relativePath] = (Get-FileHash -Algorithm SHA256 `
        -LiteralPath $absolutePath).Hash.ToLowerInvariant()
}
$sourceText = ($sourceHashes.GetEnumerator() | ForEach-Object {
    "$($_.Key)=$($_.Value)"
}) -join "`n"
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $sourceHash = [Convert]::ToHexString($sha256.ComputeHash(
        [Text.Encoding]::UTF8.GetBytes($sourceText))).ToLowerInvariant()
}
finally {
    $sha256.Dispose()
}
$trackedStatus = @(Invoke-Git @('status', '--porcelain', '--untracked-files=no'))
$dirty = $trackedStatus.Count -gt 0

$env:APPDATA = Join-Path $userRoot 'appdata'
$env:LOCALAPPDATA = Join-Path $userRoot 'localappdata'
$env:USERPROFILE = Join-Path $userRoot 'profile'
$env:TEMP = Join-Path $userRoot 'temp'
$env:TMP = $env:TEMP
$env:NUMBER_OF_PROCESSORS = '4'
$env:GODOT_THREADS_OVERRIDE = '2'
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:LOCALAPPDATA,
    $env:USERPROFILE, $env:TEMP | Out-Null

$env:ELORIA_NATIVE_CROWD = '0'
$env:ELORIA_NATIVE_PRESENTATION = 'all'
$env:ELORIA_CROWD_NATIVE_BACKEND = 'gdscript'
$env:ELORIA_CROWD_PROFILE = 'primary'
$env:ELORIA_CROWD_COUNTS = ''
$env:ELORIA_CROWD_POPULATIONS = ''
$env:ELORIA_CROWD_ACTIVITIES = ''
$env:ELORIA_CROWD_VISIBILITIES = ''
$env:ELORIA_CROWD_FEATURES = ''
$env:ELORIA_CROWD_NETWORKS = ''
$env:ELORIA_CROWD_MAP = 'four_gates'
$env:ELORIA_CROWD_SAMPLE_MSEC = [string]$SampleMilliseconds
$env:ELORIA_CROWD_WARMUP_MSEC = '1000'
$env:ELORIA_CROWD_CADENCE_MSEC = '100'
$env:ELORIA_CROWD_CAPTURE = '0'
$env:ELORIA_CROWD_ATTRIBUTION = '0'
$env:ELORIA_CROWD_LABEL = $safeLabel
$env:ELORIA_CROWD_INTERFERENCE = $InterferenceLabel
$env:ELORIA_CROWD_ARTIFACT_DIR = $sessionRoot
$env:ELORIA_CROWD_USER_ROOT = $userRoot
$env:ELORIA_CROWD_COMMIT = $commit
$env:ELORIA_CROWD_DIRTY = if ($dirty) { '1' } else { '0' }
$env:ELORIA_CROWD_SOURCE_HASH = $sourceHash
$env:ELORIA_CROWD_RENDERER = 'gl_compatibility'
$env:ELORIA_CROWD_TRIAL = '1'
$env:ELORIA_CROWD_RUN_ID = $safeLabel
$env:ELORIA_CROWD_OUTPUT = 'crowd-report.json'
$env:ELORIA_CROWD_PROCESS_METADATA = (@{
    runnerPid = $PID
    affinityMask = 15
    logicalProcessors = @(0, 1, 2, 3)
    requestedWorkerThreads = 2
    requestedNativePresentation = 'All'
    nativePresentationEnvironment = 'all'
    diagnostic = 'Godot local script profiler; process-lifetime accumulated data'
} | ConvertTo-Json -Compress)

$stdoutPath = Join-Path $sessionRoot 'profiler.stdout.log'
$stderrPath = Join-Path $sessionRoot 'profiler.stderr.log'
$logPath = Join-Path $sessionRoot 'godot.log'
$reportPath = Join-Path $sessionRoot 'crowd-report.json'
$processPath = Join-Path $sessionRoot 'process.json'
$arguments = @(
    '--headless', '--debug', '--profiling', '--audio-driver', 'Dummy',
    '--rendering-method', 'gl_compatibility', '--path', $clientRoot,
    '--script', 'res://tests/integration/crowd_benchmarks.gd',
    '--log-file', $logPath
)

function Quote-ProcessArgument([string]$Value) {
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}
$quotedArguments = @($arguments | ForEach-Object {
    Quote-ProcessArgument ([string]$_
    )
})

$startedAt = (Get-Date).ToUniversalTime()
$process = Start-Process -FilePath $launchGodot -ArgumentList $quotedArguments `
    -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath
$observedMasks = [Collections.Generic.List[long]]::new()
$identityPath = ''
$identityStart = $null
$monitoringError = ''
$forcedTermination = $false
try {
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    while (-not $process.HasExited) {
        $process.ProcessorAffinity = 15
        $process.Refresh()
        $mask = $process.ProcessorAffinity.ToInt64()
        $observedMasks.Add($mask)
        if ($mask -ne 15) { throw "Godot affinity was $mask, expected 15." }
        if ([string]::IsNullOrWhiteSpace($identityPath)) {
            for ($probe = 0; $probe -lt 20; $probe++) {
                try {
                    $identityPath = $process.MainModule.FileName
                    $identityStart = $process.StartTime.ToUniversalTime()
                    break
                }
                catch {
                    Start-Sleep -Milliseconds 50
                    $process.Refresh()
                    if ($process.HasExited) { break }
                }
            }
        }
        if ((Get-Date) -ge $deadline) {
            $process.Kill($true)
            $forcedTermination = $true
            throw "Profile exceeded the $TimeoutMinutes minute timeout."
        }
        Start-Sleep -Seconds 1
        $process.Refresh()
    }
    $process.WaitForExit()
}
catch {
    $monitoringError = $_.Exception.Message
    if (-not $process.HasExited) {
        $process.Kill($true)
        $forcedTermination = $true
    }
    $process.WaitForExit()
}
$completedAt = (Get-Date).ToUniversalTime()

$scriptErrors = $false
foreach ($path in @($stdoutPath, $stderrPath, $logPath)) {
    if ((Test-Path -LiteralPath $path) -and
            (Select-String -LiteralPath $path -Pattern 'SCRIPT ERROR|Parse Error' -Quiet)) {
        $scriptErrors = $true
    }
}
$profileStarted = Select-String -LiteralPath $stdoutPath -Pattern '^BEGIN PROFILING$' -Quiet
$profileAccumulated = Select-String -LiteralPath $stdoutPath `
    -Pattern '^ACCUMULATED: total:' -Quiet
$report = $null
$reportValid = $false
$reportError = ''
try {
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
        throw 'Crowd report was not written.'
    }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $cells = @($report.cells)
    if ($report.failureCount -ne 0 -or $cells.Count -ne 1 -or
            $report.profile -ne 'primary' -or -not $report.headless -or
            $report.actualRenderingMethod -ne 'gl_compatibility' -or
            $report.nativeBackend -ne 'gdscript' -or
            $report.nativePresentation.requestedMode -ne 'all' -or
            -not [bool]$report.nativePresentation.actual.matchedRequest -or
            [int]$report.nativePresentation.actual.capeFallbackCalls -ne 0 -or
            [int]$report.nativePresentation.actual.flightBuildFallbacks -ne 0 -or
            [int]$report.nativePresentation.actual.worldBuildFallbacks -ne 0 -or
            $cells[0].count -ne 300 -or $cells[0].plannedActive -ne 100 -or
            $cells[0].fixture.before.frustumAndDrawVisible -ne 150 -or
            @($cells[0].sample.raw.wallMilliseconds).Count -lt 60 -or
            [double]$cells[0].sample.summary.flushesPerFrame.max -gt 1 -or
            $report.interferenceLabel -ne $InterferenceLabel -or
            $report.commit -ne $commit -or $report.sourceHash -ne $sourceHash -or
            [bool]$report.dirty -ne $dirty) {
        throw 'Crowd report contract did not match the requested profiled primary fixture.'
    }
    $reportValid = $true
}
catch {
    $reportError = $_.Exception.Message
}

$cleanExit = $process.ExitCode -eq 0 -and -not $forcedTermination
$identityVerified = -not [string]::IsNullOrWhiteSpace($identityPath) -and
    ([IO.Path]::GetFullPath($identityPath) -eq [IO.Path]::GetFullPath($launchGodot))
$profileValid = $profileStarted -and $profileAccumulated
$valid = $cleanExit -and $identityVerified -and $observedMasks.Count -gt 0 -and
    @($observedMasks | Where-Object { $_ -ne 15 }).Count -eq 0 -and
    -not $scriptErrors -and [string]::IsNullOrWhiteSpace($monitoringError) -and
    $reportValid -and $profileValid
$processRecord = [ordered]@{
    schemaVersion = 1
    diagnosticOnly = $true
    acceptanceEligible = $false
    reason = 'Godot script-profiler instrumentation covers the full process lifetime'
    label = $safeLabel
    branch = $branch
    commit = $commit
    dirty = $dirty
    sourceHash = $sourceHash
    sourceFiles = $sourceHashes
    nativePresentation = 'all'
    nativeReducer = 'gdscript'
    requestedGodotPath = $requestedGodot
    requestedGodotSha256 = (Get-FileHash -Algorithm SHA256 `
        -LiteralPath $requestedGodot).Hash.ToLowerInvariant()
    launchExecutablePath = $launchGodot
    launchExecutableSha256 = (Get-FileHash -Algorithm SHA256 `
        -LiteralPath $launchGodot).Hash.ToLowerInvariant()
    arguments = $arguments
    startedAtUtc = $startedAt.ToString('o')
    completedAtUtc = $completedAt.ToString('o')
    rootPid = $process.Id
    exitCode = $process.ExitCode
    cleanExit = $cleanExit
    forcedTermination = $forcedTermination
    affinityMask = 15
    observedAffinityMasks = @($observedMasks)
    identityPath = $identityPath
    identityStartTimeUtc = if ($null -eq $identityStart) { $null } `
        else { $identityStart.ToString('o') }
    identityVerified = $identityVerified
    monitoringError = $monitoringError
    scriptErrorsDetected = $scriptErrors
    profileStarted = $profileStarted
    profileAccumulated = $profileAccumulated
    reportValid = $reportValid
    reportValidationError = $reportError
    valid = $valid
    profilerScope = [ordered]@{
        nativeCallsEnabled = $false
        lifetime = 'startup, import/setup, spawn, warmup, timed sample and teardown'
        comparison = 'diagnostic only; profiler overhead invalidates acceptance timing'
    }
    artifacts = [ordered]@{}
}
foreach ($item in @($reportPath, $stdoutPath, $stderrPath, $logPath)) {
    if (Test-Path -LiteralPath $item -PathType Leaf) {
        $processRecord.artifacts[[IO.Path]::GetFileName($item)] = [ordered]@{
            path = $item
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $item).Hash.ToLowerInvariant()
            bytes = (Get-Item -LiteralPath $item).Length
        }
    }
}
$processRecord | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $processPath

if (-not $valid) {
    throw "Script profile failed validation. See $processPath"
}
Write-Host "Godot script profile captured: $sessionRoot"
