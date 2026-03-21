# HomeClaw install script for Windows.
# Run from project root (existing clone) or from a parent directory (script will clone).
# Steps (same as install.sh): Python (3.9+) -> Node.js -> tsx -> ClawHub -> [clone if needed] -> VMPrint -> pip install -> Cognee deps (cognee in vendor/) -> document stack -> MemOS (vendor/memos) -> llama.cpp -> GGUF/Ollama -> open Portal.
#
# If you see "cannot be loaded... not digitally signed" (execution policy):
#   Easiest: run install.bat instead (it uses Bypass automatically).
#   Or: powershell -ExecutionPolicy Bypass -File .\install.ps1
#   Or: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser   (then run .\install.ps1 again)

$ErrorActionPreference = "Stop"
$RepoUrl = if ($env:HOMECLAW_REPO_URL) { $env:HOMECLAW_REPO_URL } else { "https://github.com/allenpeng0705/HomeClaw.git" }
$PortalUrl = "http://127.0.0.1:18472"

Write-Host "=============================================="
Write-Host "  HomeClaw Installer (Windows)"
Write-Host "=============================================="
Write-Host ""
Write-Host "Tip: If you see 'not digitally signed' when running .\install.ps1 directly, use install.bat or run: powershell -ExecutionPolicy Bypass -File .\install.ps1"
Write-Host ""

# Resolve project root
$InRepo = $false
$Root = ""

if ((Test-Path "$PSScriptRoot\main.py") -and (Test-Path "$PSScriptRoot\requirements.txt")) {
  $Root = $PSScriptRoot
  $InRepo = $true
  Write-Host "Using existing HomeClaw repo at: $Root"
} elseif ((Test-Path "main.py") -and (Test-Path "requirements.txt")) {
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
    Write-Host "Cloning HomeClaw into $CloneDir from GitHub..."
    Write-Host "  Repository: $RepoUrl"
    Write-Host "  Shallow clone (--depth 1). This may take 1-3 minutes; progress will stream below."
    Write-Host ""
    try {
      # Run git without redirecting stderr so progress streams to the console (avoids "blocking" with no output)
      & git clone --progress --depth 1 $RepoUrl $CloneDir
      if ($LASTEXITCODE -ne 0) { throw "git clone exited with $LASTEXITCODE" }
      Write-Host ""
      Write-Host "Clone complete. Continuing with setup..."
    } catch {
      Write-Host "Error: git clone failed. Check network, repo URL ($RepoUrl), and that you have git installed."
      Write-Host $_.Exception.Message
      exit 1
    }
    $Root = (Join-Path (Get-Location).Path $CloneDir)
  }
}

if (-not $Root -or -not (Test-Path -LiteralPath $Root -PathType Container)) {
  Write-Host "Error: could not determine project root."
  exit 1
}
Set-Location $Root
Write-Host "Working directory: $Root"
Write-Host ""

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
try {
  & $PythonExe -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Note: Python < 3.10 — optional MCP client (mcp) is not installed. Use 3.10+ for mcp_call / mcp_list_tools, or see docs/mcp.md."
  }
} catch {}

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

# ----- Step 2b: TypeScript runner (for .ts skill scripts) -----
# Skills can use .js (node) or .ts (tsx/ts-node). Node is required for .js; tsx or ts-node for .ts.
Write-Host ""
Write-Host "=== Step 2b: TypeScript runner (for .ts skill scripts) ==="
$TsRunnerOk = $false
if ($NodeOk) {
  try {
    $null = Get-Command tsx -ErrorAction SilentlyContinue
    if ($?) { Write-Host "OK: tsx (for .ts skills)"; $TsRunnerOk = $true }
  } catch {}
  if (-not $TsRunnerOk) {
    try {
      $null = Get-Command ts-node -ErrorAction SilentlyContinue
      if ($?) { Write-Host "OK: ts-node (for .ts skills)"; $TsRunnerOk = $true }
    } catch {}
  }
  if (-not $TsRunnerOk) {
    Write-Host "tsx/ts-node not found. Installing tsx (recommended for running TypeScript skill scripts)..."
    try {
      npm install -g tsx 2>$null
      if ($LASTEXITCODE -eq 0) { Write-Host "OK: tsx installed (for .ts skills)"; $TsRunnerOk = $true }
    } catch {}
    if (-not $TsRunnerOk) {
      Write-Host "To run TypeScript (.ts) skill scripts later, install one of: npm install -g tsx  (recommended), or  npm install -g ts-node"
    }
  }
} else {
  Write-Host "Node.js not available; skipping. For .ts skills you need: node on PATH, then npm install -g tsx (or ts-node)."
}

