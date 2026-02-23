# Start Time plugin server and register with Core (one command).
# Run from project root:  .\external_plugins\time\run.ps1
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$LogDir = Join-Path (Split-Path -Parent $ScriptDir) ".run_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$env:CORE_URL = if ($env:CORE_URL) { $env:CORE_URL } else { "http://127.0.0.1:9000" }

$pidFile = Join-Path $LogDir "time.pid"
$logFile = Join-Path $LogDir "time.log"
if (Test-Path $pidFile) {
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
    Write-Host "[time] Already running (PID $oldPid). Registering..."
    Push-Location $Root; python -m external_plugins.time.register; Pop-Location
    Write-Host "Done."
    exit 0
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "[time] Starting server on port 3102..."
$p = Start-Process -FilePath "python" -ArgumentList "-m","external_plugins.time.server" -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"
$p.Id | Out-File $pidFile -Force
Start-Sleep -Seconds 1
$n = 0
while ($n -lt 20) {
  try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:3102/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { break } } catch {}
  $n++; Start-Sleep -Seconds 1
}
if ($n -ge 20) { Write-Host "[time] Timeout waiting for server. Check $logFile" -ForegroundColor Red; exit 1 }
Write-Host "[time] Registering with Core..."
Push-Location $Root; python -m external_plugins.time.register; Pop-Location
Write-Host "Done. Time plugin running (PID $($p.Id))."
