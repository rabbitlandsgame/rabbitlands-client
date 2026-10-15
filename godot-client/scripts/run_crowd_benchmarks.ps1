[CmdletBinding()]
param(
    [string]$GodotPath = "",
    [ValidateSet("primary", "matrix", "features", "stress", "all", "custom")]
    [string]$Profile = "primary",
    [ValidateSet("Both", "Headless", "Windowed")]
    [string]$Mode = "Both",
    [ValidateSet("gl_compatibility", "forward_plus")]
    [string[]]$Renderer = @("gl_compatibility"),
    [ValidateSet("Both", "GDScript", "Native")]
    [string]$NativeBackend = "Both",
    [ValidateSet("Off", "Cape", "Flight", "Both", "World", "All")]
    [string]$NativePresentation = "Off",
    [ValidateRange(1, 20)]
    [int]$Repeats = 3,
    [ValidateRange(1, 180)]
    [int]$TimeoutMinutes = 30,
    [ValidateRange(1, 300)]
    [int]$PostReportGraceSeconds = 5,
    [string]$Counts = "",
    [string]$Populations = "",
    [string]$Activities = "",
    [string]$Visibilities = "",
    [string]$Features = "",
    [string]$Networks = "",
    [string]$Map = "four_gates",
    [int]$SampleMilliseconds = 2500,
    [int]$WarmupMilliseconds = 1000,
    [int]$CadenceMilliseconds = 100,
    [switch]$Capture,
    [switch]$Attribution,
    [switch]$EngineProfileMarkers,
    [string]$Label = "",
    [string]$InterferenceLabel = "shared host; unrelated Godot jobs may be present"
)

$ErrorActionPreference = "Stop"
(Get-Process -Id $PID).ProcessorAffinity = 15

$clientRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $clientRoot
$runRoot = Join-Path $clientRoot "test-artifacts/native-crowd"
$userRoot = Join-Path $runRoot "user-data"
New-Item -ItemType Directory -Force -Path $runRoot, $userRoot | Out-Null

if ([string]::IsNullOrWhiteSpace($GodotPath)) {
    $godot = Get-Command godot4, godot, Godot -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $godot) {
        throw "Godot was not found. Pass -GodotPath with the executable path."
    }
    $GodotPath = $godot.Source
}
$GodotPath = (Resolve-Path -LiteralPath $GodotPath).Path
$launchPath = $GodotPath
if ([IO.Path]::GetFileNameWithoutExtension($GodotPath) -like '*_console') {
    $directPath = Join-Path (Split-Path -Parent $GodotPath) `
        (([IO.Path]::GetFileNameWithoutExtension($GodotPath) -replace '_console$', '') + '.exe')
    if (-not (Test-Path -LiteralPath $directPath)) {
        throw "The console Godot executable has no sibling direct executable at $directPath."
    }
    $launchPath = (Resolve-Path -LiteralPath $directPath).Path
}

# Keep mutable state in this worktree. The process mask is the enforceable CPU
# bound. Thread environment variables are requests recorded in the report;
# Godot does not expose a runtime worker-count query.
$env:APPDATA = Join-Path $userRoot "appdata"
$env:LOCALAPPDATA = Join-Path $userRoot "localappdata"
$env:USERPROFILE = Join-Path $userRoot "profile"
$env:TEMP = Join-Path $userRoot "temp"
$env:TMP = $env:TEMP
$env:NUMBER_OF_PROCESSORS = "4"
$env:GODOT_THREADS_OVERRIDE = "2"
$env:OMP_NUM_THREADS = "2"
$env:OPENBLAS_NUM_THREADS = "2"
$env:MKL_NUM_THREADS = "2"
$nativePresentationEnvironment = switch ($NativePresentation) {
    "Off" { "0" }
    "Cape" { "cape" }
    "Flight" { "flight" }
    "Both" { "both" }
    "World" { "world" }
    "All" { "all" }
}
# Set this unconditionally so a parent shell cannot contaminate comparisons.
$env:ELORIA_NATIVE_PRESENTATION = $nativePresentationEnvironment
New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:LOCALAPPDATA,
    $env:USERPROFILE, $env:TEMP | Out-Null

$gitSafe = "safe.directory=$($repositoryRoot.Replace('\', '/'))"
$commit = (& git -c $gitSafe -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Cannot determine the benchmark commit." }
& git -c $gitSafe -C $repositoryRoot diff --quiet --ignore-submodules --
$worktreeDirty = $LASTEXITCODE -ne 0
& git -c $gitSafe -C $repositoryRoot diff --cached --quiet --ignore-submodules --
$indexDirty = $LASTEXITCODE -ne 0
$sourceRelativePaths = @(
    "godot-client/tests/integration/crowd_benchmarks.gd",
    "godot-client/tests/integration/crowd_benchmark_main.gd",
    "godot-client/tests/integration/crowd_benchmark_main.tscn",
    "godot-client/tests/fixtures/crowd_skin_census.gd",
    "godot-client/scripts/run_crowd_benchmarks.ps1",
    "godot-client/project.godot",
    "godot-client/src/state/app_state.gd",
    "godot-client/src/app/main.gd",
    "godot-client/src/actors/replicated_actor_3d.gd",
    "godot-client/src/actors/ranger_bow_3d.gd",
    "godot-client/src/actors/cape_cloth.gd",
    "godot-client/src/actors/combat_presentation_3d.gd",
    "godot-client/src/world/world_effect_3d.gd",
    "godot-client/src/world/spell_flight_3d.gd",
    "godot-client/src/world/combat_effect_mesh.gd",
    "godot-client/src/world/spell_energy.gdshader",
    "godot-client/src/world/animation_gate.gd",
    "godot-client/native/native_crowd/src/native_crowd_reducer.cpp",
    "godot-client/native/native_crowd/src/native_crowd_reducer.h",
    "godot-client/native/native_crowd/src/register_types.cpp",
    "godot-client/native/native_crowd/src/register_types.h",
    "godot-client/native/native_crowd/CMakeLists.txt",
    "godot-client/native/native_crowd/build_profile.json",
    "godot-client/bin/native_crowd.gdextension",
    "godot-client/bin/windows/native_crowd.windows.template_release.x86_64.dll"
)
$optionalSourceRelativePaths = @(
    "godot-client/src/actors/equipment_registry_snapshot_cache.gd",
    "godot-client/src/actors/rebound_skin_pool.gd",
    "godot-client/native/native_crowd/src/native_cape_constraint_kernel.cpp",
    "godot-client/native/native_crowd/src/native_cape_constraint_kernel.h",
    "godot-client/native/native_crowd/src/native_spell_flight_geometry.cpp",
    "godot-client/native/native_crowd/src/native_spell_flight_geometry.h",
    "godot-client/native/native_crowd/src/native_world_effect_geometry.cpp",
    "godot-client/native/native_crowd/src/native_world_effect_geometry.h"
)
foreach ($relativePath in $optionalSourceRelativePaths) {
    if (Test-Path -LiteralPath (Join-Path $repositoryRoot $relativePath)) {
        $sourceRelativePaths += $relativePath
    }
}
$sourceStatus = @(& git -c $gitSafe -C $repositoryRoot status --porcelain -- `
    $sourceRelativePaths)
