# Download nuget.exe so flutter_tts can build on Windows.
# Run from repo root or from clients/homeclaw_companion:
#   .\scripts\ensure_nuget.ps1
# Then (in the same session) run: flutter run -d windows
# Or add the tools folder to your system PATH permanently.

$ErrorActionPreference = "Stop"
$nugetUrl = "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"

# Resolve project root (companion app directory)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$companionDir = Split-Path -Parent $scriptDir
$toolsDir = Join-Path $companionDir "tools"

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir | Out-Null
}

$nugetPath = Join-Path $toolsDir "nuget.exe"
if (-not (Test-Path $nugetPath)) {
    Write-Host "Downloading nuget.exe to $toolsDir ..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $nugetUrl -OutFile $nugetPath -UseBasicParsing
    } catch {
        Write-Host "Download failed. Get it manually: $nugetUrl" -ForegroundColor Red
        Write-Host "Save as: $nugetPath" -ForegroundColor Red
        exit 1
    }
    Write-Host "Downloaded: $nugetPath" -ForegroundColor Green
} else {
    Write-Host "nuget.exe already at: $nugetPath" -ForegroundColor Green
}

# Add to PATH for this session so CMake can find it
$toolsDirAbs = (Resolve-Path $toolsDir).Path
if ($env:PATH -notlike "*$toolsDirAbs*") {
    $env:PATH = "$toolsDirAbs;$env:PATH"
    Write-Host "Added to PATH for this session. Run: flutter run -d windows" -ForegroundColor Cyan
} else {
    Write-Host "Already on PATH. Run: flutter run -d windows" -ForegroundColor Cyan
}
