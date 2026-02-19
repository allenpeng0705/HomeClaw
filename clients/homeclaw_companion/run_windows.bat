@echo off
REM Build and run HomeClaw Companion on Windows
cd /d "%~dp0"

echo HomeClaw Companion - Windows
echo.

where flutter >nul 2>nul
if errorlevel 1 (
    echo Flutter not found in PATH. Install Flutter from https://flutter.dev
    exit /b 1
)

echo Running: flutter pub get
flutter pub get
if errorlevel 1 exit /b 1

echo.
echo Running: flutter run -d windows
flutter run -d windows
exit /b %ERRORLEVEL%
