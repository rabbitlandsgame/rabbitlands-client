param(
    [string]$Godot = $env:GODOT_EXE,
    [string]$Python = $env:PYTHON_EXE,
    [ValidateRange(1024,65535)][int]$Port = 2008,
    [switch]$Fresh
)

$ErrorActionPreference = 'Stop'
if (-not $Godot) {
    $localEngineRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../godot-client'))
    foreach ($localEngineName in @('Godot_v4.7.2-stable_win64_console.exe', 'Godot_v4.7.2-stable_win64.exe')) {
        $localEngine = Join-Path $localEngineRoot $localEngineName
        if (Test-Path -LiteralPath $localEngine) { $Godot = $localEngine; break }
    }
}

if (-not $Godot) {
    $command = Get-Command godot -ErrorAction SilentlyContinue
    if ($command) { $Godot = $command.Source }
}
if (-not $Godot) {
    $candidate = Join-Path $env:USERPROFILE 'Downloads/godot47/Godot_v4.7.2-stable_win64_console.exe'
    if (Test-Path -LiteralPath $candidate) { $Godot = $candidate }
}
if (-not $Godot -or -not (Test-Path -LiteralPath $Godot)) {
    throw 'Pass a Godot 4 executable: .\play.cmd -Godot "C:\path\Godot.exe"'
}
if (-not $Python) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { $Python = $command.Source }
}
if (-not $Python) { throw 'Python 3.11+ is required. Pass -Python "C:\path\python.exe".' }
$serverRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../rabbitlands-server'))
$clientRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../godot-client'))
if (-not (Test-Path -LiteralPath (Join-Path $serverRoot 'eloria/lantern.py'))) {
    throw 'The matching rabbitlands-server checkout must be beside rabbitlands-client.'
}
$profile = Join-Path $PSScriptRoot '.local/native'
if ($Fresh) { $profile = Join-Path $PSScriptRoot ('.local/native-' + [Guid]::NewGuid().ToString('N')) }
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$profile = [IO.Path]::GetFullPath($profile)
$database = Join-Path $profile 'characters.sqlite3'
$terrain = Join-Path $profile 'server-maps'
$probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
try { $probe.Start() } catch { throw "Port $Port is in use. Try .\play.cmd -Port 2009." }
finally { $probe.Stop() }
$savedAppData = $env:APPDATA
$savedLocalAppData = $env:LOCALAPPDATA
$savedTerrain = $env:ELORIA_DATA_DIRECTORY
$localServer = $null
try {
    & $Python (Join-Path $serverRoot 'tools/prepare_local_maps.py') $terrain
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare local server terrain.' }
    $env:APPDATA = $profile
    $env:LOCALAPPDATA = $profile
    $env:ELORIA_DATA_DIRECTORY = $terrain
    $serverArgs = @('-m', 'eloria.server', '--host', '127.0.0.1', '--port', "$Port",
        '--database', ('"' + $database + '"'))
    $localServer = Start-Process -FilePath $Python -ArgumentList $serverArgs -WorkingDirectory $serverRoot `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $profile 'server.log') `
        -RedirectStandardError (Join-Path $profile 'server-errors.log') -PassThru
    $ready = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    while (-not $ready -and [DateTime]::UtcNow -lt $deadline) {
        $localServer.Refresh()
        if ($localServer.HasExited) { throw "Local server stopped. See $profile\server-errors.log" }
        $connection = [Net.Sockets.TcpClient]::new()
        try { $ready = $connection.ConnectAsync('127.0.0.1', $Port).Wait(250) -and $connection.Connected }
        catch { $ready = $false }
        finally { $connection.Dispose() }
        if (-not $ready) { Start-Sleep -Milliseconds 200 }
    }
    if (-not $ready) { throw "Local server did not start. See $profile\server-errors.log" }
    Write-Host 'Rabbit Lands is ready. Click Connect, then New Character to begin The Last Lantern.'
    Write-Host "Returning players: log in with the same local character. Saves: $database"
    & $Godot --path $clientRoot -- --dev-plain-tcp "--server=127.0.0.1" "--port=$Port"
    if ($LASTEXITCODE -ne 0) { throw "Godot exited with code $LASTEXITCODE" }
} finally {
    if ($localServer -and -not $localServer.HasExited) {
        Stop-Process -Id $localServer.Id -ErrorAction SilentlyContinue
    }
    $env:APPDATA = $savedAppData
    $env:LOCALAPPDATA = $savedLocalAppData
    $env:ELORIA_DATA_DIRECTORY = $savedTerrain
}
