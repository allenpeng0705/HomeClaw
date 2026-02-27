# Build and run HomeClaw Companion on Windows
# Usage: .\run_windows.ps1   (from this directory, or run from repo root)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "HomeClaw Companion - Windows" -ForegroundColor Cyan
Write-Host ""

# Check Flutter
if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) {
    Write-Host "Flutter not found in PATH. Install Flutter from https://flutter.dev" -ForegroundColor Red
    exit 1
}

Write-Host "Running: flutter pub get" -ForegroundColor Yellow
flutter pub get
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Running: flutter run -d windows" -ForegroundColor Yellow
flutter run -d windows
exit $LASTEXITCODE
