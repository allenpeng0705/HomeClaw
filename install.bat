@echo off
REM HomeClaw installer launcher for Windows. Runs install.ps1 with ExecutionPolicy Bypass.
REM Same steps as install.ps1: Python, Node, tsx, ClawHub, clone, VMPrint, pip, Cognee deps (cognee in vendor/), document stack, MemOS (vendor/memos), llama.cpp, Portal.
REM Use this if .\install.ps1 fails with "not digitally signed" (execution policy).
echo.
echo Running HomeClaw installer (same as install.ps1, with execution policy bypass)...
echo If you saw "cannot be loaded" or "not digitally signed" when running install.ps1 directly,
echo use this .bat file or run: powershell -ExecutionPolicy Bypass -File .\install.ps1
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% neq 0 exit /b %EXITCODE%
exit /b 0
