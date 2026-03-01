# HomeClaw install script for Windows.
# Run from project root (existing clone) or from a parent directory (script will clone).
# Steps: Python (3.9+) -> Node.js -> [clone if needed] -> pip install -> llama.cpp -> GGUF/Ollama instructions -> open Portal.

$ErrorActionPreference = "Stop"
$RepoUrl = if ($env:HOMECLAW_REPO_URL) { $env:HOMECLAW_REPO_URL } else { "https://github.com/allenpeng0705/HomeClaw.git" }
$PortalUrl = "http://127.0.0.1:18472"

# Resolve project root
$InRepo = $false
$Root = ""

if (Test-Path "$PSScriptRoot\main.py") -and (Test-Path "$PSScriptRoot\requirements.txt") {
  $Root = $PSScriptRoot
  $InRepo = $true
  Write-Host "Using existing HomeClaw repo at: $Root"
} elseif (Test-Path "main.py") -and (Test-Path "requirements.txt") {
  $Root = (Get-Location).Path
  $InRepo = $true
  Write-Host "Using existing HomeClaw repo at: $Root"
} else {
  $CloneDir = "HomeClaw"
  if (Test-Path "$CloneDir\main.py") {
    $Root = (Join-Path (Get-Location).Path $CloneDir)
    $InRepo = $true
    Write-Host "Using existing clone at: $Root"
  } else {
    Write-Host "Cloning HomeClaw into $CloneDir ..."
    try {
      git clone $RepoUrl $CloneDir 2>&1
      if ($LASTEXITCODE -ne 0) { throw "git clone exited with $LASTEXITCODE" }
    } catch {
      Write-Host "Error: git clone failed. Check network, repo URL ($RepoUrl), and that you have git installed."
      Write-Host $_.Exception.Message
      exit 1
    }
    $Root = (Join-Path (Get-Location).Path $CloneDir)
  }
}

Set-Location $Root

# ----- Step 1: Python 3.9+ -----
Write-Host ""
Write-Host "=== Step 1: Python ==="
$PythonExe = $null
foreach ($p in @("py", "python3", "python")) {
  try {
    $v = & $p -3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $PythonExe = $p; break }
  } catch {}
  try {
    $v = & $p -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $PythonExe = $p; break }
  } catch {}
}
if (-not $PythonExe) {
  Write-Host "Python 3.9+ not found. Attempting to install..."
  try {
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements 2>$null
    $PythonExe = "py"
  } catch {}
  if (-not $PythonExe) {
    foreach ($p in @("py", "python")) {
      try {
        & $p -3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $PythonExe = $p; break }
      } catch {}
    }
  }
  if (-not $PythonExe) {
    Write-Host "Please install Python 3.9 or newer from https://www.python.org or run: winget install Python.Python.3.11"
    exit 1
  }
}
$pyVer = & $PythonExe --version 2>&1
Write-Host "OK: Python $pyVer"

# ----- Step 2: Node.js -----
Write-Host ""
Write-Host "=== Step 2: Node.js ==="
$NodeOk = $false
try {
  $nv = node --version 2>$null
  if ($LASTEXITCODE -eq 0) { Write-Host "OK: Node $nv"; $NodeOk = $true }
} catch {}
if (-not $NodeOk) {
  Write-Host "Node.js not found. Attempting to install..."
  try {
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements 2>$null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $nv = node --version 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "OK: Node $nv"; $NodeOk = $true }
  } catch {}
  if (-not $NodeOk) {
    Write-Host "Node.js could not be installed automatically. Install from https://nodejs.org and re-run if you need it. Continuing..."
  }
}

# ----- Step 5: pip install -r requirements.txt -----
Write-Host ""
Write-Host "=== Step 5: Python dependencies ==="
Set-Location $Root
$pipArgs = if ($PythonExe -eq "py") { @("-3", "-m", "pip", "install", "-q", "-r", "requirements.txt") } else { @("-m", "pip", "install", "-q", "-r", "requirements.txt") }
& $PythonExe $pipArgs
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed."; exit 1 }
Write-Host "OK: requirements installed"

# ----- Step 6a: llama.cpp -----
Write-Host ""
Write-Host "=== Step 6a: llama.cpp ==="
$LlamaOk = $false
try {
  $null = Get-Command llama-server -ErrorAction SilentlyContinue
  if ($?) { Write-Host "OK: llama-server already on PATH"; $LlamaOk = $true }
} catch {}
if (-not $LlamaOk) {
  try {
    winget install llama.cpp --accept-package-agreements --accept-source-agreements 2>$null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $null = Get-Command llama-server -ErrorAction SilentlyContinue
    if ($?) { Write-Host "OK: llama.cpp installed via Winget"; $LlamaOk = $true }
  } catch {}
}
if (-not $LlamaOk) {
  Write-Host "llama.cpp could not be installed via command line. You can use Method A - Copy binary into project:"
  Write-Host "  Download the executable for your platform from https://github.com/ggml-org/llama.cpp/releases"
  Write-Host "  (e.g. llama-b...-bin-win-cuda-12.4-x64.zip for Windows CUDA)."
  Write-Host "  Unzip and copy llama-server.exe into llama.cpp-master\<platform>\ in this repo"
  Write-Host "  (win_cpu, win_cuda, etc.). See llama.cpp-master\README.md for folder layout."
  Write-Host "  Or run: winget install llama.cpp"
}

# ----- Step 6b: GGUF / Ollama instructions -----
Write-Host ""
Write-Host "=== Step 6b: GGUF models / Ollama ==="
Write-Host "Local GGUF models are used by llama.cpp. To add more:"
Write-Host "  Download GGUF models from Hugging Face (huggingface.co)."
Write-Host "  In China you can use ModelScope (modelscope.cn) or HF Mirror (https://hf-mirror.com/)."
Write-Host "  Put .gguf files in the models folder and add entries in config\llm.yml under local_models with path set to the filename (e.g. model.gguf)."
Write-Host ""
Write-Host "Alternatively use Ollama: install from https://ollama.com then run: python -m main ollama pull <model> and set main_llm via Portal or config."

# ----- Step 7: Done; open Portal -----
Write-Host ""
Write-Host "=== Installation complete ==="
Write-Host "Starting Portal and opening browser at $PortalUrl ..."
Set-Location $Root
$portalArgs = if ($PythonExe -eq "py") { @("-3", "-m", "main", "portal", "--no-open-browser") } else { @("-m", "main", "portal", "--no-open-browser") }
Start-Process -FilePath $PythonExe -ArgumentList $portalArgs -NoNewWindow
Start-Sleep -Seconds 3
Start-Process $PortalUrl
Write-Host "Portal started. To run again later: cd $Root; $PythonExe -m main portal"
