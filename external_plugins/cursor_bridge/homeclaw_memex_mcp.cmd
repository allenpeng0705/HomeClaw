@echo off
REM HomeClaw bundled memex MCP — chdir to repo root (parent of external_plugins\).
set "BRIDGE=%~dp0"
cd /d "%BRIDGE%..\.." || exit /b 1
where py >nul 2>nul && py -3 -m external_plugins.cursor_bridge.memex_mcp %* && exit /b %ERRORLEVEL%
where python >nul 2>nul && python -m external_plugins.cursor_bridge.memex_mcp %* && exit /b %ERRORLEVEL%
echo homeclaw_memex_mcp: Python 3 not found. Install Python and ensure "python" or "py" is on PATH.
exit /b 1
