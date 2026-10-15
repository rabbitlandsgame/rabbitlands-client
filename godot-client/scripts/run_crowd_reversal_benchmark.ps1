[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OptimizedRevision,
    [string]$BaselineRevision = '4c42ab09f12844d5b9e370619c9be93b4f48033f',
    [Parameter(Mandatory = $true)][string]$GodotPath,
    [ValidateSet('Headless', 'Windowed')][string]$Mode = 'Headless',
    [ValidateSet('gl_compatibility', 'forward_plus')]
    [string]$Renderer = 'gl_compatibility',
    [string]$Sequence = 'A,B,B,A,A,B',
    [ValidateSet('Off', 'Cape', 'Flight', 'Both', 'World', 'All')]
    [string]$BaselineNativePresentation = 'Off',
    [ValidateSet('Off', 'Cape', 'Flight', 'Both', 'World', 'All')]
    [string]$CandidateNativePresentation = 'Off',
    [string[]]$RelativePaths = @(
        'godot-client/src/actors/cape_cloth.gd',
        'godot-client/src/world/combat_effect_mesh.gd',
        'godot-client/src/world/spell_flight_3d.gd',
        'godot-client/src/world/world_effect_3d.gd'
    ),
    [string]$Label = 'optimization-final-reversal-v1',
    [ValidateRange(1000, 30000)][int]$SampleMilliseconds = 5000,
    [switch]$Capture,
    [switch]$CpuSlotGranted
)

$ErrorActionPreference = 'Stop'
(Get-Process -Id $PID).ProcessorAffinity = 15
if (-not $CpuSlotGranted) {
    throw 'Refusing to switch sources or run Godot without -CpuSlotGranted.'
}

$clientRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $clientRoot)).Path
$runner = Join-Path $clientRoot 'scripts/run_crowd_benchmarks.ps1'
$godotRequested = (Resolve-Path -LiteralPath $GodotPath).Path
$godotLaunch = $godotRequested
if ([IO.Path]::GetFileNameWithoutExtension($godotRequested) -like '*_console') {
    $directPath = Join-Path (Split-Path -Parent $godotRequested) `
        (([IO.Path]::GetFileNameWithoutExtension($godotRequested) -replace '_console$', '') + '.exe')
    $godotLaunch = (Resolve-Path -LiteralPath $directPath).Path
}
$safeLabel = ($Label -replace '[^A-Za-z0-9_.-]+', '-').Trim('-')
if ([string]::IsNullOrWhiteSpace($safeLabel) -or $safeLabel -ne $Label) {
    throw 'Label must already be a nonempty filename-safe value.'
}
$artifactRoot = Join-Path $clientRoot 'test-artifacts/native-crowd/optimization-reversal'
$sessionStamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$sessionRoot = Join-Path $artifactRoot "$safeLabel-$Mode-$sessionStamp"
$backupRoot = Join-Path $sessionRoot 'candidate-backups'
$originalRoot = Join-Path $sessionRoot 'original-blobs'
New-Item -ItemType Directory -Force -Path $sessionRoot, $backupRoot, $originalRoot |
    Out-Null

$approvedRelativePaths = @(
    'godot-client/src/app/main.gd',
    'godot-client/src/actors/cape_cloth.gd',
    'godot-client/src/actors/combat_presentation_3d.gd',
    'godot-client/src/actors/ranger_bow_3d.gd',
    'godot-client/src/actors/replicated_actor_3d.gd',
    'godot-client/src/world/combat_effect_mesh.gd',
    'godot-client/src/world/spell_flight_3d.gd',
    'godot-client/src/world/world_effect_3d.gd'
)
$relativePaths = @($RelativePaths | ForEach-Object { $_.Replace('\', '/').Trim() })
if ($relativePaths.Count -eq 0 -or @($relativePaths | Where-Object {
        [string]::IsNullOrWhiteSpace($_) -or $_ -notin $approvedRelativePaths
    }).Count -or @($relativePaths | Sort-Object -Unique).Count -ne $relativePaths.Count) {
    throw ('RelativePaths must be unique entries from the approved runtime allowlist: ' +
        ($approvedRelativePaths -join ', '))
}
$variants = @($Sequence.Split(',') | ForEach-Object { $_.Trim().ToUpperInvariant() })
if ($variants.Count -lt 3 -or @($variants | Where-Object { $_ -notin @('A', 'B') }).Count -or
    'A' -notin $variants -or 'B' -notin $variants) {
    throw 'Sequence must contain at least three entries and include both A and B.'
}

$git = (Get-Command git -ErrorAction Stop).Source
$gitSafe = "safe.directory=$($repositoryRoot.Replace('\', '/'))"
function Invoke-Git([string[]]$Arguments) {
    $text = & $git -c $gitSafe -C $repositoryRoot @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git failed: $($Arguments -join ' ')" }
    return $text
}

function Get-Sha256Bytes([byte[]]$Bytes) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToHexString($algorithm.ComputeHash($Bytes)).ToLowerInvariant() }
    finally { $algorithm.Dispose() }
}

function Get-GitBlobBytes([string]$Revision, [string]$RelativePath) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $git
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in @('-c', $gitSafe, '-C', $repositoryRoot, 'show',
            "${Revision}:$RelativePath")) {
        [void]$start.ArgumentList.Add($argument)
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw "Could not start git show for $RelativePath." }
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $memory = [IO.MemoryStream]::new()
    try {
        $process.StandardOutput.BaseStream.CopyTo($memory)
        $process.WaitForExit()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) {
            throw "git show failed for ${Revision}:$RelativePath`: $stderr"
        }
        return ,$memory.ToArray()
    }
    finally {
        $memory.Dispose()
        $process.Dispose()
    }
}

