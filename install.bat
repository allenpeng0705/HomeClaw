@echo off
REM HomeClaw installer launcher for Windows.
REM Use this if .\install.ps1 fails with "not digitally signed" (execution policy).
REM This runs the PowerShell script with ExecutionPolicy Bypass for this run only.
echo.
echo Running HomeClaw installer (PowerShell with execution policy bypass)...
echo If you saw "cannot be loaded" or "not digitally signed" when running install.ps1 directly,
echo you can use this .bat file instead, or run: powershell -ExecutionPolicy Bypass -File .\install.ps1
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% neq 0 exit /b %EXITCODE%
exit /b 0