# ----- Step 2c: ClawHub CLI (for skill search/install from Portal and Companion) -----
Write-Host ""
Write-Host "=== Step 2c: ClawHub CLI (skill search/install) ==="
$ClawhubOk = $false
try {
  $null = Get-Command clawhub -ErrorAction SilentlyContinue
  if ($?) { Write-Host "OK: clawhub already on PATH"; $ClawhubOk = $true }
} catch {}
if (-not $ClawhubOk) {
  if ($NodeOk) {
    Write-Host "Installing ClawHub CLI (npm i -g clawhub)..."
    try {
      npm install -g clawhub 2>$null
      if ($LASTEXITCODE -eq 0) { Write-Host "OK: clawhub installed (for skill search/install from Portal and Companion)"; $ClawhubOk = $true }
    } catch {}
    if (-not $ClawhubOk) {
      Write-Host "ClawHub CLI install failed. To install later: npm i -g clawhub"
    }
  } else {
    Write-Host "npm not available; skipping. For skill search/install from Companion/Portal, install Node.js then: npm i -g clawhub"
  }
}

# ----- Step 2d: Dev CLIs (optional): Cursor CLI + Claude Code CLI + Trae Agent -----
# Off by default. Enable with:
#   $env:HOMECLAW_INSTALL_CURSOR_CLI="1"; .\install.ps1
#   $env:HOMECLAW_INSTALL_CLAUDE_CODE="1"; .\install.ps1
#   $env:HOMECLAW_INSTALL_TRAE_AGENT="1"; .\install.ps1
Write-Host ""
Write-Host "=== Step 2d: Dev CLIs (optional) ==="
$InstallCursorCli = ($env:HOMECLAW_INSTALL_CURSOR_CLI -eq "1")
$InstallClaudeCode = ($env:HOMECLAW_INSTALL_CLAUDE_CODE -eq "1")
$InstallTraeAgent = ($env:HOMECLAW_INSTALL_TRAE_AGENT -eq "1")

if ($InstallCursorCli) {
  $hasAgent = $false
  $hasCursor = $false
  try { $null = Get-Command agent -ErrorAction SilentlyContinue; if ($?) { $hasAgent = $true } } catch {}
  try { $null = Get-Command cursor -ErrorAction SilentlyContinue; if ($?) { $hasCursor = $true } } catch {}
  if ($hasAgent -and $hasCursor) {
    Write-Host "OK: Cursor CLI already installed (agent + cursor found on PATH)"
  } else {
    Write-Host "Installing Cursor CLI (agent/cursor)..."
    try {
      irm "https://cursor.com/install?win32=true" | iex
      Write-Host "OK: Cursor CLI installer finished"
    } catch {
      Write-Host "Warning: Cursor CLI install failed. See https://cursor.com/docs/cli"
    }
  }
} else {
  Write-Host "Skipping Cursor CLI install (set HOMECLAW_INSTALL_CURSOR_CLI=1 to enable)"
}

if ($InstallClaudeCode) {
  $hasClaude = $false
  try { $null = Get-Command claude -ErrorAction SilentlyContinue; if ($?) { $hasClaude = $true } } catch {}
  if ($hasClaude) {
    Write-Host "OK: Claude Code CLI already installed (claude found on PATH)"
  } else {
    Write-Host "Installing Claude Code CLI (claude)..."
    try {
      irm "https://claude.ai/install.ps1" | iex
      Write-Host "OK: Claude Code CLI installer finished"
    } catch {
      Write-Host "Warning: Claude Code CLI install failed. See https://docs.claude.com/en/docs/claude-code/setup"
    }
  }
} else {
  Write-Host "Skipping Claude Code CLI install (set HOMECLAW_INSTALL_CLAUDE_CODE=1 to enable)"
}

