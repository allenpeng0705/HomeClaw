# Build signal-cli for Windows from source.
# Requires: Git, JDK 17+ (Gradle). For signal-cli runtime, JRE 25 may be required; check signal-cli README.
# Optional: set JAVA_HOME to a JDK 17+ (or 25) before running, e.g. $env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-25.0.0"

$ErrorActionPreference = "Stop"
$SignalCliRepo = "https://github.com/AsamK/signal-cli.git"
$RepoRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
$BuildRoot = if ($env:SIGNAL_CLI_BUILD_ROOT) { $env:SIGNAL_CLI_BUILD_ROOT } else { Join-Path (Split-Path $RepoRoot -Parent) "signal-cli-build" }
# Use existing clone at <parent>\signal-cli if present (e.g. D:\mygithub\signal-cli)
$SiblingClone = Join-Path (Split-Path $RepoRoot -Parent) "signal-cli"
$CloneDir = if ((Test-Path (Join-Path $SiblingClone ".git"))) { $SiblingClone } else { Join-Path $BuildRoot "signal-cli" }
$OutputZip = Join-Path $BuildRoot "signal-cli-windows.zip"

# Gradle requires JVM 17+. Check before building.
$javaExe = $null
if ($env:JAVA_HOME) {
    $javaExe = Join-Path $env:JAVA_HOME "bin\java.exe"
}
if (-not ($javaExe -and (Test-Path $javaExe))) {
    $javaExe = (Get-Command java -ErrorAction SilentlyContinue).Source
}
if (-not $javaExe) {
    Write-Host "Java not found. Install JDK 17+ (e.g. Eclipse Temurin from https://adoptium.net/) and set JAVA_HOME."
    exit 1
}
try { $verOutput = & $javaExe -version 2>&1 | Out-String } catch { $verOutput = "$_" }
Write-Host $verOutput
if ($verOutput -match 'version "1\.([0-9]+)') {
    $major = [int]$Matches[1]
    if ($major -lt 17) {
        Write-Host "Gradle requires JVM 17 or later. Current is 1.$major. Set JAVA_HOME to a JDK 17+ (e.g. from https://adoptium.net/) and run again."
        exit 1
    }
} elseif ($verOutput -match 'version "([0-9]+)') {
    $major = [int]$Matches[1]
    if ($major -lt 17) {
        Write-Host "Gradle requires JVM 17 or later. Current is $major. Set JAVA_HOME to a JDK 17+ and run again."
        exit 1
    }
}

Write-Host "Build root: $BuildRoot"
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null

if (-not (Test-Path (Join-Path $CloneDir ".git"))) {
    Write-Host "Cloning signal-cli..."
    git clone --depth 1 $SignalCliRepo $CloneDir
} else {
    Write-Host "Repo already cloned at $CloneDir; pulling latest..."
    Push-Location $CloneDir
    git pull --depth 1
    Pop-Location
}

Write-Host "Building (installDist)..."
Push-Location $CloneDir
try {
    .\gradlew.bat installDist
} finally {
    Pop-Location
}

$InstallDir = Join-Path $CloneDir "build\install\signal-cli"
if (-not (Test-Path $InstallDir)) {
    Write-Error "Expected output not found: $InstallDir"
    exit 1
}

Write-Host "Windows build succeeded: $InstallDir"
Write-Host "Run with: $InstallDir\bin\signal-cli.bat -u +YOUR_NUMBER receive"

# Optional: create a zip for distribution
$zipParent = Split-Path $OutputZip -Parent
New-Item -ItemType Directory -Force -Path $zipParent | Out-Null
if (Get-Command Compress-Archive -ErrorAction SilentlyContinue) {
    Compress-Archive -Path (Join-Path $InstallDir "*") -DestinationPath $OutputZip -Force
    Write-Host "Zipped to: $OutputZip"
}
