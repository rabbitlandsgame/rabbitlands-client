[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string]$Session,
    [string]$DisconnectedRunId = "",
    [string]$GodotPath = "",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
(Get-Process -Id $PID).ProcessorAffinity = 15

$clientRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $clientRoot "test-artifacts/engine-profile"
$runRoot = Join-Path $clientRoot "test-artifacts/native-crowd"
$Session = (Resolve-Path -LiteralPath $Session).Path
if ([string]::IsNullOrWhiteSpace($GodotPath)) {
    $GodotPath = Join-Path $artifactRoot `
        "godot-4.7.2-stable/bin/godot.windows.template_release.x86_64.exe"
}
$GodotPath = (Resolve-Path -LiteralPath $GodotPath).Path
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (Get-Command python -ErrorAction Stop).Source
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
$csvExe = (Resolve-Path -LiteralPath (Join-Path $artifactRoot `
    "tracy-windows-0.13.0/tracy-csvexport.exe")).Path
$analyzer = Join-Path $PSScriptRoot "analyze_tracy_crowd_profile.py"
$traces = @(Get-ChildItem -LiteralPath $Session -Filter "*.tracy" -File)
if ($traces.Count -ne 1) { throw "Expected exactly one Tracy trace in $Session." }
$trace = $traces[0].FullName
$runnerLog = Join-Path $Session "runner-captured.log"
$firstRunnerLine = Get-Content -LiteralPath $runnerLog | Select-Object -First 1
if ($firstRunnerLine -notmatch '^Running (?<RunId>.+) serially \(') {
    throw "Cannot recover the captured run id from $runnerLog."
}
$runId = $Matches.RunId
$benchmarkPath = Join-Path $runRoot "$runId.json"
$processPath = Join-Path $runRoot "$runId.process.json"
$benchmark = Get-Content -LiteralPath $benchmarkPath -Raw | ConvertFrom-Json
$processReport = Get-Content -LiteralPath $processPath -Raw | ConvertFrom-Json
if (-not [bool]$processReport.cleanExit -or -not [bool]$processReport.reportValid -or
        [bool]$processReport.postReportStop) {
    throw "Captured process report is not a clean validated run: $processPath"
}
$priorManifestPath = Join-Path $Session "manifest.json"
$priorManifest = if (Test-Path -LiteralPath $priorManifestPath -PathType Leaf) {
    Get-Content -LiteralPath $priorManifestPath -Raw | ConvertFrom-Json
} else {
    $null
}
$hasPriorEnginePath = $null -ne $priorManifest -and
    $priorManifest.PSObject.Properties.Name -contains "enginePath"
$hasPriorEngineHash = $null -ne $priorManifest -and
    $priorManifest.PSObject.Properties.Name -contains "engineSha256" -and
    -not [string]::IsNullOrWhiteSpace([string]$priorManifest.engineSha256)
$captureEnginePath = if ($hasPriorEnginePath) {
    [string]$priorManifest.enginePath
} elseif ($processReport.PSObject.Properties.Name -contains "launchExecutablePath") {
    [string]$processReport.launchExecutablePath
} else {
    $null
}
$captureEngineSha256 = if ($hasPriorEngineHash) {
    [string]$priorManifest.engineSha256
} else {
    $null
}
$captureEngineAttestation = if ($hasPriorEngineHash) {
    "Path and SHA-256 preserved from the capture wrapper manifest."
} elseif (-not [string]::IsNullOrWhiteSpace($captureEnginePath)) {
    "Executable path preserved from the monitored process report; capture-time SHA-256 was unavailable."
} else {
    "Capture engine provenance unavailable."
}

function Invoke-FileProcess {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$Arguments,
        [Parameter(Mandatory)] [string]$StdoutPath,
        [Parameter(Mandatory)] [string]$StderrPath
    )
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = (Resolve-Path -LiteralPath $FilePath).Path
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { [void]$info.ArgumentList.Add($argument) }
    $stdout = [System.IO.File]::Open($StdoutPath, "Create", "Write", "Read")
    $stderr = [System.IO.File]::Open($StderrPath, "Create", "Write", "Read")
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw "Failed to start $FilePath." }
        $stdoutTask = $process.StandardOutput.BaseStream.CopyToAsync($stdout)
        $stderrTask = $process.StandardError.BaseStream.CopyToAsync($stderr)
        # Short-lived exporters can finish before this assignment. They inherit
        # affinity 15 from this PowerShell process, so only narrow it if live.
        if (-not $process.HasExited) {
            $process.ProcessorAffinity = [IntPtr]15
        }
        $process.WaitForExit()
        [void]$stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "$FilePath failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        $stdout.Dispose()
        $stderr.Dispose()
    }
}