if ($InstallTraeAgent) {
  $TraeAgentDir = Join-Path $Root "tools\trae-agent"
  $TraeAgentVenv = Join-Path $TraeAgentDir ".venv"
  $TraeAgentPyproject = Join-Path $TraeAgentDir "pyproject.toml"
  if ((Test-Path $TraeAgentVenv) -and (Test-Path $TraeAgentPyproject)) {
    try {
      Push-Location $TraeAgentDir
      $null = Get-Command uv -ErrorAction SilentlyContinue
      if ($?) {
        $uvRun = & uv run trae-cli --help 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "OK: Trae Agent already installed at $TraeAgentDir (trae-cli in venv)" }
        else { & uv sync --all-extras 2>$null; Write-Host "OK: Trae Agent updated at $TraeAgentDir" }
      } else { Write-Host "uv not found. Install with: pip install uv. Then run: cd $TraeAgentDir; uv sync --all-extras" }
    } finally { Pop-Location -ErrorAction SilentlyContinue }
  } else {
    Write-Host "Installing Trae Agent (clone + uv sync)..."
    $hasGit = $false; $hasUv = $false
    try { $null = Get-Command git -ErrorAction SilentlyContinue; if ($?) { $hasGit = $true } } catch {}
    try { $null = Get-Command uv -ErrorAction SilentlyContinue; if ($?) { $hasUv = $true } } catch {}
    if (-not $hasUv) {
      Write-Host "Installing uv (required for Trae Agent)..."
      & $PythonExe -m pip install -q uv 2>$null
      $null = Get-Command uv -ErrorAction SilentlyContinue; if ($?) { $hasUv = $true }
    }
    if ($hasGit -and $hasUv) {
      New-Item -ItemType Directory -Path (Join-Path $Root "tools") -Force | Out-Null
      if (Test-Path (Join-Path $TraeAgentDir ".git")) {
        Set-Location $TraeAgentDir
        git pull --quiet 2>$null
        & uv sync --all-extras 2>$null
        if (-not (Test-Path (Join-Path $TraeAgentDir "trae_config.yaml")) -and (Test-Path (Join-Path $TraeAgentDir "trae_config.yaml.example"))) {
          Copy-Item -Path (Join-Path $TraeAgentDir "trae_config.yaml.example") -Destination (Join-Path $TraeAgentDir "trae_config.yaml")
          Write-Host "  Created trae_config.yaml from example. Edit it and add your API key."
        }
        Write-Host "OK: Trae Agent at $TraeAgentDir (set cursor_bridge_trae_agent_path to .venv\Scripts\trae-cli.exe and cursor_bridge_trae_agent_config to trae_config.yaml in config)"
        Set-Location $Root
      } else {
        & git clone --progress --depth 1 https://github.com/bytedance/trae-agent.git $TraeAgentDir 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Host "Warning: Trae Agent clone failed." } else {
          Set-Location $TraeAgentDir
          & uv sync --all-extras 2>$null
          if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: Trae Agent installed at $TraeAgentDir"
            $exampleConfig = Join-Path $TraeAgentDir "trae_config.yaml.example"
            $configPath = Join-Path $TraeAgentDir "trae_config.yaml"
            if (-not (Test-Path $configPath) -and (Test-Path $exampleConfig)) {
              Copy-Item -Path $exampleConfig -Destination $configPath
              Write-Host "  Created $TraeAgentDir\trae_config.yaml from example. Edit it and add your API key (see repo README)."
            }
            $venvCli = Join-Path $TraeAgentDir ".venv\Scripts\trae-cli.exe"
            if (Test-Path $venvCli) { Write-Host "  Set in config: cursor_bridge_trae_agent_path = $venvCli , cursor_bridge_trae_agent_config = $configPath" }
          } else { Write-Host "Warning: uv sync failed in $TraeAgentDir" }
          Set-Location $Root
        }
      }
    } else {
      Write-Host "Skipping Trae Agent (need git and uv). Install uv: pip install uv. Then: `$env:HOMECLAW_INSTALL_TRAE_AGENT=`"1`"; .\install.ps1"
    }
  }
  # Apply HomeClaw patch for Minimax / Anthropic-compatible backends (standard tool format)
  $TraePatch = Join-Path $Root "patches\trae-agent-anthropic-client-minimax.patch"
  $AnthropicClient = Join-Path $TraeAgentDir "trae_agent\utils\llm_clients\anthropic_client.py"
  if ((Test-Path $TraePatch) -and (Test-Path (Join-Path $TraeAgentDir "trae_agent"))) {
    $alreadyPatched = Get-Content $AnthropicClient -Raw -ErrorAction SilentlyContinue | Select-String -Pattern "use_standard_tools_only" -Quiet
    if (-not $alreadyPatched) {
      Push-Location $TraeAgentDir
      git apply $TraePatch 2>$null
      if ($LASTEXITCODE -eq 0) { Write-Host "  Applied Minimax/compat patch to trae-agent" } else { Write-Host "  Note: could not apply trae-agent patch (already applied or upstream changed)." }
      Pop-Location
    }
  }
  $TraeLakeviewPatch = Join-Path $Root "patches\trae-agent-lakeview-index-fix.patch"
  $LakeviewPy = Join-Path $TraeAgentDir "trae_agent\utils\lake_view.py"
  if ((Test-Path $TraeLakeviewPatch) -and (Test-Path $LakeviewPy)) {
    $lakeviewPatched = Get-Content $LakeviewPy -Raw -ErrorAction SilentlyContinue | Select-String -Pattern "if not matched_tags:" -Quiet
    if (-not $lakeviewPatched) {
      Push-Location $TraeAgentDir
      git apply $TraeLakeviewPatch 2>$null
      if ($LASTEXITCODE -eq 0) { Write-Host "  Applied lakeview index-fix patch to trae-agent" } else { Write-Host "  Note: could not apply trae-agent lakeview patch." }
      Pop-Location
    }
  }
} else {
  Write-Host "Skipping Trae Agent install (set HOMECLAW_INSTALL_TRAE_AGENT=1 to enable)"
}

# ----- Step 4b: VMPrint (Markdown to PDF tool) -----
Write-Host ""
Write-Host "=== Step 4b: VMPrint (Markdown to PDF) ==="
$VmprintDir = Join-Path $Root "tools\vmprint"
$VmprintMain = Join-Path $Root "tools\vmprint-main"
# If user downloaded GitHub ZIP, folder is vmprint-main; rename to vmprint so config path works
if ((Test-Path $VmprintMain) -and -not (Test-Path $VmprintDir)) {
  Write-Host "Renaming tools\vmprint-main to tools\vmprint ..."
  try {
    Rename-Item -Path $VmprintMain -NewName "vmprint" -ErrorAction Stop
  } catch {
    Write-Host "Warning: Could not rename vmprint-main to vmprint. You can rename manually or re-run install."
  }
}
$VmprintOk = (Test-Path (Join-Path $VmprintDir "draft2final")) -and (Test-Path (Join-Path $VmprintDir "package.json"))
if ($VmprintOk) {
  Write-Host "OK: VMPrint already at tools\vmprint"
} else {
  try {
    $null = Get-Command git -ErrorAction SilentlyContinue
    if ($?) {
      New-Item -ItemType Directory -Path (Join-Path $Root "tools") -Force | Out-Null
      if (Test-Path (Join-Path $VmprintDir ".git")) {
        Write-Host "Updating VMPrint at tools\vmprint ..."
        Set-Location $VmprintDir; git pull --quiet 2>$null
      } else {
        Write-Host "Cloning VMPrint from GitHub into tools\vmprint (optional Markdown-to-PDF tool)..."
        & git clone --progress --depth 1 https://github.com/cosmiciron/vmprint.git $VmprintDir
      }
      if ((Test-Path (Join-Path $VmprintDir "draft2final")) -and (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Host "Installing VMPrint dependencies (npm install) ..."
        Set-Location $VmprintDir; npm install --silent 2>$null
        if (Test-Path (Join-Path $VmprintDir "node_modules")) {
          Write-Host "Building VMPrint workspaces (transmuters then draft2final) ..."
          npm run build --workspace=@vmprint/transmuter-mkd-mkd --workspace=@vmprint/transmuter-mkd-academic --workspace=@vmprint/transmuter-mkd-literature --workspace=@vmprint/transmuter-mkd-manuscript --workspace=@vmprint/transmuter-mkd-screenplay 2>$null
          npm run build --workspace=draft2final 2>$null
          Write-Host "OK: VMPrint installed at tools\vmprint"
        } else {
          Write-Host "VMPrint clone present; run manually: cd $VmprintDir; npm install"
        }
      } elseif (Test-Path (Join-Path $VmprintDir "draft2final")) {
        Write-Host "VMPrint cloned; Node not found. Install from https://nodejs.org then run: cd $VmprintDir; npm install"
      } else {
        Write-Host "VMPrint clone skipped. Markdown-to-PDF will use pandoc/weasyprint if available."
      }
    } else {
      Write-Host "VMPrint skipped (git not found). Markdown-to-PDF will use pandoc or weasyprint if available."
    }
  } catch {
    Write-Host "VMPrint skipped. Markdown-to-PDF will use pandoc or weasyprint if available."
  } finally {
    Set-Location $Root
  }
}

# ----- Step 5: pip install -r requirements.txt -----
Write-Host ""
Write-Host "=== Step 5: Python dependencies ==="
Set-Location $Root
if (Test-Path (Join-Path $Root ".venv\Scripts\Activate.ps1")) {
  Write-Host "Using existing .venv"
  try { . (Join-Path $Root ".venv\Scripts\Activate.ps1") } catch {}
  if (Test-Path (Join-Path $Root ".venv\Scripts\python.exe")) {
    $PythonExe = (Join-Path $Root ".venv\Scripts\python.exe")
  }
  if (($env:VIRTUAL_ENV -replace '[\\/]+$','') -eq ((Join-Path $Root ".venv") -replace '[\\/]+$','')) {
    Write-Host "OK: using venv Python: $PythonExe"
    $venvMm = & $PythonExe -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
    if ($venvMm) { Write-Host "  (.venv is Python $venvMm — pip uses this, not necessarily your system default.)" }
    & $PythonExe -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Warning: .venv is Python $venvMm (< 3.10). Optional package 'mcp' is skipped."
      Write-Host "  Recreate with Python 3.12:  cd $Root; Remove-Item -Recurse -Force .venv; py -3.12 -m venv .venv; .\install.ps1"
    }
  } else {
    Write-Host "Warning: .venv exists but activation did not switch interpreter. Current Python: $PythonExe"
  }
}
# Shared pip constraints for deterministic dependency resolution.
$PipConstraints = Join-Path $Root "requirements-constraints.txt"
if (-not (Test-Path $PipConstraints)) { $PipConstraints = $null }
# Upgrade pip first (old pip can cause 403 with some mirrors)
$pipUpgradeArgs = if ($PythonExe -eq "py") { @("-3", "-m", "pip", "install", "-q", "--upgrade", "pip") } else { @("-m", "pip", "install", "-q", "--upgrade", "pip") }
& $PythonExe $pipUpgradeArgs 2>$null
$pipArgs = if ($PythonExe -eq "py") { @("-3", "-m", "pip", "install", "-q", "-r", "requirements.txt") } else { @("-m", "pip", "install", "-q", "-r", "requirements.txt") }
if ($PipConstraints) { $pipArgs += @("-c", $PipConstraints) }
& $PythonExe $pipArgs
if ($LASTEXITCODE -ne 0) {
  Write-Host "First attempt failed. Retrying automatically with official PyPI (ignoring mirror config)..."
  Write-Host "This may take a few minutes (downloading from pypi.org). You will see progress below."
  $env:PIP_INDEX_URL = $null
  $env:PIP_EXTRA_INDEX_URL = $null
  # Retry without -q so user sees download/install progress and knows it is not stuck
  $pipRetryArgs = if ($PythonExe -eq "py") { @("-3", "-m", "pip", "install", "-r", "requirements.txt", "-i", "https://pypi.org/simple") } else { @("-m", "pip", "install", "-r", "requirements.txt", "-i", "https://pypi.org/simple") }
  if ($PipConstraints) { $pipRetryArgs += @("-c", $PipConstraints) }
  & $PythonExe $pipRetryArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: pip install failed."
    Write-Host "  If you saw 403 Forbidden: your pip index (e.g. mirror) may be blocking. Try:"
    Write-Host "    $PythonExe -m pip install -r requirements.txt -i https://pypi.org/simple"
    Write-Host "  If you see permission errors: $PythonExe -m pip install --user -r requirements.txt"
    exit 1
  }
}
Write-Host "OK: requirements installed"

# ----- Step 5b: Cognee dependencies (for memory backend) -----
# Cognee is the default memory backend. Cognee is vendored in vendor/cognee; we only
# install its dependencies here. Do not run "pip install cognee".
Write-Host ""
Write-Host "=== Step 5b: Cognee dependencies (memory backend) ==="
$cogneeDepsPath = Join-Path $Root "requirements-cognee-deps.txt"
if (Test-Path $cogneeDepsPath) {
  Write-Host "Installing Cognee dependencies (safe mode: avoid overriding core deps like openai/litellm)..."
  $env:PIP_INDEX_URL = $null
  $env:PIP_EXTRA_INDEX_URL = $null
  $cogneeDepsArgs = if ($PythonExe -eq "py") { @("-3", "-m", "pip", "install", "--no-deps", "-r", $cogneeDepsPath, "-i", "https://pypi.org/simple") } else { @("-m", "pip", "install", "--no-deps", "-r", $cogneeDepsPath, "-i", "https://pypi.org/simple") }
  if ($PipConstraints) { $cogneeDepsArgs += @("-c", $PipConstraints) }
  & $PythonExe $cogneeDepsArgs
  if ($LASTEXITCODE -eq 0) { Write-Host "OK: Cognee direct dependencies installed (without transitive downgrades)" } else { Write-Host "Cognee deps install failed or skipped. To retry: pip install --no-deps -r requirements-cognee-deps.txt -i https://pypi.org/simple" }
} else {
  Write-Host "requirements-cognee-deps.txt not found; skipping."
}

# ----- Step 5c: Document stack (unstructured, opencv) — separate to avoid backtracking -----
Write-Host ""
Write-Host "=== Step 5c: Document support (document_read: PDF, Word, images) ==="
if (Test-Path (Join-Path $Root "requirements-document.txt")) {
  Write-Host "Installing document stack (pinned versions)..."
  $env:PIP_INDEX_URL = $null
  $env:PIP_EXTRA_INDEX_URL = $null
  $docArgs = if ($PythonExe -eq "py") { @("-3", "-m", "pip", "install", "-r", (Join-Path $Root "requirements-document.txt"), "-i", "https://pypi.org/simple") } else { @("-m", "pip", "install", "-r", (Join-Path $Root "requirements-document.txt"), "-i", "https://pypi.org/simple") }
  if ($PipConstraints) { $docArgs += @("-c", $PipConstraints) }
  & $PythonExe $docArgs
  if ($LASTEXITCODE -eq 0) { Write-Host "OK: document stack installed" } else { Write-Host "Document stack install failed or skipped. To install later: $PythonExe -m pip install -r requirements-document.txt -c requirements-constraints.txt -i https://pypi.org/simple" }
} else {
  Write-Host "requirements-document.txt not found; skipping."
}

# ----- Step 5d: MemOS (memory backend, optional) -----
Write-Host ""
Write-Host "=== Step 5d: MemOS (memory backend) ==="
$MemosDir = Join-Path $Root "vendor\memos"
$MemosStandalone = Join-Path $MemosDir "server-standalone.ts"
if (Test-Path $MemosStandalone) {
  $MemosSrc = Join-Path $MemosDir "src"
  $MemosPkg = Join-Path $MemosDir "package.json"
  if (-not (Test-Path $MemosSrc) -or -not (Test-Path $MemosPkg)) {
    Write-Host "MemOS app source missing in vendor\memos. Cloning MemOS and copying app..."
    try {
      $null = Get-Command git -ErrorAction SilentlyContinue
      if ($?) {
        $MemosTmp = Join-Path $Root ".tmp_memos_clone"
        if (Test-Path $MemosTmp) { Remove-Item -Recurse -Force $MemosTmp }
        & git clone --depth 1 https://github.com/MemTensor/MemOS.git $MemosTmp 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $MemosTmp "apps\memos-local-openclaw"))) {
          $MemosApp = Join-Path $MemosTmp "apps\memos-local-openclaw"
          Get-ChildItem -Path $MemosApp | ForEach-Object {
            if ($_.Name -notin @("server-standalone.ts", "HOMECLAW-STANDALONE.md", "memos-standalone.json.example")) {
              Copy-Item -Path $_.FullName -Destination $MemosDir -Recurse -Force -ErrorAction SilentlyContinue
            }
          }
          Write-Host "MemOS app copied to vendor\memos"
        }
        if (Test-Path $MemosTmp) { Remove-Item -Recurse -Force $MemosTmp -ErrorAction SilentlyContinue }
      } else {
        Write-Host "git not found; skipping MemOS app copy. See vendor\memos\HOMECLAW-STANDALONE.md for manual setup."
      }
    } catch {
      Write-Host "MemOS clone/copy failed. See vendor\memos\HOMECLAW-STANDALONE.md for manual setup."
    }
  }
  if (Test-Path $MemosPkg) {
    $pkgContent = Get-Content $MemosPkg -Raw -ErrorAction SilentlyContinue
    if ($pkgContent -and $pkgContent -notmatch '"standalone"') {
      if (Get-Command node -ErrorAction SilentlyContinue) {
        $env:MEMOS_DIR = $MemosDir
        & node -e "const fs=require('fs'),p=require('path'),d=process.env.MEMOS_DIR;if(d){const f=p.join(d,'package.json');try{const j=JSON.parse(fs.readFileSync(f,'utf8'));j.scripts=j.scripts||{};j.scripts.standalone='tsx server-standalone.ts';fs.writeFileSync(f,JSON.stringify(j,null,2));}catch(e){}}" 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "Added standalone script to MemOS package.json" }
      }
    }
    if (Get-Command npm -ErrorAction SilentlyContinue) {
      Write-Host "Installing MemOS dependencies (npm install in vendor\memos)..."
      $memosPushed = $false
      try {
        Push-Location $MemosDir -ErrorAction Stop
        $memosPushed = $true
        npm install --silent 2>$null
      } catch {
        # path invalid or npm failed; continue
      } finally {
        if ($memosPushed) { Pop-Location -ErrorAction SilentlyContinue }
      }
      if (Test-Path (Join-Path $MemosDir "node_modules")) {
        Write-Host "OK: MemOS installed at vendor\memos (run automatically with Core when memory_backend is memos or composite)"
      } else {
        Write-Host "MemOS npm install failed or skipped. To retry: cd vendor\memos; npm install"
      }
    } else {
      Write-Host "npm not found; skipping MemOS dependencies. Install Node.js then: cd vendor\memos; npm install"
    }
  } else {
    Write-Host "MemOS package.json missing; run install again after copying MemOS app (see vendor\memos\HOMECLAW-STANDALONE.md)"
  }
} else {
  Write-Host "vendor\memos\server-standalone.ts not found; skipping MemOS (optional memory backend)"
}

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
# Start Portal in a new window (so it keeps running after this script exits, like nohup on install.sh)
$portalArgs = if ($PythonExe -eq "py") { @("-3", "-m", "main", "portal", "--no-open-browser") } else { @("-m", "main", "portal", "--no-open-browser") }
Start-Process -FilePath $PythonExe -ArgumentList $portalArgs -WorkingDirectory $Root
Start-Sleep -Seconds 3
Start-Process $PortalUrl
Write-Host ""
Write-Host "--- Next steps ---"
Write-Host "  1. In Portal ($PortalUrl): create admin account, choose model, add users, start Core."
Write-Host "  2. Check setup: cd $Root; $PythonExe -m main doctor"
Write-Host "  3. Start Core: cd $Root; $PythonExe -m main start"
Write-Host "  4. Run Portal again: cd $Root; $PythonExe -m main portal"
Write-Host ""
Write-Host "--- Optional (Dev Bridge) ---"
Write-Host "If you want to use the Cursor / ClaudeCode / Trae friends (run tools on your dev machine), you may want:"
Write-Host "  - Cursor CLI (agent/cursor): `$env:HOMECLAW_INSTALL_CURSOR_CLI=`"1`"; .\\install.ps1"
Write-Host "  - Claude Code CLI (claude):  `$env:HOMECLAW_INSTALL_CLAUDE_CODE=`"1`"; .\\install.ps1"
Write-Host "  - Trae Agent (trae-cli):     `$env:HOMECLAW_INSTALL_TRAE_AGENT=`"1`"; .\\install.ps1"
Write-Host "  - Or using install.bat flags: install.bat cursor   |  install.bat claude   |  install.bat trae   |  install.bat cursor claude trae"
Write-Host ""
Write-Host "Trae Agent: install clones to tools\trae-agent and creates trae_config.yaml from example. Edit trae_config.yaml with your API key (see https://github.com/bytedance/trae-agent). Then set cursor_bridge_trae_agent_path (path to trae-cli, e.g. tools\trae-agent\.venv\Scripts\trae-cli.exe) and cursor_bridge_trae_agent_config (path to trae_config.yaml) in config\skills_and_plugins.yml."
Write-Host ""
Write-Host "Docs: https://github.com/allenpeng0705/HomeClaw"
