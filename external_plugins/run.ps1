# Start external plugin servers and register them with Core (one step).
# Run from project root after Core is running:  .\external_plugins\run.ps1
# Or specific plugins:  .\external_plugins\run.ps1 -Plugins time,companion,quote-node
# Requires: Python, Node (for quote-node), Go (for time-go), Maven (for quote-java).

param(
    [string[]] $Plugins = @("time", "companion", "quote-node", "time-go", "quote-java"),
    [string] $CoreUrl = $env:CORE_URL
)
if (-not $CoreUrl) { $CoreUrl = "http://127.0.0.1:9000" }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogDir = Join-Path $ScriptDir ".run_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Wait-ForHealth {
    param([int]$Port, [string]$Name, [int]$TimeoutSec = 20)
    $url = "http://127.0.0.1:$Port/health"
    $n = 0
    while ($n -lt $TimeoutSec) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        $n++; Start-Sleep -Seconds 1
    }
    Write-Host "  $Name : timeout waiting for port $Port" -ForegroundColor Red
    return $false
}

function Run-One {
    param([string]$Name, [int]$Port, [string]$StartExe, [string[]]$StartArgs, [string]$StartCwd, [string]$RegisterExe, [string[]]$RegisterArgs, [string]$RegisterCwd)
    $pidFile = Join-Path $LogDir "$Name.pid"
    $logFile = Join-Path $LogDir "$Name.log"
    if (Test-Path $pidFile) {
        $oldPid = (Get-Content $pidFile -ErrorAction SilentlyContinue) -replace '\s', ''
        if ($oldPid -match '^\d+$') {
            $pidInt = [int]$oldPid
            if (Get-Process -Id $pidInt -ErrorAction SilentlyContinue) {
                Write-Host "[$Name] Already running (PID $pidInt). Registering..."
                Push-Location $RegisterCwd; & $RegisterExe @RegisterArgs; Pop-Location
                return
            }
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[$Name] Starting server on port $Port..."
    $p = Start-Process -FilePath $StartExe -ArgumentList $StartArgs -WorkingDirectory $StartCwd -PassThru -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError "$logFile.err"
    $p.Id | Out-File $pidFile -Force
    Start-Sleep -Seconds 1
    if (-not (Wait-ForHealth -Port $Port -Name $Name)) {
        Write-Host "[$Name] Server failed to become ready. Check $logFile" -ForegroundColor Red
        return
    }
    Write-Host "[$Name] Registering with Core..."
    Push-Location $RegisterCwd
    & $RegisterExe @RegisterArgs
    Pop-Location
}

$env:CORE_URL = $CoreUrl
Push-Location $Root
try {
    Write-Host "Core URL: $CoreUrl"
    Write-Host "Plugins:  $($Plugins -join ', ')"
    Write-Host "Logs:     $LogDir"
    Write-Host ""

    if ($Plugins -contains "time") {
        Run-One -Name "time" -Port 3102 -StartExe "python" -StartArgs @("-m","external_plugins.time.server") -StartCwd $Root `
            -RegisterExe "python" -RegisterArgs @("-m","external_plugins.time.register") -RegisterCwd $Root
    }
    if ($Plugins -contains "companion") {
        Run-One -Name "companion" -Port 3103 -StartExe "python" -StartArgs @("-m","external_plugins.companion.server") -StartCwd $Root `
            -RegisterExe "python" -RegisterArgs @("-m","external_plugins.companion.register") -RegisterCwd $Root
    }
    if ($Plugins -contains "quote-node") {
        $qnDir = Join-Path $ScriptDir "quote-node"
        if (-not (Test-Path (Join-Path $qnDir "node_modules"))) {
            Write-Host "[quote-node] Installing npm dependencies..."
            Push-Location $qnDir; npm install --no-fund --no-audit 2>$null; Pop-Location
        }
        Run-One -Name "quote-node" -Port 3111 -StartExe "node" -StartArgs @("server.js") -StartCwd $qnDir `
            -RegisterExe "node" -RegisterArgs @("register.js") -RegisterCwd $qnDir
    }
    if ($Plugins -contains "time-go") {
        $tgDir = Join-Path $ScriptDir "time-go"
        Run-One -Name "time-go" -Port 3112 -StartExe "go" -StartArgs @("run",".") -StartCwd $tgDir `
            -RegisterExe "bash" -RegisterArgs @("register.sh") -RegisterCwd $tgDir
    }
    if ($Plugins -contains "quote-java") {
        $qjDir = Join-Path $ScriptDir "quote-java"
        Run-One -Name "quote-java" -Port 3113 -StartExe "mvn" -StartArgs @("compile","exec:java","-Dexec.mainClass=QuotePlugin") -StartCwd $qjDir `
            -RegisterExe "bash" -RegisterArgs @("register.sh") -RegisterCwd $qjDir
    }

    Write-Host ""
    Write-Host "Done. Requested plugins are running and registered. PIDs in $LogDir\*.pid"
} finally {
    Pop-Location
}
