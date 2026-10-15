param(
    [string]$GodotPath = '',
    [string]$Python = '',
    [string]$ServerRoot = '',
    [ValidateRange(1024,65535)][int]$Port = 2013,
    [switch]$Fresh,
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
$clientRoot = Split-Path -Parent $PSScriptRoot
if (-not $ServerRoot) { $ServerRoot = Join-Path (Split-Path -Parent $clientRoot) 'dev-server' }
$ServerRoot = [IO.Path]::GetFullPath($ServerRoot)
if (-not (Test-Path -LiteralPath (Join-Path $ServerRoot 'eloria/sky.py'))) {
    throw 'Pass -ServerRoot pointing to the matching dev-server checkout with magic ring training.'
}
if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
$profile = Join-Path $clientRoot 'godot-client/test-artifacts/magic-tutorial/local'
if ($Fresh -or $Check) { $profile += '-' + [Guid]::NewGuid().ToString('N') }
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$database = Join-Path $profile 'characters.sqlite3'
$terrain = Join-Path $profile 'server-maps'
$probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Port)
try { $probe.Start() } catch { throw "Port $Port is in use. Run with -Port 2014 to choose another." }
finally { $probe.Stop() }
& $Python (Join-Path $PSScriptRoot 'magic_tutorial_profile.py') $ServerRoot $database
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the local tutorial account.' }
& $Python (Join-Path $ServerRoot 'tools/prepare_local_maps.py') $terrain
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the local server maps.' }
$savedAppData = $env:APPDATA
$savedLocalAppData = $env:LOCALAPPDATA
$savedTerrain = $env:ELORIA_DATA_DIRECTORY
$localServer = $null
try {
    $env:APPDATA = $profile
    $env:LOCALAPPDATA = $profile
    $env:ELORIA_DATA_DIRECTORY = $terrain
    $serverArgs = @('-m','eloria.server','--host','127.0.0.1','--port',"$Port",'--database',('"'+$database+'"'))
    $localServer = Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $ServerRoot `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $profile 'server.log') `
        -RedirectStandardError (Join-Path $profile 'server-errors.log') -PassThru
    $ready = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not $ready -and [DateTime]::UtcNow -lt $deadline) {
        $localServer.Refresh()
        if ($localServer.HasExited) { throw "Local server stopped. See $profile\server-errors.log" }
        $connection = [Net.Sockets.TcpClient]::new()
        try { $ready = $connection.ConnectAsync('127.0.0.1',$Port).Wait(250) -and $connection.Connected }
        catch { $ready = $false }
        finally { $connection.Dispose() }
        if (-not $ready) { Start-Sleep -Milliseconds 200 }
    }
    if (-not $ready) { throw "Local server did not start. See $profile\server-errors.log" }
    Write-Host 'Magic ring tutorial: local server ready.'
    Write-Host 'Log in as RingStudent with password ringpractice, then type #tutorial magic in chat.'
    Write-Host 'Your tutorial checkpoint is kept for the next run. Use -Fresh for a separate new practice account.'
    if ($Check) {
        if (-not $GodotPath) { $GodotPath = Join-Path $env:USERPROFILE 'Downloads/godot47/Godot_v4.7.2-stable_win64_console.exe' }
        $clientLog = Join-Path $profile 'client-check.log'
        & $GodotPath --headless --path (Join-Path $clientRoot 'godot-client') --script res://tests/test_magic_ring_tutorial_live.gd --log-file $clientLog --quit-after 20000 -- "--server=127.0.0.1" "--port=$Port"
        if ($LASTEXITCODE -ne 0 -or (Get-Content -LiteralPath $clientLog -Raw) -notmatch 'live magic ring tutorial: PASS') { throw "Live tutorial check failed. See $clientLog" }
    } else {
        & (Join-Path $PSScriptRoot 'run-magic-prototype.ps1') -Live -Mode wheel -GodotPath $GodotPath -Server '127.0.0.1' -Port $Port
        if ($LASTEXITCODE -ne 0) { throw "Client exited with code $LASTEXITCODE" }
    }
} finally {
    if ($localServer -and -not $localServer.HasExited) { Stop-Process -Id $localServer.Id -ErrorAction SilentlyContinue }
    $env:APPDATA = $savedAppData
    $env:LOCALAPPDATA = $savedLocalAppData
    $env:ELORIA_DATA_DIRECTORY = $savedTerrain
}
