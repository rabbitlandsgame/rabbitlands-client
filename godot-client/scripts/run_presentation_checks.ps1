[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GodotPath,
    [Parameter(Mandatory = $true)][string[]]$Scripts,
    [ValidateSet('gl_compatibility', 'forward_plus')]
    [string]$Renderer = 'gl_compatibility',
    [switch]$Headless,
    [string]$Label = 'presentation',
    [ValidateRange(1, 60)][int]$TimeoutMinutes = 10
)

# Run only while this task owns the shared four-core execution slot.
$ErrorActionPreference = 'Stop'
(Get-Process -Id $PID).ProcessorAffinity = 15
$clientRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $clientRoot
$launchPath = (Resolve-Path -LiteralPath $GodotPath).Path
if ([IO.Path]::GetFileNameWithoutExtension($launchPath) -like '*_console') {
    $launchPath = Join-Path (Split-Path -Parent $launchPath) (
        ([IO.Path]::GetFileNameWithoutExtension($launchPath) -replace '_console$', '') + '.exe')
    $launchPath = (Resolve-Path -LiteralPath $launchPath).Path
}
$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]+', '-').Trim('-')
if ([string]::IsNullOrWhiteSpace($safeLabel)) { throw 'Label must contain a filename character.' }
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$runRoot = Join-Path $clientRoot "test-artifacts/presentation-checks/$safeLabel-$Renderer-$stamp"
$userRoot = Join-Path $runRoot 'user-data'
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
$env:ELORIA_NATIVE_CROWD = '0'
New-Item -ItemType Directory -Force -Path $runRoot, $env:APPDATA,
    $env:LOCALAPPDATA, $env:USERPROFILE, $env:TEMP | Out-Null
