@echo off
REM HomeClaw installer launcher for Windows. Runs install.ps1 with ExecutionPolicy Bypass.
REM Same flow as install.sh / install.ps1: Python 3.9+, Node, tsx, ClawHub, shallow clone if needed,
REM VMPrint (tools\vmprint: npm install + npm run build — Markdown/PDF + magazine AST browser preview; @vmprint/context-canvas),
REM auto-create .venv if missing then pip (requirements + constraints), Cognee deps, document stack,
REM MemOS (vendor\memos), llama.cpp hint, start Portal.
REM Optional: set HOMECLAW_REPO_URL before running to override the default GitHub URL (same as install.sh).
REM Use this if .\install.ps1 fails with "not digitally signed" (execution policy).
echo.
echo Running HomeClaw installer (same as install.ps1, with execution policy bypass)...
echo If you saw "cannot be loaded" or "not digitally signed" when running install.ps1 directly,
echo use this .bat file or run: powershell -ExecutionPolicy Bypass -File .\install.ps1
echo.
echo Optional (Dev Bridge):
echo   If you want to use the Cursor / ClaudeCode / Trae friends (run tools on your dev machine), you may want:
echo     - Cursor CLI (agent/cursor):  install.bat cursor
echo     - Claude Code CLI (claude):   install.bat claude
echo     - Trae Agent (trae-cli):      install.bat trae
echo     - Bundled memex (npm ci):     install.bat memex   (or runs with cursor / claude flags)
echo     - All three CLIs:             install.bat cursor claude trae
echo.
echo   Trae Agent: install clones to tools\trae-agent and creates trae_config.yaml from example.
echo   Edit trae_config.yaml with your API key (see https://github.com/bytedance/trae-agent).
echo   Then set cursor_bridge_trae_agent_path and cursor_bridge_trae_agent_config in config\skills_and_plugins.yml.
echo.
REM Optional flags for installing Dev CLIs:
REM   install.bat cursor        -> installs Cursor CLI (agent/cursor) if missing
REM   install.bat claude        -> installs Claude Code CLI (claude) if missing
REM   install.bat trae         -> installs Trae Agent (clone + uv sync + config example)
REM   install.bat cursor claude trae -> installs all three
REM   install.bat memex -> npm ci in bundled memex only (Cursor/Claude MCP); also auto with cursor or claude flag
set HOMECLAW_INSTALL_CURSOR_CLI=
set HOMECLAW_INSTALL_CLAUDE_CODE=
set HOMECLAW_INSTALL_TRAE_AGENT=
set HOMECLAW_INSTALL_BUNDLED_MEMEX=
for %%A in (%*) do (
  if /I "%%~A"=="cursor" set HOMECLAW_INSTALL_CURSOR_CLI=1
  if /I "%%~A"=="claude" set HOMECLAW_INSTALL_CLAUDE_CODE=1
  if /I "%%~A"=="trae" set HOMECLAW_INSTALL_TRAE_AGENT=1
  if /I "%%~A"=="memex" set HOMECLAW_INSTALL_BUNDLED_MEMEX=1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% neq 0 exit /b %EXITCODE%
exit /b 0
