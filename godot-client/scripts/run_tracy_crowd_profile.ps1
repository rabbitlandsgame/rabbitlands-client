[CmdletBinding()]
param(
    [string]$GodotPath = "",
    [string]$ArtifactRoot = "",
    [string]$PythonPath = "",
    [ValidateSet("Headless", "Windowed")]
    [string]$Mode = "Headless",
    [ValidateSet("gl_compatibility", "forward_plus")]
    [string]$Renderer = "gl_compatibility",
    [ValidateSet("GDScript", "Native")]
    [string]$NativeBackend = "GDScript",
    [ValidateSet("Off", "Cape", "Flight", "Both", "World", "All")]
    [string]$NativePresentation = "All",
    [int]$SampleMilliseconds = 10000,
    [int]$WarmupMilliseconds = 2000,
    [ValidateRange(10, 285)]
    [int]$CaptureSeconds = 45,
    [bool]$RunDisconnectedBaseline = $true,
    [string]$Label = "engine-tracy-production-schedule"
)

$ErrorActionPreference = "Stop"
(Get-Process -Id $PID).ProcessorAffinity = 15

$clientRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ArtifactRoot)) {
    $ArtifactRoot = Join-Path $clientRoot "test-artifacts/engine-profile"
}
$ArtifactRoot = (Resolve-Path -LiteralPath $ArtifactRoot).Path
if ([string]::IsNullOrWhiteSpace($GodotPath)) {
    $GodotPath = Join-Path $ArtifactRoot `
        "godot-4.7.2-stable/bin/godot.windows.template_release.x86_64.exe"
}
$GodotPath = (Resolve-Path -LiteralPath $GodotPath).Path
$runner = Join-Path $PSScriptRoot "run_crowd_benchmarks.ps1"
$tracyBin = Join-Path $ArtifactRoot "tracy-windows-0.13.0"
$captureExe = (Resolve-Path -LiteralPath (Join-Path $tracyBin "tracy-capture.exe")).Path
$csvExe = (Resolve-Path -LiteralPath (Join-Path $tracyBin "tracy-csvexport.exe")).Path
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (Get-Command python -ErrorAction Stop).Source
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$analyzer = Join-Path $PSScriptRoot "analyze_tracy_crowd_profile.py"
$runRoot = Join-Path $clientRoot "test-artifacts/native-crowd"
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
$session = Join-Path $ArtifactRoot "captures/$stamp-$($Mode.ToLowerInvariant())-$Renderer"
New-Item -ItemType Directory -Force -Path $session | Out-Null
$postReportGraceSeconds = [Math]::Min(300, [Math]::Max(60, $CaptureSeconds + 15))

function Start-FileProcess {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$StdoutPath,
        [Parameter(Mandatory)] [string]$StderrPath,
        [bool]$RequireLiveIdentity = $true
    )

    $resolvedPath = (Resolve-Path -LiteralPath $FilePath).Path
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $resolvedPath
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) {
        [void]$info.ArgumentList.Add([string]$argument)
    }
    $stdout = [System.IO.File]::Open(
        $StdoutPath, [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    $stderr = [System.IO.File]::Open(
        $StderrPath, [System.IO.FileMode]::Create,
        [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    $started = $false
    $stdoutTask = $null
    $stderrTask = $null
    try {
        if (-not $process.Start()) {
            throw "Failed to start $resolvedPath."
        }
        $started = $true
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderr)
        if (-not $process.HasExited) {
            $process.ProcessorAffinity = [IntPtr]15
        }
        $startedUtc = $process.StartTime.ToUniversalTime()
        $process.Refresh()
        if ($RequireLiveIdentity) {
            if ($process.HasExited) {
                throw "Expected $resolvedPath to remain live for identity verification."
            }
            if ($process.Path -ne $resolvedPath -or
                    $process.StartTime.ToUniversalTime() -ne $startedUtc -or
                    $process.ProcessorAffinity.ToInt64() -ne 15) {
                throw "Process identity or affinity verification failed for $resolvedPath."
            }
        }
        return [pscustomobject]@{
            Process = $process
            ExpectedPath = $resolvedPath
            ExpectedStartUtc = $startedUtc
            Stdout = $stdout
            Stderr = $stderr
            StdoutTask = $stdoutTask
            StderrTask = $stderrTask
            Completed = $false
        }
    }
    catch {
        if ($started) {
            try {
                $process.Refresh()
                if (-not $process.HasExited) {
                    # This is the exact Process object created above; no PID lookup.
                    $process.Kill($true)
                    $process.WaitForExit()
                }
            }
            catch {}
            try { if ($null -ne $stdoutTask) { [void]$stdoutTask.GetAwaiter().GetResult() } } catch {}
            try { if ($null -ne $stderrTask) { [void]$stderrTask.GetAwaiter().GetResult() } } catch {}
        }
        $stdout.Dispose()
        $stderr.Dispose()
        throw
    }
}

function Assert-LiveProcessIdentity {
    param([Parameter(Mandatory)] $Managed)
    $process = $Managed.Process
    $process.Refresh()
    if ($process.HasExited) {
        throw "Expected process $($process.Id) already exited."
    }
    if ($process.Path -ne $Managed.ExpectedPath -or
            $process.StartTime.ToUniversalTime() -ne $Managed.ExpectedStartUtc -or
            $process.ProcessorAffinity.ToInt64() -ne 15) {
        throw "Process identity or affinity changed for PID $($process.Id)."
    }
}

function Stop-ManagedProcess {
    param([Parameter(Mandatory)] $Managed)
    $process = $Managed.Process
    $process.Refresh()
    if (-not $process.HasExited) {
        Assert-LiveProcessIdentity $Managed
        $process.Kill($true)
        $process.WaitForExit()
    }
}

function Complete-ManagedProcess {
    param(
        [Parameter(Mandatory)] $Managed,
        [int]$TimeoutMilliseconds = -1
    )
    if ($Managed.Completed) { return $Managed.Process.ExitCode }
    $process = $Managed.Process
    $exited = if ($TimeoutMilliseconds -lt 0) {
        $process.WaitForExit()
        $true
    } else {
        $process.WaitForExit($TimeoutMilliseconds)
    }
    if (-not $exited) {
        Stop-ManagedProcess $Managed
        throw "$($Managed.ExpectedPath) did not exit within the timeout."
    }
    try {
        [void]$Managed.StdoutTask.GetAwaiter().GetResult()
        [void]$Managed.StderrTask.GetAwaiter().GetResult()
    }
    finally {
        $Managed.Stdout.Dispose()
        $Managed.Stderr.Dispose()
        $Managed.Completed = $true
    }
    return $process.ExitCode
}

function Invoke-CrowdRun {
    param(
        [Parameter(Mandatory)] [string]$RunLabel,
        [Parameter(Mandatory)] [string]$LogPath
    )
    & $runner -GodotPath $GodotPath -Profile primary -Mode $Mode `
        -Renderer $Renderer -NativeBackend $NativeBackend `
        -NativePresentation $NativePresentation -Repeats 1 `
        -SampleMilliseconds $SampleMilliseconds `
        -WarmupMilliseconds $WarmupMilliseconds `
        -PostReportGraceSeconds $postReportGraceSeconds `
        -CadenceMilliseconds 100 -EngineProfileMarkers `
        -Label $RunLabel `
        -InterferenceLabel `
            "shared host; unrelated Godot jobs authorized; activity not continuously monitored" `
        *>&1 | Tee-Object -LiteralPath $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "Crowd runner failed with exit code $LASTEXITCODE."
    }
}

$manifest = [ordered]@{
    schemaVersion = 1
    createdUtc = [DateTime]::UtcNow.ToString("o")
    diagnosticOnly = $true
    enginePath = $GodotPath
    engineSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $GodotPath).Hash.ToLowerInvariant()
    expectedEngineVersion = "4.7.2.stable.custom_build.ed1daf0bf"
    engineVersionFromBenchmark = $null
    mode = $Mode
    renderer = $Renderer
    nativeBackend = $NativeBackend
    nativePresentation = $NativePresentation
    sampleMilliseconds = $SampleMilliseconds
    warmupMilliseconds = $WarmupMilliseconds
    captureSeconds = $CaptureSeconds
    postReportGraceSeconds = $postReportGraceSeconds
    affinityMask = 15
    interference = "shared host; unrelated Godot jobs authorized; activity not continuously monitored"
    disconnectedBaseline = $null
    captured = $null
    trace = $null
    exports = @()
}

if ($RunDisconnectedBaseline) {
    $baselineStarted = [DateTime]::UtcNow
    $baselineLog = Join-Path $session "runner-disconnected.log"
    Invoke-CrowdRun "$Label-disconnected" $baselineLog
    $manifest.disconnectedBaseline = [ordered]@{
        startedUtc = $baselineStarted.ToString("o")
        runnerLog = $baselineLog
        reports = @(Get-ChildItem -LiteralPath $runRoot -File |
            Where-Object { $_.LastWriteTimeUtc -ge $baselineStarted } |
            Select-Object -ExpandProperty FullName)
    }
}

$trace = Join-Path $session "crowd-primary-$($Mode.ToLowerInvariant())-$Renderer.tracy"
$captureOut = Join-Path $session "tracy-capture.stdout.log"
$captureErr = Join-Path $session "tracy-capture.stderr.log"
$runnerLog = Join-Path $session "runner-captured.log"
$capture = Start-FileProcess $captureExe `
    @("-o", $trace, "-f", "-s", [string]$CaptureSeconds) `
    $captureOut $captureErr
Start-Sleep -Milliseconds 750
Assert-LiveProcessIdentity $capture
$capturedStarted = [DateTime]::UtcNow
$runError = $null
try {
    Invoke-CrowdRun "$Label-captured" $runnerLog
    if (-not $capture.Process.HasExited) {
        Assert-LiveProcessIdentity $capture
    }
    $captureExit = Complete-ManagedProcess $capture 300000
    if ($captureExit -ne 0) {
        throw "Tracy capture failed with exit code $captureExit."
    }
}
catch {
    $runError = $_
    if (-not $capture.Process.HasExited) {
        Stop-ManagedProcess $capture
    }
    if (-not $capture.Completed) {
        [void](Complete-ManagedProcess $capture)
    }
}
if ($null -ne $runError) { throw $runError }
if (-not (Test-Path -LiteralPath $trace -PathType Leaf)) {
    throw "Tracy did not create $trace."
}
$manifest.trace = $trace
$manifest.captured = [ordered]@{
    startedUtc = $capturedStarted.ToString("o")
    runnerLog = $runnerLog
    capturePid = $capture.Process.Id
    captureExecutable = $capture.ExpectedPath
    captureStartUtc = $capture.ExpectedStartUtc.ToString("o")
    reports = @(Get-ChildItem -LiteralPath $runRoot -File |
        Where-Object { $_.LastWriteTimeUtc -ge $capturedStarted } |
        Select-Object -ExpandProperty FullName)
}
$benchmarkReports = @($manifest.captured.reports | Where-Object {
    $_ -like "*.json" -and $_ -notlike "*.process.json"
} | ForEach-Object {
    $candidate = Get-Content -LiteralPath $_ -Raw | ConvertFrom-Json
    if ($null -ne $candidate.cells -and $null -ne $candidate.process) {
        [pscustomobject]@{ Path = $_; Report = $candidate }
    }
})
if ($benchmarkReports.Count -ne 1) {
    throw "Expected one captured benchmark report, found $($benchmarkReports.Count)."
}
$manifest.engineVersionFromBenchmark = $benchmarkReports[0].Report.godot
$manifestPath = Join-Path $session "manifest.json"
# Persist capture-time engine/source/process attestations before postprocessing,
# so an exporter failure can be resumed without substituting later provenance.
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath

$exports = @(
    @{ Name = "messages.csv"; Args = @("-m", $trace) },
    @{ Name = "zones.csv"; Args = @($trace) },
    @{ Name = "zones-self.csv"; Args = @("-e", $trace) }
)
$focusFilters = @(
    "Skeleton3D::",
    "AnimationMixer::",
    "SceneTree::",
    "Main::iteration",
    "RenderingServer::",
    "OS::add_frame_delay",
    "_stall_for_frame",
    "fence_wait",
    "_process_modification_with_delta",
    "update_pose"
)
for ($index = 0; $index -lt $focusFilters.Count; $index++) {
    $filter = $focusFilters[$index]
    $prefix = "focus-{0:D2}" -f $index
    $exports += @{
        Name = "$prefix-inclusive.csv"
        Args = @("-u", "-c", "-f", $filter, $trace)
    }, @{
        Name = "$prefix-self.csv"
        Args = @("-u", "-e", "-c", "-f", $filter, $trace)
    }
}
foreach ($export in $exports) {
    $path = Join-Path $session $export.Name
    $errorPath = "$path.stderr.log"
    $exportProcess = Start-FileProcess $csvExe $export.Args $path $errorPath $false
    $exitCode = Complete-ManagedProcess $exportProcess
    if ($exitCode -ne 0) {
        throw "Tracy CSV export $($export.Name) failed with exit code $exitCode."
    }
    $manifest.exports += $path
}

$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath
$analysisOut = Join-Path $session "analyzer.stdout.log"
$analysisErr = Join-Path $session "analyzer.stderr.log"
$analysisProcess = Start-FileProcess $PythonPath @($analyzer, $session) `
    $analysisOut $analysisErr $false
$analysisExit = Complete-ManagedProcess $analysisProcess
if ($analysisExit -ne 0) {
    throw "Steady-window analyzer rejected the capture; see $analysisErr."
}
$manifest["analysis"] = [ordered]@{
    json = Join-Path $session "steady-zone-summary.json"
    csv = Join-Path $session "steady-zone-summary.csv"
    stdout = $analysisOut
    stderr = $analysisErr
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath

Write-Output "TRACY_SESSION=$session"
Write-Output "TRACY_TRACE=$trace"
Write-Output "TRACY_MANIFEST=$manifestPath"
