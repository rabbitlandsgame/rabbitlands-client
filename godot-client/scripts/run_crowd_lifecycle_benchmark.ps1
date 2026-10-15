[CmdletBinding()]
param(
    [string]$GodotPath = "",
    [string]$ArtifactDirectory = "test-artifacts/native-crowd/lifecycle",
    [string]$InterferenceLabel = "shared host; interference not sampled",
    [ValidateRange(10, 900)]
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
(Get-Process -Id $PID).ProcessorAffinity = 15

$clientRoot = Split-Path -Parent $PSScriptRoot
$repositoryRoot = Split-Path -Parent $clientRoot
if ([string]::IsNullOrWhiteSpace($GodotPath)) {
    $GodotPath = Join-Path $clientRoot "Godot_v4.7.2-stable_win64.exe"
}
$GodotPath = (Resolve-Path -LiteralPath $GodotPath).Path
if ([IO.Path]::GetFileNameWithoutExtension($GodotPath) -like "*_console") {
    $GodotPath = Join-Path (Split-Path -Parent $GodotPath) `
        (([IO.Path]::GetFileNameWithoutExtension($GodotPath) -replace "_console$", "") + ".exe")
}
if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) {
    throw "The direct Godot executable was not found: $GodotPath"
}
$godotSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $GodotPath).Hash.ToLowerInvariant()

$artifactRoot = if ([IO.Path]::IsPathRooted($ArtifactDirectory)) {
    [IO.Path]::GetFullPath($ArtifactDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $clientRoot $ArtifactDirectory))
}
$repositoryPrefix = [IO.Path]::GetFullPath($repositoryRoot).TrimEnd("\") + "\"
if (-not ($artifactRoot + "\").StartsWith(
        $repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Artifacts must remain inside the worktree: $artifactRoot"
}
$runtimeRoot = Join-Path $artifactRoot "runtime"
foreach ($path in @($artifactRoot, (Join-Path $runtimeRoot "appdata"),
        (Join-Path $runtimeRoot "localappdata"), (Join-Path $runtimeRoot "profile"),
        (Join-Path $runtimeRoot "temp"))) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

$env:APPDATA = Join-Path $runtimeRoot "appdata"
$env:LOCALAPPDATA = Join-Path $runtimeRoot "localappdata"
$env:USERPROFILE = Join-Path $runtimeRoot "profile"
$env:TEMP = Join-Path $runtimeRoot "temp"
$env:TMP = $env:TEMP
$env:NUMBER_OF_PROCESSORS = "4"
$env:GODOT_THREADS_OVERRIDE = "4"
$env:OMP_NUM_THREADS = "4"
$env:OPENBLAS_NUM_THREADS = "4"
$env:MKL_NUM_THREADS = "4"
$env:NUMEXPR_NUM_THREADS = "4"
$env:ELORIA_NO_MAP_CACHE = "1"
$env:ELORIA_ARTIFACT_DIR = $artifactRoot
$env:ELORIA_CROWD_EXPECT_USER_ROOT = Join-Path $env:APPDATA "Godot/app_userdata/Eloria"
$env:ELORIA_CROWD_INTERFERENCE = $InterferenceLabel

$gitSafe = "safe.directory=$($repositoryRoot.Replace('\', '/'))"
$env:ELORIA_CROWD_COMMIT = (& git -c $gitSafe -C $repositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve the benchmark commit." }
$sourcePaths = @(
    "godot-client/src/network/protocol.gd",
    "godot-client/src/state/app_state.gd",
    "godot-client/src/state/actor_reducer.gd",
    "godot-client/native/native_crowd/src/native_crowd_reducer.cpp",
    "godot-client/native/native_crowd/src/native_crowd_reducer.h",
    "godot-client/tests/integration/crowd_lifecycle_benchmark.gd",
    "godot-client/scripts/run_crowd_lifecycle_benchmark.ps1"
)
$sourcePaths += (@(
    "godot-client/bin/native_crowd.gdextension",
    "godot-client/bin/windows/native_crowd.windows.template_release.x86_64.dll"
) | Where-Object { Test-Path -LiteralPath (Join-Path $repositoryRoot $_) })
$sourceHashes = [ordered]@{}
foreach ($relativePath in $sourcePaths) {
    $sourceHashes[$relativePath] = (Get-FileHash -Algorithm SHA256 -LiteralPath `
        (Join-Path $repositoryRoot $relativePath)).Hash.ToLowerInvariant()
}

