param(
    [string[]]$Slugs = 'luminous_male,luminous_female',
    [string[]]$Clips = 'Rest_Pose,Idle_Subtle,Walk,Jog,Run_Female,Fighting_Idle',
    [string[]]$Angles = 'front,side,gameplay',
    [string]$Prefix = 'candidate',
    [string]$Equipment = '',
    [string]$Outfit = '',
    [int]$Style = -1,
    [string]$Region = 'full',
    [string]$Hide = '',
    [switch]$Cycles
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$scratch = Join-Path $taskRoot 'equipment-fit-build/preview'
New-Item -ItemType Directory -Force $scratch | Out-Null
$godot = 'godot'
foreach ($slug in ($Slugs -join ',').Split(',')) {
    foreach ($clip in ($Clips -join ',').Split(',')) {
        foreach ($angle in ($Angles -join ',').Split(',')) {
            $name = "${Prefix}_${slug}_${clip}_${angle}"
            $out = Join-Path $scratch "$name.png"
            $argsList = @('--path', "$taskRoot/godot-client", '--script', 'res://tests/canonical_equipment_preview.gd',
                '--log-file', "$scratch/$name-engine.log", '--', '--slug', $slug, '--out', $out,
                '--clip', $clip, '--angle', $angle, '--gear', 'yes', '--hair', 'yes', '--region', $Region)
            if ($Equipment) { $argsList += @('--equipment', (Resolve-Path -LiteralPath $Equipment).Path) }
            if ($Outfit) { $argsList += @('--outfit', $Outfit) }
            if ($Hide) { $argsList += @('--hide', $Hide) }
            if ($Style -ge 0) { $argsList += @('--style', [string]$Style) }
            if ($Cycles) { $argsList += @('--cycle', 'yes') }
            $process = Start-Process -FilePath $godot -ArgumentList $argsList -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput "$scratch/$name.log" -RedirectStandardError "$scratch/$name.err"
            $process.Id | Set-Content -LiteralPath "$scratch/$name.pid"
            if (!$process.WaitForExit(180000)) {
                $process.Kill()
                throw "Capture timed out: $name"
            }
            if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath "$out.json")) { throw "Capture failed: $name" }
            Write-Output $out
        }
    }
}