$gitSafe = "safe.directory=$($repoRoot.Replace('\', '/'))"
$commit = (& git -c $gitSafe -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine source revision.' }
$sourceStatus = @(& git -c $gitSafe -C $repoRoot status --porcelain -- godot-client)
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine source status.' }
$executableHash = (Get-FileHash -LiteralPath $launchPath -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceHashes = [ordered]@{}
$sourcePaths = @('src/actors/cape_cloth.gd', 'src/actors/replicated_actor_3d.gd',
    'src/actors/combat_presentation_3d.gd', 'src/actors/ranger_bow_3d.gd',
    'src/world/world_effect_3d.gd',
    'src/world/spell_flight_3d.gd', 'src/world/combat_effect_mesh.gd',
    'src/world/spell_energy.gdshader', 'src/world/animation_gate.gd',
    'src/app/main.gd', 'project.godot', 'scripts/run_presentation_checks.ps1',
    'native/native_crowd/CMakeLists.txt', 'native/native_crowd/build_profile.json',
    'bin/native_crowd.gdextension',
    'bin/windows/native_crowd.windows.template_release.x86_64.dll')
$optionalSourcePaths = @(
    'src/actors/equipment_registry_snapshot_cache.gd',
    'src/actors/rebound_skin_pool.gd',
    'native/native_crowd/src/native_spell_flight_geometry.cpp',
    'native/native_crowd/src/native_spell_flight_geometry.h',
    'native/native_crowd/src/native_cape_constraint_kernel.cpp',
    'native/native_crowd/src/native_cape_constraint_kernel.h',
    'native/native_crowd/src/native_world_effect_geometry.cpp',
    'native/native_crowd/src/native_world_effect_geometry.h'
)
foreach ($relative in $optionalSourcePaths) {
    if (Test-Path -LiteralPath (Join-Path $clientRoot $relative)) {
        $sourcePaths += $relative
    }
}
foreach ($fixture in Get-ChildItem -LiteralPath (Join-Path $clientRoot 'tests/fixtures') -Filter '*baseline.gd') {
    $sourcePaths += 'tests/fixtures/' + $fixture.Name
}
foreach ($relative in $sourcePaths) {
    $sourceHashes[$relative] = (Get-FileHash -LiteralPath (Join-Path $clientRoot $relative) `
        -Algorithm SHA256).Hash.ToLowerInvariant()
}
$results = [System.Collections.Generic.List[object]]::new()

function Quote-Argument([string]$Value) {
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '"', '\"') + '"'
}

foreach ($script in $Scripts) {
    if ($script -notmatch '^res://tests/[A-Za-z0-9_./-]+\.gd$' -or $script.Contains('..')) {
        throw "Expected a test script resource path: $script"
    }
    $scriptPath = Join-Path $clientRoot $script.Substring(6)
    if (-not (Test-Path -LiteralPath $scriptPath)) { throw "Missing test: $script" }
    $name = ($script.Substring(6) -replace '/', '_') -replace '\.gd$', ''
    $artifactRoot = Join-Path $runRoot $name
    New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
    $env:ELORIA_ARTIFACT_DIR = $artifactRoot
    $stdout = Join-Path $artifactRoot 'stdout.log'
    $stderr = Join-Path $artifactRoot 'stderr.log'
    $log = Join-Path $artifactRoot 'godot.log'
    $arguments = @('--audio-driver', 'Dummy', '--rendering-method', $Renderer,
        '--path', $clientRoot, '--script', $script, '--log-file', $log)
    if ($Headless) { $arguments = @('--headless') + $arguments }
    $quoted = @($arguments | ForEach-Object { Quote-Argument $_ })
    Write-Host "Checking $script ($Renderer; headless=$($Headless.IsPresent); affinity=15)..."
    $process = Start-Process -FilePath $launchPath -ArgumentList $quoted -PassThru `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $expectedStart = $null
    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    $verified = $false
    $forced = $false
    $monitoringError = ''
    try {
        # Windows can briefly return an unavailable path/start time just after
        # launch. Acquire both through this captured Process, with bounded
        # retries and cleanup inside the same try as the execution monitor.
        $startupError = ''
        for ($probe = 0; $probe -lt 20 -and -not $verified; $probe++) {
            if ($process.HasExited) { break }
            try {
                $process.ProcessorAffinity = 15
                $process.Refresh()
                $actualPath = $process.Path
                $actualStart = $process.StartTime.ToUniversalTime()
                if ([string]::IsNullOrWhiteSpace($actualPath)) { throw 'Process path is not available yet.' }
                if (-not $actualPath.Equals($launchPath, [StringComparison]::OrdinalIgnoreCase) -or
                    $process.ProcessorAffinity.ToInt64() -ne 15) {
                    throw 'Captured test process identity or affinity mismatch.'
                }
                $expectedStart = $actualStart
                $verified = $true
            }
            catch { $startupError = $_.Exception.Message }
            if (-not $verified) { Start-Sleep -Milliseconds 50 }
        }
        if (-not $verified) {
            # A fast process may finish before identity acquisition. Its exit
            # and logs are retained, but it cannot count as attested evidence.
            throw "Could not attest captured test process: $startupError"
        }
        while (-not $process.HasExited) {
            try {
                $process.ProcessorAffinity = 15
                $process.Refresh()
                $actualPath = $process.Path
                if ($process.HasExited) { break }
                if (-not $actualPath -or -not $actualPath.Equals($launchPath, [StringComparison]::OrdinalIgnoreCase) -or
                    $process.StartTime.ToUniversalTime() -ne $expectedStart -or
                    $process.ProcessorAffinity.ToInt64() -ne 15) {
                    throw 'Captured test process identity or affinity mismatch.'
                }
                $verified = $true
            }
            catch { if (-not $process.HasExited) { throw } }
            if ((Get-Date) -ge $deadline) { throw "Test exceeded $TimeoutMinutes minutes." }
            Start-Sleep -Milliseconds 250
            $process.Refresh()
        }
        $process.WaitForExit()
    }
    catch {
        $monitoringError = $_.Exception.Message
        if (-not $process.HasExited) { $process.Kill($true); $forced = $true }
        $process.WaitForExit()
    }
    $scriptErrors = $false
    foreach ($path in @($stdout, $stderr, $log)) {
        if ((Test-Path -LiteralPath $path) -and
            (Select-String -LiteralPath $path -Pattern 'SCRIPT ERROR|Parse Error|SHADER ERROR' -Quiet)) {
            $scriptErrors = $true
        }
    }
    $record = [ordered]@{
        script = $script
        scriptSha256 = (Get-FileHash -LiteralPath $scriptPath -Algorithm SHA256).Hash.ToLowerInvariant()
        commit = $commit; sourceStatus = $sourceStatus; sourceFiles = $sourceHashes
        renderer = $Renderer; headless = $Headless.IsPresent
        nativePresentationEnvironment = [string]$env:ELORIA_NATIVE_PRESENTATION
        executable = $launchPath; executableSha256 = $executableHash; pid = $process.Id
        startTimeUtc = $(if ($null -ne $expectedStart) { $expectedStart.ToString('o') } else { $null })
        affinityMask = 15; requestedWorkers = 2; identityVerified = $verified
        userDataEnvironmentRoot = $userRoot; artifactDirectory = $artifactRoot
        exitCode = $process.ExitCode; forcedTermination = $forced
        monitoringError = $monitoringError; scriptErrorsDetected = $scriptErrors
        passed = ($verified -and $process.ExitCode -eq 0 -and -not $forced -and
            -not $scriptErrors -and [string]::IsNullOrEmpty($monitoringError))
    }
    $results.Add($record)
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $artifactRoot 'process.json')
    $results.ToArray() | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runRoot 'checks.json')
    Write-Host "  passed=$($record.passed); exit=$($record.exitCode); artifacts=$artifactRoot"
}
if (@($results | Where-Object { -not $_.passed }).Count -gt 0) {
    throw "Presentation checks failed; inspect $(Join-Path $runRoot 'checks.json')."
}
Write-Host "All presentation checks passed. Evidence: $(Join-Path $runRoot 'checks.json')"
