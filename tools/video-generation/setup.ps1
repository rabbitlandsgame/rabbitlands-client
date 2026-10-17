param(
    [string]$BasePython = 'python',
    [switch]$SkipDownload
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$RuntimeRoot = Join-Path $ProjectRoot '.local\video-generation'
$VideoPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VideoPython)) {
    # Reuse a compatible base CUDA runtime when present; pinned video packages
    # install into this project's environment without changing the base Python.
    & $BasePython -m venv --system-site-packages (Join-Path $RuntimeRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the video Python environment.' }
}
& $VideoPython -m pip install --disable-pip-version-check 'torch==2.7.0+cu128' --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'CUDA PyTorch installation failed.' }
& $VideoPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Video dependency installation failed.' }
if (-not $SkipDownload) {
    & $VideoPython (Join-Path $PSScriptRoot 'video.py') download
    if ($LASTEXITCODE -ne 0) { throw 'Model download or checksum verification failed. Rerun to resume.' }
    & $VideoPython (Join-Path $PSScriptRoot 'video.py') doctor
    if ($LASTEXITCODE -ne 0) { throw 'Video environment check failed.' }
}