function Set-ExactBytes([string]$Path, [byte[]]$Bytes, [string]$ExpectedHash,
        [string]$ExpectedCurrentHash) {
    $temporary = "$Path.reversal-$PID.tmp"
    try {
        $currentHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($currentHash -ne $ExpectedCurrentHash) {
            throw "Concurrent content change detected before writing $Path."
        }
        [IO.File]::WriteAllBytes($temporary, $Bytes)
        $temporaryHash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($temporaryHash -ne $ExpectedHash) { throw "Temporary hash mismatch for $Path." }
        [IO.File]::Move($temporary, $Path, $true)
        $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $ExpectedHash) { throw "Installed hash mismatch for $Path." }
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Get-CurrentHashes {
    $result = [ordered]@{}
    foreach ($relativePath in $relativePaths) {
        $absolutePath = Join-Path $repositoryRoot $relativePath
        $result[$relativePath] = (Get-FileHash -LiteralPath $absolutePath `
            -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $result
}

function Assert-WorkspaceVariant([string]$Variant,
        [Collections.IDictionary]$ExpectedHashes) {
    $currentBranch = (Invoke-Git @('branch', '--show-current')).Trim()
    if ($currentBranch -ne 'perf/native-crowd-300-benchmark') {
        throw "Branch changed to $currentBranch."
    }
    $head = (Invoke-Git @('rev-parse', 'HEAD')).Trim()
    if ($head -ne $OptimizedRevision) { throw "HEAD moved from optimized commit to $head." }
    $current = Get-CurrentHashes
    foreach ($relativePath in $relativePaths) {
        if ($current[$relativePath] -ne $ExpectedHashes[$relativePath]) {
            throw "$Variant hash mismatch for $relativePath."
        }
    }
    $trackedStatus = @(Invoke-Git @('status', '--porcelain', '--untracked-files=no'))
    $changedPaths = @($trackedStatus | ForEach-Object {
        if ($_.Length -lt 4) { throw "Cannot parse git status line: $_" }
        $_.Substring(3).Trim('"') -replace '\\', '/'
    } | Sort-Object -Unique)
    $expectedChanged = if ($Variant -eq 'A') { @($baselineChangedPaths) } else { @() }
    $statusMismatch = $expectedChanged.Count -ne $changedPaths.Count
    if (-not $statusMismatch -and $expectedChanged.Count -gt 0) {
        $statusMismatch = @(Compare-Object -ReferenceObject $expectedChanged `
            -DifferenceObject $changedPaths).Count -ne 0
    }
    if ($statusMismatch) {
        throw "Unexpected tracked paths for $Variant. Expected [$($expectedChanged -join ', ')], " +
            "found [$($changedPaths -join ', ')]."
    }
    return $current
}

$repositoryProbe = (Invoke-Git @('rev-parse', '--show-toplevel')).Trim().Replace('\', '/')
if ($repositoryProbe -ne $repositoryRoot.Replace('\', '/')) { throw 'Resolved Git repository mismatch.' }
$branch = (Invoke-Git @('branch', '--show-current')).Trim()
if ($branch -ne 'perf/native-crowd-300-benchmark') {
    throw "Expected perf/native-crowd-300-benchmark; found $branch."
}
$candidateHead = (Invoke-Git @('rev-parse', $OptimizedRevision)).Trim()
if ($candidateHead -ne $OptimizedRevision) {
    throw 'OptimizedRevision must be a full resolved commit ID.'
}
$head = (Invoke-Git @('rev-parse', 'HEAD')).Trim()
if ($head -ne $OptimizedRevision) {
    throw "Expected optimized HEAD $OptimizedRevision; found $head."
}
$baselineHead = (Invoke-Git @('rev-parse', "$BaselineRevision^{commit}")).Trim()
if (@(Invoke-Git @('status', '--porcelain', '--untracked-files=no')).Count) {
    throw 'Tracked worktree must be clean before the reversal session.'
}
$unlistedRevisionChanges = [Collections.Generic.List[string]]::new()
foreach ($approvedPath in $approvedRelativePaths) {
    $candidateBlobHash = Get-Sha256Bytes (
        Get-GitBlobBytes $OptimizedRevision $approvedPath)
    $baselineBlobHash = Get-Sha256Bytes (
        Get-GitBlobBytes $baselineHead $approvedPath)
    if ($candidateBlobHash -ne $baselineBlobHash -and
            $approvedPath -notin $relativePaths) {
        $unlistedRevisionChanges.Add($approvedPath)
    }
}
if ($unlistedRevisionChanges.Count -gt 0) {
    throw ("RelativePaths omits runtime files changed between the two revisions: " +
        ($unlistedRevisionChanges -join ', '))
}

$candidateBytes = [ordered]@{}
$candidateHashes = [ordered]@{}
$candidateGitBlobHashes = [ordered]@{}
$originalBytes = [ordered]@{}
$originalHashes = [ordered]@{}
foreach ($relativePath in $relativePaths) {
    $absolutePath = Join-Path $repositoryRoot $relativePath
    $candidateBytes[$relativePath] = [IO.File]::ReadAllBytes($absolutePath)
    $candidateHashes[$relativePath] = Get-Sha256Bytes $candidateBytes[$relativePath]
    $committedCandidate = Get-GitBlobBytes $OptimizedRevision $relativePath
    # The checkout may have CRLF worktree conversion. Git's clean status above
    # proves the workspace corresponds to the commit; retain both the exact
    # worktree bytes used by Godot and the repository blob hash as provenance.
    $candidateGitBlobHashes[$relativePath] = Get-Sha256Bytes $committedCandidate
    $originalBytes[$relativePath] = Get-GitBlobBytes $baselineHead $relativePath
    $originalHashes[$relativePath] = Get-Sha256Bytes $originalBytes[$relativePath]
    $safeName = $relativePath.Replace('/', '__')
    [IO.File]::WriteAllBytes((Join-Path $backupRoot "$safeName.candidate"),
        $candidateBytes[$relativePath])
    [IO.File]::WriteAllBytes((Join-Path $originalRoot "$safeName.original"),
        $originalBytes[$relativePath])
}
$baselineChangedPaths = @($relativePaths | Where-Object {
    $candidateGitBlobHashes[$_] -ne $originalHashes[$_]
} | Sort-Object)
$baselineBytes = [ordered]@{}
$baselineEffectiveHashes = [ordered]@{}
foreach ($relativePath in $relativePaths) {
    if ($relativePath -in $baselineChangedPaths) {
        $baselineBytes[$relativePath] = $originalBytes[$relativePath]
        $baselineEffectiveHashes[$relativePath] = $originalHashes[$relativePath]
    }
    else {
        # Preserve checkout line endings for blob-identical paths. Rewriting a
        # raw `git show` blob can make an otherwise identical Windows worktree
        # appear dirty even though the Git objects are the same.
        $baselineBytes[$relativePath] = $candidateBytes[$relativePath]
        $baselineEffectiveHashes[$relativePath] = $candidateHashes[$relativePath]
    }
}

$runnerHash = (Get-FileHash -LiteralPath $runner -Algorithm SHA256).Hash.ToLowerInvariant()
$godotRequestedHash = (Get-FileHash -LiteralPath $godotRequested `
    -Algorithm SHA256).Hash.ToLowerInvariant()
$godotLaunchHash = (Get-FileHash -LiteralPath $godotLaunch `
    -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    schemaVersion = 1
    startedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    optimizedRevision = $OptimizedRevision
    baselineRevisionInput = $BaselineRevision
    baselineRevision = $baselineHead
    relativePaths = $relativePaths
    approvedRelativePaths = $approvedRelativePaths
    unlistedRevisionChanges = @($unlistedRevisionChanges)
    mode = $Mode
    renderer = $Renderer
    sequence = $variants
    baselineNativePresentation = $BaselineNativePresentation
    candidateNativePresentation = $CandidateNativePresentation
    label = $safeLabel
    sampleMilliseconds = $SampleMilliseconds
    interferenceLabel = 'shared host; unrelated Godot jobs authorized; activity not continuously monitored'
    runner = [ordered]@{ path = $runner; sha256 = $runnerHash }
    godot = [ordered]@{
        requestedPath = $godotRequested; requestedSha256 = $godotRequestedHash
        launchPath = $godotLaunch; launchSha256 = $godotLaunchHash
    }
    candidateHashes = $candidateHashes
    candidateGitBlobHashes = $candidateGitBlobHashes
    originalHashes = $originalHashes
    baselineChangedPaths = $baselineChangedPaths
    baselineEffectiveHashes = $baselineEffectiveHashes
    runs = [Collections.Generic.List[object]]::new()
    lockAcquired = $false
    restored = $false
    restoreSkippedReason = ''
    restoreErrors = [Collections.Generic.List[string]]::new()
}
$manifestPath = Join-Path $sessionRoot 'reversal-session.json'
$failure = $null
$lockPath = Join-Path $artifactRoot 'reversal.lock'
$lock = $null
$ownsLock = $false
$currentVariant = 'B'
try {
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $ownsLock = $true
    $manifest.lockAcquired = $true
    for ($index = 0; $index -lt $variants.Count; $index++) {
        $variant = $variants[$index]
        $variantName = if ($variant -eq 'A') { 'baseline' } else { 'optimized' }
        $variantRevision = if ($variant -eq 'A') { $baselineHead } else { $OptimizedRevision }
        $variantNativePresentation = if ($variant -eq 'A') {
            $BaselineNativePresentation
        } else {
            $CandidateNativePresentation
        }
        $bytes = if ($variant -eq 'A') { $baselineBytes } else { $candidateBytes }
        $hashes = if ($variant -eq 'A') { $baselineEffectiveHashes } else { $candidateHashes }
        $previousHashes = if ($currentVariant -eq 'A') {
            $baselineEffectiveHashes
        } else {
            $candidateHashes
        }
        Assert-WorkspaceVariant $currentVariant $previousHashes | Out-Null
        if ($variant -ne $currentVariant) {
            foreach ($relativePath in $relativePaths) {
                Set-ExactBytes (Join-Path $repositoryRoot $relativePath) `
                    $bytes[$relativePath] $hashes[$relativePath] $previousHashes[$relativePath]
            }
            $currentVariant = $variant
        }
        $effectiveHashes = Assert-WorkspaceVariant $variant $hashes
        $effectiveHashText = ($hashes.GetEnumerator() | ForEach-Object {
            "$($_.Key)=$($_.Value)"
        }) -join "`n"
        $effectiveDigest = Get-Sha256Bytes ([Text.Encoding]::UTF8.GetBytes($effectiveHashText))
        $runLabel = '{0}-{1:D2}-{2}-{3}-{4}' -f $safeLabel, ($index + 1), $variantName,
            $variantRevision.Substring(0, 8), $effectiveDigest.Substring(0, 12)
        $beforeReports = @((Get-ChildItem -LiteralPath (Join-Path $clientRoot `
            'test-artifacts/native-crowd') -Filter "$runLabel-*.json" -File).FullName)
        $runStarted = (Get-Date).ToUniversalTime().ToString('o')
        $arguments = @{
            GodotPath = $godotRequested; Profile = 'primary'; Mode = $Mode
            Renderer = $Renderer; NativeBackend = 'GDScript'; Repeats = 1
            TimeoutMinutes = 30; SampleMilliseconds = $SampleMilliseconds
            WarmupMilliseconds = 1000; CadenceMilliseconds = 100; Label = $runLabel
            InterferenceLabel = $manifest.interferenceLabel
            NativePresentation = $variantNativePresentation
        }
        if ($Capture) { $arguments.Capture = $true }
        & $runner @arguments
        if ($LASTEXITCODE -ne 0) { throw "Benchmark run $($index + 1) exited $LASTEXITCODE." }
        Assert-WorkspaceVariant $variant $hashes | Out-Null
        $afterReports = @((Get-ChildItem -LiteralPath (Join-Path $clientRoot `
            'test-artifacts/native-crowd') -Filter "$runLabel-*.json" -File).FullName)
        $newFiles = @($afterReports | Where-Object { $_ -notin $beforeReports })
        $report = @($newFiles | Where-Object { $_ -notlike '*.process.json' })
        $process = @($newFiles | Where-Object { $_ -like '*.process.json' })
        if ($report.Count -ne 1 -or $process.Count -ne 1) {
            throw "Run $($index + 1) did not create exactly one report/process pair."
        }
        $reportJson = Get-Content -Raw -LiteralPath $report[0] | ConvertFrom-Json
        $processJson = Get-Content -Raw -LiteralPath $process[0] | ConvertFrom-Json
        $observedProcesses = @($processJson.observedProcesses.psobject.Properties.Value)
        $expectedDirty = $variant -eq 'A'
        if ($reportJson.failureCount -ne 0 -or -not $processJson.reportValid -or
            -not $processJson.schemaValid -or -not $processJson.cleanExit -or
            $processJson.exitCode -ne 0 -or $processJson.affinityMask -ne 15 -or
            -not $processJson.allObservedProcessesVerified -or
            $processJson.scriptErrorsDetected -or $processJson.forcedTermination -or
            $processJson.abortedAfterReport -or $processJson.postReportStop -or
            -not [string]::IsNullOrEmpty([string]$processJson.monitoringError) -or
            $observedProcesses.Count -eq 0 -or
            @($observedProcesses | Where-Object { $_.affinityMask -ne 15 }).Count -or
            $reportJson.label -ne $runLabel -or $reportJson.commit -ne $OptimizedRevision -or
            $reportJson.dirty -ne $expectedDirty -or
            $reportJson.nativePresentation.requestedMode -ne
                $variantNativePresentation.ToLowerInvariant() -or
            $processJson.commit -ne $OptimizedRevision -or
            $processJson.dirty -ne $expectedDirty -or
            $processJson.nativePresentationRequested -ne $variantNativePresentation -or
            $processJson.sourceHash -ne $reportJson.sourceHash) {
            throw "Run $($index + 1) failed report/process validation."
        }
        foreach ($relativePath in $relativePaths) {
            $attestedHash = $processJson.sourceFiles.psobject.Properties[$relativePath].Value
            if ($attestedHash -ne $hashes[$relativePath]) {
                throw "Run $($index + 1) source attestation mismatch for $relativePath."
            }
        }
        $manifest.runs.Add([ordered]@{
            order = $index + 1; variant = $variant; variantName = $variantName
            variantRevision = $variantRevision; label = $runLabel
            nativePresentation = $variantNativePresentation
            effectiveDigest = $effectiveDigest; startedAtUtc = $runStarted
            completedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
            effectiveHashes = $effectiveHashes; sourceHash = $reportJson.sourceHash
            dirty = $reportJson.dirty; runId = $reportJson.runId
            report = [ordered]@{ path = $report[0]; sha256 = (Get-FileHash `
                -LiteralPath $report[0] -Algorithm SHA256).Hash.ToLowerInvariant() }
            process = [ordered]@{ path = $process[0]; sha256 = (Get-FileHash `
                -LiteralPath $process[0] -Algorithm SHA256).Hash.ToLowerInvariant() }
        })
        $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath
    }
}
catch { $failure = $_ }
finally {
    if ($ownsLock) {
        $restoreHead = ''
        try { $restoreHead = (Invoke-Git @('rev-parse', 'HEAD')).Trim() }
        catch {
            $manifest.restoreErrors.Add(
                "Cannot verify HEAD before restore: $($_.Exception.Message)")
        }
        foreach ($relativePath in $relativePaths) {
            try {
                $absolutePath = Join-Path $repositoryRoot $relativePath
                $currentHash = (Get-FileHash -LiteralPath $absolutePath `
                    -Algorithm SHA256).Hash.ToLowerInvariant()
                $knownHashes = @(
                    $candidateHashes[$relativePath], $baselineEffectiveHashes[$relativePath])
                if ($restoreHead -ne $OptimizedRevision) {
                    throw "HEAD changed to $restoreHead; refusing to overwrite $relativePath."
                }
                if ($currentHash -notin $knownHashes) {
                    throw "Unexpected concurrent content in $relativePath; refusing to overwrite it."
                }
                Set-ExactBytes $absolutePath $candidateBytes[$relativePath] `
                    $candidateHashes[$relativePath] $currentHash
            }
            catch { $manifest.restoreErrors.Add("$relativePath`: $($_.Exception.Message)") }
        }
        try { Assert-WorkspaceVariant 'B' $candidateHashes | Out-Null }
        catch { $manifest.restoreErrors.Add($_.Exception.Message) }
        $manifest.restored = $manifest.restoreErrors.Count -eq 0
    }
    else {
        $manifest.restoreSkippedReason = 'exclusive lock was not acquired; no source writes owned'
    }
    $manifest.completedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath
    if ($null -ne $lock) { $lock.Dispose() }
}
if ($ownsLock -and -not $manifest.restored) {
    throw "Candidate restoration failed: $($manifest.restoreErrors -join '; ')"
}
if ($null -ne $failure) { throw $failure }
Write-Host "Controlled reversal complete and candidate bytes restored: $manifestPath"