function Get-TextSha256([string]$Text) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))
        return ([BitConverter]::ToString($digest) -replace "-", "").ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
}
$sourceHashText = ($sourceHashes.GetEnumerator() | ForEach-Object {
    "$($_.Key)=$($_.Value)"
}) -join "`n"
$env:ELORIA_CROWD_SOURCE_HASH = Get-TextSha256 $sourceHashText

function Quote-Argument([string]$Value) {
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '"', '\"') + '"'
}

function Get-CapturedProcessIdentity([Diagnostics.Process]$Process,
        [string]$ExpectedPath) {
    $lastFailure = "process identity was not available"
    for ($probe = 0; $probe -lt 20; $probe++) {
        if ($Process.HasExited) {
            throw "Captured process $($Process.Id) exited before identity verification."
        }
        try {
            $Process.Refresh()
            $actualPath = $Process.Path
            $actualStart = $Process.StartTime.ToUniversalTime()
            $actualMask = $Process.ProcessorAffinity.ToInt64()
            if ([string]::IsNullOrWhiteSpace($actualPath)) {
                $lastFailure = "captured process path was empty"
            } elseif (-not $actualPath.Equals(
                    $ExpectedPath, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Captured process path changed: $actualPath"
            } elseif ($actualMask -ne 15) {
                throw "Captured process inherited affinity $actualMask instead of 15."
            } else {
                return [ordered]@{
                    path = $actualPath
                    startTimeUtc = $actualStart.ToString("o")
                    affinityMask = $actualMask
                }
            }
        } catch [InvalidOperationException] {
            $lastFailure = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 50
    }
    throw "Could not verify captured process $($Process.Id): $lastFailure"
}

foreach ($backend in @("gdscript", "native")) {
    $env:ELORIA_NATIVE_CROWD = if ($backend -eq "native") { "1" } else { "0" }
    $env:ELORIA_BENCH_OUTPUT = "crowd-lifecycle-$backend.json"
    $stdoutPath = Join-Path $artifactRoot "$backend.stdout.log"
    $stderrPath = Join-Path $artifactRoot "$backend.stderr.log"
    $godotLogPath = Join-Path $artifactRoot "$backend.godot.log"
    $processPath = Join-Path $artifactRoot "$backend.process.json"
    $reportPath = Join-Path $artifactRoot $env:ELORIA_BENCH_OUTPUT
    $arguments = @("--headless", "--single-threaded-scene", "--audio-driver", "Dummy",
        "--path", $clientRoot, "--script",
        "res://tests/integration/crowd_lifecycle_benchmark.gd", "--log-file", $godotLogPath)
    $quotedArguments = @($arguments | ForEach-Object { Quote-Argument ([string]$_) })
    $inputs = [ordered]@{
        backend = $backend
        nativeFlag = $env:ELORIA_NATIVE_CROWD
        counts = @(100, 200, 300, 500)
        repeats = 9
        arguments = $arguments
        godotExecutable = $GodotPath
        godotExecutableSha256 = $godotSha256
        userDataRoot = $env:ELORIA_CROWD_EXPECT_USER_ROOT
        artifactRoot = $artifactRoot
        timeoutSeconds = $TimeoutSeconds
        interference = $InterferenceLabel
        commit = $env:ELORIA_CROWD_COMMIT
        sourceSha256 = $env:ELORIA_CROWD_SOURCE_HASH
    }
    $inputSha256 = Get-TextSha256 ($inputs | ConvertTo-Json -Depth 4 -Compress)
    Write-Host "Running lifecycle $backend serially (affinity=0xF)..."
    $process = Start-Process -FilePath $GodotPath -ArgumentList $quotedArguments `
        -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath
    try {
        $identity = Get-CapturedProcessIdentity $process $GodotPath
    } catch {
        if (-not $process.HasExited) {
            $process.Kill()
            $process.WaitForExit()
        }
        throw
    }
    $startTimeUtc = $identity.startTimeUtc
    $directExecutablePath = $identity.path
    $initialMask = $identity.affinityMask
    $observedMasks = @([ordered]@{
        timeUtc = (Get-Date).ToUniversalTime().ToString("o")
        affinityMask = $initialMask
    })
    $timedOut = $false
    $affinityVerified = $true
    $runErrors = @()
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while (-not $process.HasExited) {
        $process.Refresh()
        $mask = $process.ProcessorAffinity.ToInt64()
        if ($null -eq $initialMask) { $initialMask = $mask }
        $observedMasks += [ordered]@{
            timeUtc = (Get-Date).ToUniversalTime().ToString("o")
            affinityMask = $mask
        }
        if ($mask -ne 15) {
            $runErrors += "observed affinity $mask instead of 15"
            $process.Kill()
            break
        }
        $affinityVerified = $true
        if ((Get-Date) -ge $deadline) {
            $timedOut = $true
            $runErrors += "exceeded the $TimeoutSeconds second timeout"
            $process.Kill()
            break
        }
        Start-Sleep -Milliseconds 250
    }
    $process.WaitForExit()
    if (-not $affinityVerified) {
        $runErrors += "exited before affinity 0xF was verified"
    }
    if ($process.ExitCode -ne 0 -and -not $timedOut) {
        $runErrors += "exit code $($process.ExitCode)"
    }

    $scriptErrorFiles = @()
    foreach ($diagnosticPath in @($stdoutPath, $stderrPath, $godotLogPath)) {
        if ((Test-Path -LiteralPath $diagnosticPath) -and
                (Select-String -LiteralPath $diagnosticPath `
                    -Pattern "SCRIPT ERROR|Parse Error" -Quiet)) {
            $scriptErrorFiles += $diagnosticPath
        }
    }
    if ($scriptErrorFiles.Count -gt 0) { $runErrors += "script or parse error logged" }

    $report = $null
    $reportValid = $false
    $reportValidationError = ""
    try {
        $report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
        $expectedCounts = "100,200,300,500"
        $requiredFields = @("scope", "backend", "nativeActive", "repeats", "counts",
            "userDataDir", "commit", "sourceSha256", "sharedHostLabel", "godot",
            "unixTime", "results", "failureCount", "failures")
        $missingFields = @($requiredFields | Where-Object {
            $report.PSObject.Properties.Name -notcontains $_
        })
        $resultSchemaValid = @($report.results).Count -eq 4
        foreach ($result in @($report.results)) {
            $resultSchemaValid = $resultSchemaValid -and
                $result.actors -in @(100, 200, 300, 500) -and
                $result.dictionaryParityVerified -eq $true -and
                $result.decodeErrorCount -eq 0 -and
                @($result.add.samplesMs).Count -eq 9 -and
                @($result.remove.samplesMs).Count -eq 9 -and
                $result.packetShape -match "^\d+ add callbacks \+ 1 batched removal callback$"
        }
        $reportValid = $missingFields.Count -eq 0 -and $resultSchemaValid -and
            $report.failureCount -eq 0 -and $report.backend -eq $backend -and
            $report.nativeActive -eq ($backend -eq "native") -and
            $report.repeats -eq 9 -and (@($report.counts) -join ",") -eq $expectedCounts -and
            (@($report.results | ForEach-Object { $_.actors }) -join ",") -eq $expectedCounts -and
            $report.sharedHostLabel -eq $InterferenceLabel -and
            $report.userDataDir.Replace("\", "/").TrimEnd("/") -eq
                $env:ELORIA_CROWD_EXPECT_USER_ROOT.Replace("\", "/").TrimEnd("/") -and
            $report.commit -eq $env:ELORIA_CROWD_COMMIT -and
            $report.sourceSha256 -eq $env:ELORIA_CROWD_SOURCE_HASH
        if (-not $reportValid) { $reportValidationError = "schema or correctness mismatch" }
    } catch {
        $reportValidationError = $_.Exception.Message
    }
    if (-not $reportValid) { $runErrors += "invalid or failing report" }

    [ordered]@{
        schemaVersion = 1
        backend = $backend
        processId = $process.Id
        directExecutablePath = $directExecutablePath
        startTimeUtc = $startTimeUtc
        initialAffinityMask = $initialMask
        observedAffinityMasks = $observedMasks
        affinityVerified = $affinityVerified
        timedOut = $timedOut
        exitCode = $process.ExitCode
        scriptErrorsDetected = $scriptErrorFiles.Count -gt 0
        scriptErrorFiles = $scriptErrorFiles
        reportPath = $reportPath
        reportValid = $reportValid
        reportValidationError = $reportValidationError
        reportFailureCount = if ($null -ne $report) { $report.failureCount } else { $null }
        reportFailures = if ($null -ne $report) { @($report.failures) } else { @() }
        inputs = $inputs
        inputSha256 = $inputSha256
        sourceFilesSha256 = $sourceHashes
        sourceCompositeSha256 = $env:ELORIA_CROWD_SOURCE_HASH
        errors = $runErrors
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $processPath -Encoding utf8
    if ($runErrors.Count -gt 0) {
        throw "$backend failed: $($runErrors -join '; '); see $processPath"
    }
}

Write-Host "Lifecycle benchmark artifacts: $artifactRoot"