$exports = @(
    @{ Name = "messages.csv"; Args = @("-m", $trace) },
    @{ Name = "zones.csv"; Args = @($trace) },
    @{ Name = "zones-self.csv"; Args = @("-e", $trace) }
)
$focusFilters = @(
    "Skeleton3D::", "AnimationMixer::", "SceneTree::", "Main::iteration",
    "RenderingServer::", "OS::add_frame_delay", "_stall_for_frame", "fence_wait",
    "_process_modification_with_delta", "update_pose"
)
for ($index = 0; $index -lt $focusFilters.Count; $index++) {
    $prefix = "focus-{0:D2}" -f $index
    $exports += @{
        Name = "$prefix-inclusive.csv"
        Args = @("-u", "-c", "-f", $focusFilters[$index], $trace)
    }, @{
        Name = "$prefix-self.csv"
        Args = @("-u", "-e", "-c", "-f", $focusFilters[$index], $trace)
    }
}
foreach ($export in $exports) {
    $path = Join-Path $Session $export.Name
    Invoke-FileProcess $csvExe $export.Args $path "$path.stderr.log"
}

$capturedReports = @(
    $benchmarkPath,
    $processPath,
    (Join-Path $runRoot "$runId.log"),
    (Join-Path $runRoot "$runId.stdout.log"),
    (Join-Path $runRoot "$runId.stderr.log")
)
$manifest = [ordered]@{
    schemaVersion = 1
    createdUtc = [DateTime]::UtcNow.ToString("o")
    resumedExistingSession = $true
    diagnosticOnly = $true
    enginePath = $captureEnginePath
    engineSha256 = $captureEngineSha256
    engineAttestation = "$captureEngineAttestation The trace does not independently authenticate the binary."
    resumeEngine = [ordered]@{
        path = $GodotPath
        sha256 = (Get-FileHash -LiteralPath $GodotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    expectedEngineVersion = "4.7.2.stable.custom_build.ed1daf0bf"
    engineVersionFromBenchmark = $benchmark.godot
    benchmarkCommit = $processReport.commit
    benchmarkSourceHash = $processReport.sourceHash
    mode = $processReport.mode
    renderer = $processReport.renderer
    nativeBackend = $processReport.backend
    nativePresentation = $processReport.nativePresentationRequested
    postReportGraceSeconds = $processReport.postReportGraceSeconds
    affinityMask = 15
    interference = $benchmark.interferenceLabel
    disconnectedBaseline = $null
    captured = [ordered]@{
        runId = $runId
        processId = $processReport.rootPid
        cleanExit = $processReport.cleanExit
        reportValid = $processReport.reportValid
        runnerLog = $runnerLog
        reports = $capturedReports
    }
    trace = [ordered]@{
        path = $trace
        bytes = (Get-Item -LiteralPath $trace).Length
        sha256 = (Get-FileHash -LiteralPath $trace -Algorithm SHA256).Hash.ToLowerInvariant()
        captureLog = Join-Path $Session "tracy-capture.stdout.log"
    }
    postprocessors = [ordered]@{
        csvExporter = [ordered]@{
            path = $csvExe
            sha256 = (Get-FileHash -LiteralPath $csvExe -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        analyzer = [ordered]@{
            path = $analyzer
            sha256 = (Get-FileHash -LiteralPath $analyzer -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        finalizer = [ordered]@{
            path = $PSCommandPath
            sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    exports = @($exports | ForEach-Object {
        $path = Join-Path $Session $_.Name
        [ordered]@{
            path = $path
            bytes = (Get-Item -LiteralPath $path).Length
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
}
if (-not [string]::IsNullOrWhiteSpace($DisconnectedRunId)) {
    $baselinePath = Join-Path $runRoot "$DisconnectedRunId.json"
    $baselineProcessPath = Join-Path $runRoot "$DisconnectedRunId.process.json"
    $baselineProcess = Get-Content -LiteralPath $baselineProcessPath -Raw | ConvertFrom-Json
    if (-not [bool]$baselineProcess.cleanExit -or -not [bool]$baselineProcess.reportValid) {
        throw "Disconnected baseline is not a clean validated run: $baselineProcessPath"
    }
    $manifest.disconnectedBaseline = [ordered]@{
        runId = $DisconnectedRunId
        report = $baselinePath
        processReport = $baselineProcessPath
        sourceHash = $baselineProcess.sourceHash
        commit = $baselineProcess.commit
    }
}
$manifestPath = $priorManifestPath
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath

$analysisOut = Join-Path $Session "analyzer.stdout.log"
$analysisErr = Join-Path $Session "analyzer.stderr.log"
Invoke-FileProcess $PythonPath @($analyzer, $Session) $analysisOut $analysisErr
$manifest["analysis"] = [ordered]@{
    json = Join-Path $Session "steady-zone-summary.json"
    csv = Join-Path $Session "steady-zone-summary.csv"
    stdout = $analysisOut
    stderr = $analysisErr
}
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath
Write-Output "TRACY_SESSION=$Session"
Write-Output "TRACY_MANIFEST=$manifestPath"
Write-Output "TRACY_ANALYSIS=$($manifest.analysis.json)"
