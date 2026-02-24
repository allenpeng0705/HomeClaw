# Start Friends plugin server and register with Core (one command).
# Run from project root:  .\external_plugins\friends\run.ps1
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$LogDir = Join-Path (Split-Path -Parent $ScriptDir) ".run_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$env:CORE_URL = if ($env:CORE_URL) { $env:CORE_URL } else { "http://127.0.0.1:9000" }
$Port = if ($env:FRIENDS_PORT) { $env:FRIENDS_PORT } else { "3103" }

$pidFile = Join-Path $LogDir "friends.pid"
$logFile = Join-Path $LogDir "friends.log"
if (Test-Path $pidFile) {
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
    Write-Host "[friends] Already running (PID $oldPid). Registering..."
    Push-Location $Root; python -m external_plugins.friends.register; Pop-Location
    Write-Host "Done."
    exit 0
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
Write-Host "[friends] Starting server on port $Port..."
$p = Start-Process -FilePath "python" -ArgumentList "-m","external_plugins.friends.server" -WorkingDirectory $Root -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"
$p.Id | Out-File $pidFile -Force
Start-Sleep -Seconds 1
$n = 0
while ($n -lt 20) {
  try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue; if ($r.StatusCode -eq 200) { break } } catch {}
  $n++; Start-Sleep -Seconds 1
}
if ($n -ge 20) { Write-Host "[friends] Timeout waiting for server. Check $logFile" -ForegroundColor Red; exit 1 }
Write-Host "[friends] Registering with Core..."
Push-Location $Root; python -m external_plugins.friends.register; Pop-Location
Write-Host "Done. Friends plugin running (PID $($p.Id))."
