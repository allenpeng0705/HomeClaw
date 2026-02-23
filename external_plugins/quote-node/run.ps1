# Start Quote (Node.js) plugin server and register with Core (one command).
# Run from project root:  .\external_plugins\quote-node\run.ps1
$ErrorActionPreference = "Stop"
$PluginDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path (Split-Path -Parent $PluginDir) ".run_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$env:CORE_URL = if ($env:CORE_URL) { $env:CORE_URL } else { "http://127.0.0.1:9000" }

$pidFile = Join-Path $LogDir "quote-node.pid"
$logFile = Join-Path $LogDir "quote-node.log"
if (-not (Test-Path (Join-Path $PluginDir "node_modules"))) {
  Write-Host "[quote-node] Installing npm dependencies..."
  Push-Location $PluginDir; npm install --no-fund --no-audit 2>$null; Pop-Location
}
if (Test-Path $pidFile) {
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
    Write-Host "[quote-node] Already running (PID $oldPid). Registering..."
    Push-Location $PluginDir; node register.js; Pop-Location
    Write-Host "Done."
    exit 0
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "[quote-node] Starting server on port 3111..."
$p = Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $PluginDir -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"
$p.Id | Out-File $pidFile -Force
Start-Sleep -Seconds 1
$n = 0
while ($n -lt 20) {
  try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:3111/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { break } } catch {}
  $n++; Start-Sleep -Seconds 1
}
if ($n -ge 20) { Write-Host "[quote-node] Timeout waiting for server. Check $logFile" -ForegroundColor Red; exit 1 }
Write-Host "[quote-node] Registering with Core..."
Push-Location $PluginDir; node register.js; Pop-Location
Write-Host "Done. Quote (Node.js) plugin running (PID $($p.Id))."
