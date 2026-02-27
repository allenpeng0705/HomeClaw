@echo off
setlocal
REM Build the HomeClaw Companion app for Windows and create a distributable bundle (zip or folder).
REM Windows counterpart to scripts/build_companion_dmg.sh (macOS DMG).
REM Usage: scripts\build_companion_windows.bat [--output path\to\bundle.zip]
REM   --output  .zip path = create zip (default: dist\HomeClaw-Companion-windows.zip)
REM             folder path = copy Release files into that folder

set "REPO_ROOT=%~dp0.."
for %%A in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fA"

set "COMPANION_DIR=%REPO_ROOT%\clients\HomeClawApp"
set "DIST_DIR=%REPO_ROOT%\dist"
set "OUTPUT_BUNDLE="

REM Parse options
:parse
if "%~1"=="" goto :done_parse
if /i "%~1"=="--output" (set "OUTPUT_BUNDLE=%~2" & shift & shift & goto :parse)
echo Unknown option: %~1
echo Usage: %~nx0 [--output path\to\HomeClaw-Companion-windows.zip]
exit /b 1
:done_parse

if "%OUTPUT_BUNDLE%"=="" (
  if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
  set "OUTPUT_BUNDLE=%DIST_DIR%\HomeClaw-Companion-windows.zip"
)

echo Building Companion app (Windows release)...
pushd "%COMPANION_DIR%"
call flutter pub get
if errorlevel 1 (popd & echo flutter pub get failed & exit /b 1)
call flutter build windows --release
if errorlevel 1 (popd & echo flutter build windows failed & exit /b 1)
popd

set "RELEASE_DIR=%COMPANION_DIR%\build\windows\x64\runner\Release"
if not exist "%RELEASE_DIR%" set "RELEASE_DIR=%COMPANION_DIR%\build\windows\runner\Release"

if not exist "%RELEASE_DIR%\HomeClawApp.exe" (
  echo Build did not produce HomeClawApp.exe at %RELEASE_DIR%
  exit /b 1
)

echo Creating Windows bundle...
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

REM Output can be a .zip path or a folder path
set "OUTPUT_ABS=%OUTPUT_BUNDLE%"
if not "%OUTPUT_ABS:\=%"=="%OUTPUT_ABS%" (
  REM Path has backslash - ensure absolute
  for %%A in ("%OUTPUT_BUNDLE%") do set "OUTPUT_ABS=%%~fA"
)

set "IS_ZIP=0"
if /i "%OUTPUT_ABS:~-4%"==".zip" set "IS_ZIP=1"

if %IS_ZIP%==1 (
  REM Create zip: compress Release contents into the zip (so unzip gives a single folder or flat files)
  set "ZIP_DIR=%DIST_DIR%\companion_release_temp"
  if exist "%ZIP_DIR%" rmdir /S /Q "%ZIP_DIR%"
  mkdir "%ZIP_DIR%\HomeClaw Companion"
  xcopy /E /I /Y "%RELEASE_DIR%\*" "%ZIP_DIR%\HomeClaw Companion\"
  powershell -NoProfile -Command "Compress-Archive -Path '%ZIP_DIR%\HomeClaw Companion' -DestinationPath '%OUTPUT_ABS%' -Force"
  rmdir /S /Q "%ZIP_DIR%"
  echo Done. Bundle: %OUTPUT_ABS%
) else (
  REM Output is a folder: copy Release into it
  if not exist "%OUTPUT_ABS%" mkdir "%OUTPUT_ABS%"
  xcopy /E /I /Y "%RELEASE_DIR%\*" "%OUTPUT_ABS%\"
  echo Done. Bundle folder: %OUTPUT_ABS%
)

endlocal
exit /b 0