$dirty = $worktreeDirty -or $indexDirty -or $sourceStatus.Count -gt 0
$sourceHashes = [ordered]@{}
foreach ($relativePath in $sourceRelativePaths) {
    $absolutePath = Join-Path $repositoryRoot $relativePath
    if (Test-Path -LiteralPath $absolutePath) {
        $sourceHashes[$relativePath] = (Get-FileHash -Algorithm SHA256 `
            -LiteralPath $absolutePath).Hash.ToLowerInvariant()
    }
}
$sourceHashText = ($sourceHashes.GetEnumerator() | ForEach-Object {
    "$($_.Key)=$($_.Value)"
}) -join "`n"
$sourceHashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
try {
    $sourceHashBytes = [System.Text.Encoding]::UTF8.GetBytes($sourceHashText)
    $sourceHash = [Convert]::ToHexString(
        $sourceHashAlgorithm.ComputeHash($sourceHashBytes)).ToLowerInvariant()
}
finally {
    $sourceHashAlgorithm.Dispose()
}

$env:ELORIA_CROWD_PROFILE = $Profile
$env:ELORIA_CROWD_COUNTS = $Counts
$env:ELORIA_CROWD_POPULATIONS = $Populations
$env:ELORIA_CROWD_ACTIVITIES = $Activities
$env:ELORIA_CROWD_VISIBILITIES = $Visibilities
$env:ELORIA_CROWD_FEATURES = $Features
$env:ELORIA_CROWD_NETWORKS = $Networks
$env:ELORIA_CROWD_MAP = $Map
$env:ELORIA_CROWD_SAMPLE_MSEC = [string]$SampleMilliseconds
$env:ELORIA_CROWD_WARMUP_MSEC = [string]$WarmupMilliseconds
$env:ELORIA_CROWD_CADENCE_MSEC = [string]$CadenceMilliseconds
$env:ELORIA_CROWD_CAPTURE = if ($Capture) { "1" } else { "0" }
$env:ELORIA_CROWD_ATTRIBUTION = if ($Attribution) { "1" } else { "0" }
$env:ELORIA_CROWD_ENGINE_PROFILE_MARKERS = if ($EngineProfileMarkers) { "1" } else { "0" }
$env:ELORIA_CROWD_LABEL = $Label
$env:ELORIA_CROWD_INTERFERENCE = $InterferenceLabel
$env:ELORIA_CROWD_ARTIFACT_DIR = $runRoot
$env:ELORIA_CROWD_USER_ROOT = $userRoot
$env:ELORIA_CROWD_COMMIT = $commit
$env:ELORIA_CROWD_DIRTY = if ($dirty) { "1" } else { "0" }
$env:ELORIA_CROWD_SOURCE_HASH = $sourceHash

$modes = switch ($Mode) {
    "Headless" { @("headless") }
    "Windowed" { @("windowed") }
    default { @("headless", "windowed") }
}
$backends = switch ($NativeBackend) {
    "GDScript" { @("gdscript") }
    "Native" { @("native") }
    default { @("gdscript", "native") }
}
$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]+', '-').Trim('-')
if ([string]::IsNullOrWhiteSpace($safeLabel)) { $safeLabel = "unlabelled" }

function Set-And-VerifyAffinity([System.Diagnostics.Process]$Process,
        [hashtable]$Observed, [string]$ExpectedPath,
        [datetime]$ExpectedStartTime) {
    try {
        if ($Process.HasExited) { return }
        $Process.ProcessorAffinity = 15
        $Process.Refresh()
        $actual = $Process.ProcessorAffinity.ToInt64()
        $actualPath = ""
        for ($identityProbe = 0; $identityProbe -lt 20; $identityProbe++) {
            $Process.Refresh()
            $actualPath = $Process.Path
            if (-not [string]::IsNullOrWhiteSpace($actualPath)) { break }
            if ($Process.HasExited) { break }
            Start-Sleep -Milliseconds 50
        }
        if ([string]::IsNullOrWhiteSpace($actualPath)) {
            throw "Captured process path was unavailable for PID $($Process.Id)."
        }
        $actualStartTime = $Process.StartTime.ToUniversalTime()
        $Observed[[string]$Process.Id] = @{
            name = $Process.ProcessName
            path = $actualPath
            startTimeUtc = $actualStartTime.ToString('o')
            affinityMask = $actual
        }
        if (-not $actualPath.Equals($ExpectedPath,
                [StringComparison]::OrdinalIgnoreCase) -or
                $actualStartTime -ne $ExpectedStartTime) {
            throw "Captured process identity changed for PID $($Process.Id)."
        }
        if ($actual -ne 15) {
            throw "Process $($Process.Id) has affinity $actual instead of 15."
        }
    }
    catch {
        # A normal exit can race any property read. Suppress only that race;
        # an inspection error while the captured process is alive must fail.
        if (-not $Process.HasExited) { throw }
    }
}

function Get-ProcessMemorySample([System.Diagnostics.Process]$Process) {
    $timestamp = (Get-Date).ToUniversalTime().ToString('o')
    try {
        if ($Process.HasExited) { throw 'captured process exited before memory sampling' }
        $Process.Refresh()
        return [ordered]@{
            timestampUtc = $timestamp
            available = $true
            error = $null
            workingSetBytes = [long]$Process.WorkingSet64
            privateMemoryBytes = [long]$Process.PrivateMemorySize64
            pagedMemoryBytes = [long]$Process.PagedMemorySize64
            peakWorkingSetBytes = [long]$Process.PeakWorkingSet64
            peakPagedMemoryBytes = [long]$Process.PeakPagedMemorySize64
        }
    }
    catch {
        return [ordered]@{
            timestampUtc = $timestamp
            available = $false
            error = $_.Exception.Message
            workingSetBytes = $null
            privateMemoryBytes = $null
            pagedMemoryBytes = $null
            peakWorkingSetBytes = $null
            peakPagedMemoryBytes = $null
        }
    }
}

function Get-ByteDistribution([object[]]$Values) {
    $usable = @($Values | Where-Object { $null -ne $_ } |
        ForEach-Object { [long]$_ } | Sort-Object)
    if ($usable.Count -eq 0) { return $null }
    $middle = [int][Math]::Floor($usable.Count / 2.0)
    $median = if ($usable.Count % 2 -eq 1) {
        [long]$usable[$middle]
    }
    else {
        [long][Math]::Round(
            ([decimal]$usable[$middle - 1] + [decimal]$usable[$middle]) / 2,
            [MidpointRounding]::AwayFromZero)
    }
    return [ordered]@{
        medianBytes = $median
        maximumBytes = [long]$usable[-1]
    }
}

function Get-ProcessMemorySummary([Collections.Generic.List[object]]$Samples) {
    $available = @($Samples | Where-Object { $_.available })
    return [ordered]@{
        scope = ('periodic operating-system counters across the full captured process ' +
            'lifetime, including startup and lifecycle; not exact steady benchmark frames')
        sampleInterval = 'approximately one second while the captured process is alive'
        sampleCount = $Samples.Count
        availableSampleCount = $available.Count
        unavailableSampleCount = $Samples.Count - $available.Count
        workingSetBytes = Get-ByteDistribution @($available | ForEach-Object {
            $_.workingSetBytes })
        privateMemoryBytes = Get-ByteDistribution @($available | ForEach-Object {
            $_.privateMemoryBytes })
        pagedMemoryBytes = Get-ByteDistribution @($available | ForEach-Object {
            $_.pagedMemoryBytes })
        peakWorkingSetBytes = Get-ByteDistribution @($available | ForEach-Object {
            $_.peakWorkingSetBytes })
        peakPagedMemoryBytes = Get-ByteDistribution @($available | ForEach-Object {
            $_.peakPagedMemoryBytes })
        privatePeakBytes = $null
        privatePeakCaveat = ('Windows Process exposes sampled PrivateMemorySize64 here, ' +
            'not a private-memory peak counter; no peak is inferred')
        samples = @($Samples)
    }
}

function Quote-ProcessArgument([string]$Value) {
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Assert-BenchmarkReport([string]$JsonPath, [string]$ExpectedProfile,
        [bool]$ExpectedAttribution, [string]$ExpectedNativePresentation,
        [bool]$ExpectedEngineProfileMarkers, [int]$ExpectedProcessId) {
    if (-not (Test-Path -LiteralPath $JsonPath)) {
        throw "Benchmark exited without writing $JsonPath."
    }
    try { $result = Get-Content -Raw -LiteralPath $JsonPath | ConvertFrom-Json }
    catch { throw "Benchmark artifact is not valid JSON: $JsonPath`n$_" }
    if ($result.schemaVersion -ne 1 -or $result.profile -ne $ExpectedProfile -or
            $result.failureCount -ne 0) {
        throw "Benchmark artifact reports an invalid schema, profile, or failure count: $JsonPath"
    }
    $cells = @($result.cells)
    if ($cells.Count -eq 0 -or $cells.Count -ne @($result.plannedCells).Count) {
        throw "Benchmark artifact has incomplete cell coverage: $JsonPath"
    }
    foreach ($cell in $cells) {
        if ($cell.fixture.before.total -ne $cell.count -or
                $cell.fixture.after.total -ne $cell.count) {
            throw "Benchmark artifact has an actor-count mismatch: $JsonPath"
        }
    }
    if ($ExpectedProfile -eq "primary" -and ($cells.Count -ne 1 -or
            $cells[0].count -ne 300 -or $cells[0].plannedActive -ne 100 -or
            $cells[0].fixture.before.frustumAndDrawVisible -ne 150)) {
        throw "Primary acceptance invariants are absent: $JsonPath"
    }
    $expectedPresentationMode = $ExpectedNativePresentation.ToLowerInvariant()
    $expectedPresentationEnvironment = switch ($ExpectedNativePresentation) {
        "Off" { "0" }
        "Cape" { "cape" }
        "Flight" { "flight" }
        "Both" { "both" }
        "World" { "world" }
        "All" { "all" }
    }
    $presentation = $result.nativePresentation
    $actualPresentation = $presentation.actual
    if ($null -eq $presentation -or $presentation.requestedMode -ne $expectedPresentationMode -or
            $presentation.environmentValue -ne $expectedPresentationEnvironment -or
            -not [bool]$presentation.reducerIndependent -or
            -not [bool]$actualPresentation.matchedRequest -or
            -not [bool]$actualPresentation.capeMatchedRequest -or
            -not [bool]$actualPresentation.flightMatchedRequest -or
            -not [bool]$actualPresentation.worldMatchedRequest) {
        throw "Native presentation request/activity attestation is invalid: $JsonPath"
    }
    $wantsCape = $ExpectedNativePresentation -in @("Cape", "Both", "All")
    $wantsFlight = $ExpectedNativePresentation -in @("Flight", "Both", "All")
    $wantsWorld = $ExpectedNativePresentation -in @("World", "All")
    if ($wantsCape) {
        if ([int]$actualPresentation.capeActiveInstancesMaximum -le 0 -or
                [int]$actualPresentation.capeNativeBackendInstancesMaximum -le 0 -or
                [int]$actualPresentation.capeNativeCalls -le 0 -or
                [int]$actualPresentation.capeFallbackCalls -ne 0) {
            throw "Requested native cape component was inactive or fell back: $JsonPath"
        }
    }
    elseif ([int]$actualPresentation.capeActiveInstancesMaximum -ne 0 -or
            [int]$actualPresentation.capeNativeBackendInstancesMaximum -ne 0 -or
            [int]$actualPresentation.capeNativeCalls -ne 0 -or
            [int]$actualPresentation.capeFallbackCalls -ne 0) {
        throw "Unrequested native cape component was active: $JsonPath"
    }
    if ($wantsFlight) {
        if ([int]$actualPresentation.flightActiveInstancesMaximum -le 0 -or
                [int]$actualPresentation.flightBuildAttempts -le 0 -or
                [int]$actualPresentation.flightBuildSuccesses -ne
                    [int]$actualPresentation.flightBuildAttempts -or
                [int]$actualPresentation.flightBuildFallbacks -ne 0) {
            throw "Requested native flight component was inactive or fell back: $JsonPath"
        }
    }
    elseif ([int]$actualPresentation.flightActiveInstancesMaximum -ne 0 -or
            [int]$actualPresentation.flightBuildAttempts -ne 0 -or
            [int]$actualPresentation.flightBuildSuccesses -ne 0 -or
            [int]$actualPresentation.flightBuildFallbacks -ne 0) {
        throw "Unrequested native flight component was active: $JsonPath"
    }
    if ($wantsWorld) {
        if (-not [bool]$actualPresentation.worldStatsSupported -or
                [int]$actualPresentation.worldActiveInstancesMaximum -le 0 -or
                [int]$actualPresentation.worldBuildAttempts -le 0 -or
                [int]$actualPresentation.worldBuildSuccesses -ne
                    [int]$actualPresentation.worldBuildAttempts -or
                [int]$actualPresentation.worldBuildFallbacks -ne 0) {
            throw "Requested native world component was inactive or fell back: $JsonPath"
        }
    }
    elseif ([int]$actualPresentation.worldActiveInstancesMaximum -ne 0 -or
            [int]$actualPresentation.worldBuildAttempts -ne 0 -or
            [int]$actualPresentation.worldBuildSuccesses -ne 0 -or
            [int]$actualPresentation.worldBuildFallbacks -ne 0) {
        throw "Unrequested native world component was active: $JsonPath"
    }
    $solverCells = @($cells | Where-Object { $_.features -eq "cape_solver_off" })
    $hasSolverDiagnostic = $solverCells.Count -gt 0
    if ($result.measurement.engineProfileMarkersEnabled -isnot [bool] -or
            $result.measurement.engineProfileMarkersEnabled -ne $ExpectedEngineProfileMarkers) {
        throw "Engine profile marker mode does not match the requested mode: $JsonPath"
    }
    $hasDiagnosticIntervention = $hasSolverDiagnostic -or $ExpectedEngineProfileMarkers
    $acceptance = $result.measurement.acceptance
    if ($null -eq $acceptance -or [string]::IsNullOrWhiteSpace([string]$acceptance.reason) -or
            [bool]$acceptance.eligible -eq [bool]$acceptance.diagnosticOnly) {
        throw "Benchmark acceptance eligibility metadata is absent or inconsistent: $JsonPath"
    }
    if ($hasDiagnosticIntervention -and ([bool]$acceptance.eligible -or
            -not [bool]$acceptance.diagnosticOnly)) {
        throw "Instrumented benchmark is not marked diagnostic-only: $JsonPath"
    }
    if (-not $hasDiagnosticIntervention -and (-not [bool]$acceptance.eligible -or
            [bool]$acceptance.diagnosticOnly)) {
        throw "Production benchmark is unexpectedly marked diagnostic-only: $JsonPath"
    }
    foreach ($cell in $cells) {
        $window = $cell.sample.engineProfileWindow
        if ($null -eq $window -or $window.enabled -isnot [bool] -or
                $window.enabled -ne $ExpectedEngineProfileMarkers) {
            throw "Cell engine profile mode is missing or inconsistent: $JsonPath"
        }
        if ($ExpectedEngineProfileMarkers) {
            $begin = $window.start
            $end = $window.end
            if ($begin.event -ne 'sample_start' -or $end.event -ne 'sample_end' -or
                    $begin.cell -ne $cell.id -or $end.cell -ne $cell.id -or
                    [long]$begin.processId -ne $ExpectedProcessId -or
                    $begin.processId -ne $end.processId -or
                    [long]$end.engineMicroseconds -le [long]$begin.engineMicroseconds -or
                    ([long]$end.processFrame - [long]$begin.processFrame) -ne [long]$cell.sample.frames -or
                    [Math]::Abs(([double]$end.unixMicroseconds - [double]$begin.unixMicroseconds) -
                        ([double]$end.engineMicroseconds - [double]$begin.engineMicroseconds)) -gt 100000) {
                throw "Engine profile window has invalid boundaries or a system clock discontinuity: $JsonPath"
            }
        }
    }
    if ($hasSolverDiagnostic) {
        foreach ($cell in $cells) {
            if (-not [bool]$cell.featureAttestation.diagnosticOnly -or
                    [bool]$cell.featureAttestation.acceptanceTimingComparable -or
                    -not [bool]$cell.featureAttestation.perFrameActivityCensusEnabled -or
                    -not [bool]$cell.sample.capeSolverProbe.enabled -or
                    [bool]$cell.sample.capeSolverProbe.acceptanceTimingComparable) {
                throw "Cape diagnostic cell lacks non-acceptance probe attestation: $JsonPath"
            }
            $activity = @($cell.sample.raw.capeSolverActivePerFrame)
            if ($activity.Count -ne [int]$cell.sample.frames -or $activity.Count -eq 0) {
                throw "Cape activity census has incomplete frame coverage: $JsonPath"
            }
        }
        foreach ($cell in $solverCells) {
            $before = $cell.featureAttestation.beforeSample
            $disabled = $cell.featureAttestation.afterDisable
            $after = $cell.featureAttestation.afterSample
            if (-not [bool]$cell.featureAttestation.featureUnderTest -or
                    $cell.count -ne 300 -or $cell.population -ne "mixed" -or
                    $cell.activity -ne "third_active" -or $cell.visibility -ne "half300" -or
                    $cell.network -ne "normal_burst" -or
                    [int]$before.capeEquipmentActors -ne 150 -or
                    [int]$before.modifierNodes -lt 150 -or
                    [int]$before.wornFlags -ne 150 -or
                    [int]$before.activeModifiers -le 0 -or
                    [int]$before.settledModifiers -lt [int]$before.activeModifiers -or
                    [int]$before.capeMeshInstances -lt 150 -or
                    [int]$disabled.activeModifiers -ne 0 -or [int]$disabled.wornFlags -ne 0 -or
                    [int]$after.activeModifiers -ne 0 -or [int]$after.wornFlags -ne 0) {
                throw "cape_solver_off fixture or modifier-state attestation is invalid: $JsonPath"
            }
            foreach ($field in @("capeEquipmentActors", "capeEquipmentNodes",
                    "capeMeshInstances", "appliedEquipmentVisuals")) {
                if ([int]$before.$field -ne [int]$disabled.$field -or
                        [int]$before.$field -ne [int]$after.$field) {
                    throw "cape_solver_off changed retained cape/equipment census $field`: $JsonPath"
                }
            }
            if (@($cell.sample.raw.capeSolverActivePerFrame | Where-Object {
                    [int]$_ -ne 0 }).Count -gt 0) {
                throw "cape_solver_off was reactivated during sampled frames: $JsonPath"
            }
        }
    }
    $actualAttribution = [bool]$result.measurement.attribution.enabled
    if ($actualAttribution -ne $ExpectedAttribution -or
            [bool]$result.measurement.attribution.acceptanceTimingComparable -eq $ExpectedAttribution) {
        throw "Benchmark attribution metadata does not match the requested diagnostic mode: $JsonPath"
    }
    if ($ExpectedAttribution) {
        $requiredRaw = @(
            "processDeltaMilliseconds", "mainProcessInclusiveMilliseconds",
            "mainProcessCallsPerFrame",
            "combatPoseFromSkeletonMilliseconds", "skeletonUpdatesPerFrame",
            "uniqueSkeletonsUpdatedPerFrame", "maximumSkeletonUpdatesPerActor",
            "mirroredEffectSetterMissilePerFrame",
            "mirroredEffectSetterGroundMissilePerFrame",
            "mirroredEffectSetterSpecialPerFrame",
            "mirroredEffectSetterAnimationPerFrame", "mirroredSpellPalettePerFrame",
            "mirroredSpellPowerPerFrame"
        )
        $countMetrics = @(
            "mainProcessCallsPerFrame", "skeletonUpdatesPerFrame",
            "uniqueSkeletonsUpdatedPerFrame", "maximumSkeletonUpdatesPerActor",
            "mirroredEffectSetterMissilePerFrame",
            "mirroredEffectSetterGroundMissilePerFrame",
            "mirroredEffectSetterSpecialPerFrame",
            "mirroredEffectSetterAnimationPerFrame", "mirroredSpellPalettePerFrame",
            "mirroredSpellPowerPerFrame"
        )
        foreach ($cell in $cells) {
            if (-not [bool]$cell.sample.attribution.enabled -or
                    [bool]$cell.sample.attribution.acceptanceTimingComparable -or
                    -not [bool]$cell.sample.attribution.attachment.ok) {
                throw "Cell attribution attestation is absent or acceptance-comparable: $JsonPath"
            }
            $expectedSamples = @($cell.sample.raw.wallMilliseconds).Count
            foreach ($metric in $requiredRaw) {
                $values = @($cell.sample.raw.$metric)
                if ($values.Count -ne $expectedSamples -or $values.Count -eq 0) {
                    throw "Attribution metric $metric has incomplete raw coverage: $JsonPath"
                }
                foreach ($value in $values) {
                    if ($null -eq $value -or -not ($value -is [ValueType])) {
                        throw "Attribution metric $metric contains a non-number: $JsonPath"
                    }
                    $number = [double]$value
                    if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) {
                        throw "Attribution metric $metric contains a non-finite number: $JsonPath"
                    }
                    if ($metric -in $countMetrics -and
                            ($number -lt 0 -or $number -ne [math]::Truncate($number))) {
                        throw "Attribution count $metric is not a nonnegative integer: $JsonPath"
                    }
                }
                if ($null -eq $cell.sample.summary.$metric) {
                    throw "Attribution metric $metric has no reported distribution: $JsonPath"
                }
            }
            for ($index = 0; $index -lt $expectedSamples; $index++) {
                $total = [int]$cell.sample.raw.skeletonUpdatesPerFrame[$index]
                $unique = [int]$cell.sample.raw.uniqueSkeletonsUpdatedPerFrame[$index]
                $maximum = [int]$cell.sample.raw.maximumSkeletonUpdatesPerActor[$index]
                if ($unique -gt $total -or $maximum -gt $total -or
                        ($total -eq 0 -and ($unique -ne 0 -or $maximum -ne 0)) -or
                        ($total -gt 0 -and ($unique -eq 0 -or $maximum -eq 0))) {
                    throw "Skeleton attribution counts are internally inconsistent: $JsonPath"
                }
            }
            if (@($cell.sample.raw.mainProcessCallsPerFrame | Where-Object {
                    [int]$_ -ne 1 }).Count -gt 0) {
                throw "Attribution did not capture exactly one Main process call per frame: $JsonPath"
            }
        }
    }
}

foreach ($trial in 1..$Repeats) {
    $trialBackends = @($backends)
    if ($trialBackends.Count -eq 2 -and $trial % 2 -eq 0) {
        [array]::Reverse($trialBackends)
    }
    foreach ($renderingMethod in $Renderer) {
        $env:ELORIA_CROWD_RENDERER = $renderingMethod
        foreach ($run in $modes) {
            foreach ($backend in $trialBackends) {
                $env:ELORIA_NATIVE_CROWD = if ($backend -eq "native") { "1" } else { "0" }
                $env:ELORIA_CROWD_NATIVE_BACKEND = $backend
                $env:ELORIA_NATIVE_PRESENTATION = $nativePresentationEnvironment
                $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssfffZ")
                $runId = "$safeLabel-$Profile-$backend-$renderingMethod-$run-trial$trial-$timestamp"
                $env:ELORIA_CROWD_TRIAL = [string]$trial
                $env:ELORIA_CROWD_RUN_ID = $runId
                $env:ELORIA_CROWD_OUTPUT = "$runId.json"
                $env:ELORIA_CROWD_PROCESS_METADATA = (@{
                    runnerPid = $PID
                    affinityMask = 15
                    logicalProcessors = @(0, 1, 2, 3)
                    requestedWorkerThreads = 2
                    requestedNativePresentation = $NativePresentation
                    nativePresentationEnvironment = $nativePresentationEnvironment
                } | ConvertTo-Json -Compress)
                $logPath = Join-Path $runRoot "$runId.log"
                $stdoutPath = Join-Path $runRoot "$runId.stdout.log"
                $stderrPath = Join-Path $runRoot "$runId.stderr.log"
                $processPath = Join-Path $runRoot "$runId.process.json"
				$jsonPath = Join-Path $runRoot "$runId.json"
                $arguments = @(
                    "--audio-driver", "Dummy",
                    "--rendering-method", $renderingMethod,
                    "--path", $clientRoot,
                    "--script", "res://tests/integration/crowd_benchmarks.gd",
                    "--log-file", $logPath
                )
                if ($run -eq "headless") { $arguments = @("--headless") + $arguments }
				$quotedArguments = @($arguments | ForEach-Object {
					Quote-ProcessArgument ([string]$_
				)})

                Write-Host "Running $runId serially (affinity=0xF; worker request=2)..."
                $observed = @{}
                $memorySamples = [Collections.Generic.List[object]]::new()
                $process = Start-Process -FilePath $launchPath -ArgumentList $quotedArguments `
					-PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutPath `
					-RedirectStandardError $stderrPath
				$expectedProcessPath = $launchPath
				$expectedProcessStart = $process.StartTime.ToUniversalTime()
				$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
				$artifactSeenAt = $null
				$postReportStop = $false
				$identityVerified = $false
				try {
                    Set-And-VerifyAffinity $process $observed $expectedProcessPath `
                        $expectedProcessStart
                    $identityVerified = $observed.ContainsKey([string]$process.Id)
                    do {
						$process.Refresh()
						$live = if ($process.HasExited) { 0 } else { 1 }
                        if ($live -gt 0) {
                            Set-And-VerifyAffinity $process $observed $expectedProcessPath `
                                $expectedProcessStart
                            $memorySamples.Add((Get-ProcessMemorySample $process))
						}
						if ((Get-Date) -ge $deadline) {
							if (-not $process.HasExited) { $process.Kill($true) }
							throw "$runId exceeded the $TimeoutMinutes minute timeout."
						}
						if (Test-Path -LiteralPath $jsonPath) {
							if ($null -eq $artifactSeenAt) { $artifactSeenAt = Get-Date }
							elseif (((Get-Date) - $artifactSeenAt).TotalSeconds -ge $PostReportGraceSeconds -and $live -gt 0) {
								$process.Kill($true)
								$postReportStop = $true
							}
						}
						if ($live -gt 0) { Start-Sleep -Seconds 1 }
					} while ($live -gt 0)
					$process.WaitForExit()
				}
				catch {
					$monitoringError = $_.Exception.Message
					$forcedTermination = $false
					try {
						if (-not $process.HasExited) {
							$process.Kill($true)
							$forcedTermination = $true
						}
						$process.WaitForExit()
					}
					catch {}
					$failedExitCode = if ($process.HasExited) { $process.ExitCode } else { -1 }
					@{
						runId = $runId; rootPid = $process.Id; exitCode = $failedExitCode
						affinityMask = 15; allObservedProcessesVerified = $false
						observedProcesses = $observed; commit = $commit; dirty = $dirty
						sourceHash = $sourceHash; sourceFiles = $sourceHashes
						requestedGodotPath = $GodotPath; launchExecutablePath = $launchPath
						monitoring = "captured direct Godot Process object only; monitoring failed"
						monitoringError = $monitoringError; forcedTermination = $forcedTermination
						postReportStop = $false; abortedAfterReport = $false; cleanExit = $false
						postReportGraceSeconds = $PostReportGraceSeconds
						scriptErrorsDetected = $false; schemaValid = $false; reportValid = $false
						reportValidationError = "monitoring failed before report validation"
						renderer = $renderingMethod; mode = $run; backend = $backend; trial = $trial
						attributionEnabled = $Attribution.IsPresent
                        engineProfileMarkersEnabled = $EngineProfileMarkers.IsPresent
                        nativePresentationRequested = $NativePresentation
                        nativePresentationEnvironment = $nativePresentationEnvironment
                        processMemory = Get-ProcessMemorySummary $memorySamples
                    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $processPath
					throw
				}
				$scriptErrorsDetected = $false
				foreach ($diagnosticPath in @($logPath, $stdoutPath, $stderrPath)) {
					if ((Test-Path -LiteralPath $diagnosticPath) -and
							(Select-String -Path $diagnosticPath -Pattern 'SCRIPT ERROR|Parse Error' -Quiet)) {
						$scriptErrorsDetected = $true
					}
				}
				$schemaValid = $false
				$reportValidationError = ""
				try {
					Assert-BenchmarkReport $jsonPath $Profile $Attribution.IsPresent `
						$NativePresentation $EngineProfileMarkers.IsPresent $process.Id
					$schemaValid = $true
				}
				catch {
					$reportValidationError = $_.Exception.Message
				}
				$cleanExit = -not $postReportStop -and $process.ExitCode -eq 0
				$reportValid = $identityVerified -and $schemaValid -and -not $scriptErrorsDetected -and $cleanExit
				if (-not $identityVerified) {
					$reportValidationError = "Process exited before executable identity and affinity were verified."
				}
                @{
                    runId = $runId
                    rootPid = $process.Id
                    exitCode = $process.ExitCode
                    affinityMask = 15
                    allObservedProcessesVerified = $identityVerified
                    observedProcesses = $observed
                    commit = $commit
                    dirty = $dirty
					sourceHash = $sourceHash
					sourceFiles = $sourceHashes
					requestedGodotPath = $GodotPath
					launchExecutablePath = $launchPath
					monitoring = "captured direct Godot Process object only; exact path/start time and mask checked every second"
					monitoringError = ""
					forcedTermination = $postReportStop
					postReportStop = $postReportStop
					abortedAfterReport = $postReportStop
					postReportGraceSeconds = $PostReportGraceSeconds
					cleanExit = $cleanExit
					scriptErrorsDetected = $scriptErrorsDetected
					schemaValid = $schemaValid
					reportValid = $reportValid
					reportValidationError = $reportValidationError
                    renderer = $renderingMethod
                    mode = $run
                    backend = $backend
                    trial = $trial
					attributionEnabled = $Attribution.IsPresent
                    engineProfileMarkersEnabled = $EngineProfileMarkers.IsPresent
                    nativePresentationRequested = $NativePresentation
                    nativePresentationEnvironment = $nativePresentationEnvironment
                    processMemory = Get-ProcessMemorySummary $memorySamples
                } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $processPath
				if ($postReportStop) {
					throw "$runId wrote a report but required forced post-report termination. See $logPath"
				}
                if ($process.ExitCode -ne 0) {
                    throw "$runId failed with exit code $($process.ExitCode). See $logPath"
                }
				if ($scriptErrorsDetected) {
					throw "$runId logged a script or parse error. See $logPath"
				}
				if (-not $reportValid) {
					throw $reportValidationError
				}
            }
        }
    }
}

Write-Host "Crowd benchmark artifacts: $runRoot"
