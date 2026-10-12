# =============================================================================
#  Maritime Cyber Range -- Windows launcher.
#
#  FitGirl-style layout: this script ships next to the ~6 GB data file
#  "mcr-image.tar.gz" (NSIS cannot embed >2 GB into one .exe, so the image
#  rides alongside the small launcher .exe and this script finds it).
#
#  Run order:
#    1. ensure Docker Desktop is installed + running (offers to install it),
#    2. load mcr-image.tar.gz into Docker (one-time),
#    3. start the container and open the dashboard in the browser.
#
#  Params:
#    -DataDir  folder containing mcr-image.tar.gz (default: this script's folder)
#    -Action   run | stop | uninstall   (default: run)
# =============================================================================
param(
  [string]$DataDir = $PSScriptRoot,
  [ValidateSet('run','stop','uninstall')][string]$Action = 'run'
)
$ErrorActionPreference = 'Stop'
# native (docker) non-zero exits must NOT throw -- we check $LASTEXITCODE ourselves
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}
$Image     = 'mcr:latest'
$Container = 'mcr'
$Port      = 8080
$Url       = "http://localhost:$Port"
$Tarball   = Join-Path $DataDir 'mcr-image.tar.gz'

function Say  ($m){ Write-Host "[MCR] $m" -ForegroundColor Cyan }
function Warn ($m){ Write-Host "[MCR] $m" -ForegroundColor Yellow }
function Die  ($m){ Write-Host "[MCR] $m" -ForegroundColor Red; Read-Host 'Press Enter to close'; exit 1 }

function Have-Docker { $null -ne (Get-Command docker -ErrorAction SilentlyContinue) }
function Docker-Up   { try { docker info *> $null; return $true } catch { return $false } }

function Ensure-Docker {
  if (-not (Have-Docker)) {
    Warn 'Docker Desktop is not installed.'
    $a = Read-Host 'Install Docker Desktop now? (downloads the official installer, needs admin + a reboot) [y/N]'
    if ($a -notmatch '^[Yy]') { Die 'Docker is required. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and re-run.' }
    $inst = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'
    Say 'Downloading Docker Desktop installer ...'
    Invoke-WebRequest 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' -OutFile $inst
    Say 'Running the Docker Desktop installer (accept the UAC prompt) ...'
    Start-Process -Wait -Verb RunAs $inst -ArgumentList 'install','--quiet','--accept-license'
    Die 'Docker Desktop was installed. Please REBOOT, then run this launcher again.'
  }
  if (-not (Docker-Up)) {
    Say 'Starting Docker Desktop (this can take a minute the first time) ...'
    $dd = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $dd) { Start-Process $dd }
    for ($i=0; $i -lt 60; $i++) { if (Docker-Up) { break }; Start-Sleep 3 }
    if (-not (Docker-Up)) { Die 'Docker Desktop is installed but not running. Start it from the Start Menu and re-run.' }
  }
}

function Load-Image {
  docker image inspect $Image *> $null
  if ($LASTEXITCODE -eq 0) { Say "Image '$Image' already present -- skipping load."; return }
  if (-not (Test-Path $Tarball)) { Die "Data file not found: $Tarball  (keep mcr-image.tar.gz next to this launcher)." }
  Say 'Loading the simulator image (~21 GB uncompressed, one-time) ...'
  docker load -i $Tarball
  if ($LASTEXITCODE -ne 0) { Die 'docker load failed (out of disk? needs ~25 GB free).' }
  Say 'Image loaded.'
}

function Run-Container {
  docker rm -f $Container 2>$null | Out-Null
  Say 'Starting the Maritime Cyber Range ...'
  docker run -d --name $Container -p "$($Port):8080" $Image | Out-Null
  if ($LASTEXITCODE -ne 0) { Die "Could not start the container (is port $Port in use?)." }
  Say 'Waiting for the dashboard ...'
  for ($i=0; $i -lt 40; $i++) {
    try { Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3 *> $null; Say "Dashboard is up -> $Url"; Start-Process $Url; return } catch { Start-Sleep 3 }
  }
  Warn "The dashboard did not respond in time. Check:  docker logs $Container"
}

switch ($Action) {
  'run'       { Ensure-Docker; Load-Image; Run-Container; Say 'Leave this window; close the app later with:  docker rm -f mcr' }
  'stop'      { docker rm -f $Container 2>$null | Out-Null; Say 'Stopped.' }
  'uninstall' { docker rm -f $Container 2>$null | Out-Null; docker rmi $Image 2>$null | Out-Null; Say 'Uninstalled.' }
}
