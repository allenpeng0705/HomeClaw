@echo off
setlocal EnableDelayedExpansion
REM Package HomeClaw for Windows: Core + config + embedded Python + Node + Companion,
REM and RunHomeClaw.bat to start Core and open Companion.
REM Models are NOT included; users put GGUF etc. in %USERPROFILE%\HomeClaw\models (see PACKAGE_README.txt).
REM
REM Usage: scripts\package_homeclaw.bat [--no-companion] [--no-node] [--with-llama-cpp] [--llama-cpp-variant win_cpu^|win_cuda] [--output DIR] [--no-archive]
REM   --with-llama-cpp       Include llama.cpp-master (llama-server for local GGUF). Optional.
REM   --llama-cpp-variant    When --with-llama-cpp: win_cpu (default) or win_cuda. win_cuda requires NVIDIA GPU + drivers (CUDA not bundled).

set "REPO_ROOT=%~dp0.."
set "REPO_ROOT=%REPO_ROOT:\=/%"
for %%A in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fA"
set "REPO_ROOT=%REPO_ROOT:/=\%"

set BUILD_COMPANION=1
set BUNDLE_NODE=1
set CREATE_ARCHIVE=1
set INCLUDE_LLAMA_CPP=0
set "LLAMA_CPP_VARIANT=win_cpu"
set "OUTPUT_DIR="

REM Parse options
:parse
if "%~1"=="" goto :done_parse
if /i "%~1"=="--no-companion"       (set BUILD_COMPANION=0 & shift & goto :parse)
if /i "%~1"=="--no-node"            (set BUNDLE_NODE=0    & shift & goto :parse)
if /i "%~1"=="--no-archive"        (set CREATE_ARCHIVE=0  & shift & goto :parse)
if /i "%~1"=="--with-llama-cpp"    (set INCLUDE_LLAMA_CPP=1 & shift & goto :parse)
if /i "%~1"=="--llama-cpp-variant" (set "LLAMA_CPP_VARIANT=%~2" & shift & shift & goto :parse)
if /i "%~1"=="--output"            (set "OUTPUT_DIR=%~2" & shift & shift & goto :parse)
echo Unknown option: %~1
echo Usage: %~nx0 [--no-companion] [--no-node] [--with-llama-cpp] [--llama-cpp-variant win_cpu^|win_cuda] [--output DIR] [--no-archive]
exit /b 1
:done_parse

if /i not "%LLAMA_CPP_VARIANT%"=="win_cpu" if /i not "%LLAMA_CPP_VARIANT%"=="win_cuda" (
  echo --llama-cpp-variant must be win_cpu or win_cuda, got: %LLAMA_CPP_VARIANT%
  exit /b 1
)

if "%OUTPUT_DIR%"=="" (
  for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set DATE_PART=%%i
  set "OUTPUT_DIR=%REPO_ROOT%\dist\HomeClaw-package-%DATE_PART%"
)

set "PYTHON_STANDALONE_RELEASE=20260211"
set "PYTHON_VERSION=3.11.14"
set "NODE_VERSION=20.18.0"

echo Package output: %OUTPUT_DIR%
echo Companion: %BUILD_COMPANION%, Node bundle: %BUNDLE_NODE%, llama.cpp: %INCLUDE_LLAMA_CPP% (%LLAMA_CPP_VARIANT%)
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM ---------- Copy Core code and config ----------
echo Copying Core code and config...
copy /Y "%REPO_ROOT%\main.py" "%OUTPUT_DIR%\"
copy /Y "%REPO_ROOT%\requirements.txt" "%OUTPUT_DIR%\"

for %%D in (base core llm memory tools hybrid_router plugins channels system_plugins examples ui) do (
  if exist "%REPO_ROOT%\%%D" (
    robocopy "%REPO_ROOT%\%%D" "%OUTPUT_DIR%\%%D" /E /NFL /NDL /NJH /NJS /XD __pycache__ .git database logs models node_modules site docs docs_design tests plugs_disabled llama.cpp-master .env venv .DS_Store /XF *.pyc *.gguf .env 2>nul
  )
)

if not exist "%OUTPUT_DIR%\config" mkdir "%OUTPUT_DIR%\config"
copy /Y "%REPO_ROOT%\config\core.yml" "%OUTPUT_DIR%\config\"
copy /Y "%REPO_ROOT%\config\user.yml" "%OUTPUT_DIR%\config\"
if exist "%REPO_ROOT%\config\core.yml.reference" copy /Y "%REPO_ROOT%\config\core.yml.reference" "%OUTPUT_DIR%\config\" 2>nul

for %%D in (workspace skills prompts hybrid) do (
  if exist "%REPO_ROOT%\config\%%D" (
    robocopy "%REPO_ROOT%\config\%%D" "%OUTPUT_DIR%\config\%%D" /E /NFL /NDL /NJH /NJS /XD __pycache__ /XF *.pyc 2>nul
  )
)

REM ---------- llama.cpp for Windows (local GGUF): package win_cpu or win_cuda (--with-llama-cpp) ----------
REM win_cuda requires NVIDIA GPU and drivers; CUDA runtime is NOT bundled (user may need CUDA Toolkit/redist).
if %INCLUDE_LLAMA_CPP%==1 (
  set "LLAMA_SRC=%REPO_ROOT%\llama.cpp-master\%LLAMA_CPP_VARIANT%"
  if exist "%LLAMA_SRC%" (
    echo Packaging llama.cpp (%LLAMA_CPP_VARIANT%) for local models...
    if not exist "%OUTPUT_DIR%\llama.cpp-master" mkdir "%OUTPUT_DIR%\llama.cpp-master"
    xcopy /E /I /Y "%LLAMA_SRC%\*" "%OUTPUT_DIR%\llama.cpp-master\%LLAMA_CPP_VARIANT%\"
    echo llama.cpp-master/%LLAMA_CPP_VARIANT%/ copied (llama-server for local GGUF).
  ) else (
    echo llama.cpp-master/%LLAMA_CPP_VARIANT% not found at %LLAMA_SRC%, skipping.
  )
)

REM ---------- Companion app (Windows) ----------
if %BUILD_COMPANION%==1 (
  echo Building Companion app (Windows)...
  set "COMPANION_DIR=%REPO_ROOT%\clients\HomeClawApp"
  if not exist "%COMPANION_DIR%" (
    echo Companion not found at %COMPANION_DIR%, skipping.
  ) else (
    pushd "%COMPANION_DIR%"
    call flutter pub get
    call flutter build windows --release
    popd
    set "COMPANION_RELEASE=%COMPANION_DIR%\build\windows\x64\runner\Release"
    if not exist "%COMPANION_RELEASE%" set "COMPANION_RELEASE=%COMPANION_DIR%\build\windows\runner\Release"
    if exist "%COMPANION_RELEASE%\HomeClawApp.exe" (
      if not exist "%OUTPUT_DIR%\companion" mkdir "%OUTPUT_DIR%\companion"
      xcopy /E /I /Y "%COMPANION_RELEASE%\*" "%OUTPUT_DIR%\companion\"
      echo Companion app copied to %OUTPUT_DIR%\companion\
    ) else (
      echo Companion build did not produce HomeClawApp.exe at %COMPANION_RELEASE%
    )
  )
) else (
  echo Skipping Companion build (--no-companion).
)

REM ---------- Bundle Node.js and npm install for homeclaw-browser ----------
if %BUNDLE_NODE%==1 (
  echo Bundling Node.js and installing homeclaw-browser dependencies...
  set "NODE_ZIP=node-v%NODE_VERSION%-win-x64.zip"
  set "NODE_URL=https://nodejs.org/dist/v%NODE_VERSION%/%NODE_ZIP%"
  set "NODE_CACHE=%REPO_ROOT%\dist\node-standalone-cache"
  if not exist "%NODE_CACHE%" mkdir "%NODE_CACHE%"
  if not exist "%NODE_CACHE%\%NODE_ZIP%" (
    echo Downloading Node.js %NODE_VERSION% for Windows x64...
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '%NODE_URL%' -OutFile '%NODE_CACHE%\%NODE_ZIP%' -UseBasicParsing"
  )
  if not exist "%OUTPUT_DIR%\node" (
    powershell -NoProfile -Command "Expand-Archive -Path '%NODE_CACHE%\%NODE_ZIP%' -DestinationPath '%OUTPUT_DIR%' -Force"
    move "%OUTPUT_DIR%\node-v%NODE_VERSION%-win-x64" "%OUTPUT_DIR%\node"
  )
  set "NPM_CMD=%OUTPUT_DIR%\node\npm.cmd"
  if exist "%NPM_CMD%" (
    set "BROWSER_PLUGIN=%OUTPUT_DIR%\system_plugins\homeclaw-browser"
    if exist "%BROWSER_PLUGIN%\package.json" (
      echo Running npm install in system_plugins/homeclaw-browser...
      pushd "%BROWSER_PLUGIN%"
      call "%NPM_CMD%" install --omit=dev --no-fund --no-audit
      popd
      echo homeclaw-browser dependencies installed.
    )
  ) else (
    echo Node.js not found at %OUTPUT_DIR%\node
  )
) else (
  echo Skipping Node.js bundle (--no-node). homeclaw-browser will need Node on PATH at run time.
)

REM ---------- Embedded Python (python-build-standalone) ----------
echo Bundling standalone Python and installing dependencies...
set "PYTHON_ARCH=x86_64-pc-windows-msvc"
set "PYTHON_TAR=cpython-%PYTHON_VERSION%+%PYTHON_STANDALONE_RELEASE%-%PYTHON_ARCH%-install_only.tar.gz"
set "PYTHON_URL=https://github.com/astral-sh/python-build-standalone/releases/download/%PYTHON_STANDALONE_RELEASE%/%PYTHON_TAR%"
set "CACHE_DIR=%REPO_ROOT%\dist\python-standalone-cache"
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"

if not exist "%CACHE_DIR%\%PYTHON_TAR%" (
  echo Downloading standalone Python %PYTHON_VERSION% for Windows...
  powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%CACHE_DIR%\%PYTHON_TAR%' -UseBasicParsing"
)

if not exist "%OUTPUT_DIR%\python\python.exe" (
  echo Extracting Python into package...
  tar -xzf "%CACHE_DIR%\%PYTHON_TAR%" -C "%OUTPUT_DIR%"
  REM Tarball may extract to "python/install" or "cpython-3.11.14+..."
  if exist "%OUTPUT_DIR%\python\install" (
    move "%OUTPUT_DIR%\python\install" "%OUTPUT_DIR%\python_install"
    rmdir /S /Q "%OUTPUT_DIR%\python" 2>nul
    move "%OUTPUT_DIR%\python_install" "%OUTPUT_DIR%\python"
  )
  if not exist "%OUTPUT_DIR%\python\python.exe" (
    for /d %%P in ("%OUTPUT_DIR%\cpython-*") do (
      if exist "%%P\python.exe" (
        if exist "%OUTPUT_DIR%\python" rmdir /S /Q "%OUTPUT_DIR%\python" 2>nul
        move "%%P" "%OUTPUT_DIR%\python"
        goto :python_done
      )
    )
  )
  :python_done
)

set "PYTHON_BIN=%OUTPUT_DIR%\python\python.exe"
if not exist "%PYTHON_BIN%" set "PYTHON_BIN=%OUTPUT_DIR%\python\python3.exe"
if not exist "%PYTHON_BIN%" (
  echo Standalone Python not found in %OUTPUT_DIR%\python
  exit /b 1
)

echo Installing dependencies into bundle (pip install -r requirements.txt)...
"%PYTHON_BIN%" -m pip install --quiet --upgrade pip
"%PYTHON_BIN%" -m pip install --quiet --index-url https://pypi.org/simple/ -r "%OUTPUT_DIR%\requirements.txt"

REM ---------- RunHomeClaw.bat launcher ----------
echo Creating RunHomeClaw.bat launcher...
(
  echo @echo off
  echo setlocal
  echo set "PKG_ROOT=%%~dp0"
  echo set "PATH=%%PKG_ROOT%%python;%%PKG_ROOT%%node;%%PATH%%"
  echo set "CORE_ROOT=%%PKG_ROOT%%"
  echo cd /d "%%CORE_ROOT%%"
  echo.
  echo echo Starting HomeClaw Core...
  echo start /B "" "%%PKG_ROOT%%python\python.exe" -m main start --no-open-browser
  echo.
  echo echo Waiting for Core to be ready...
  echo set READY_URL=http://127.0.0.1:9000/ready
  echo for /L %%%%i in ^(1,1,60^) do ^(
  echo   powershell -NoProfile -Command "try { if ^((Invoke-WebRequest -Uri 'http://127.0.0.1:9000/ready' -UseBasicParsing -TimeoutSec 2^).StatusCode -eq 200^) { exit 0 }; exit 1 } catch { exit 1 }" 2^>nul ^&^& goto :core_ready
  echo   timeout /t 1 /nobreak ^>nul
  echo ^)
  echo :core_ready
  echo.
  echo if exist "%%PKG_ROOT%%companion\HomeClawApp.exe" ^(
  echo   echo Opening Companion...
  echo   start "" "%%PKG_ROOT%%companion\HomeClawApp.exe"
  echo ^)
  echo.
  echo echo Core is running. Close this window to stop Core, or leave it open.
  echo pause
) > "%OUTPUT_DIR%\RunHomeClaw.bat"

REM ---------- PACKAGE_README.txt ----------
(
  echo HomeClaw package for Windows — run RunHomeClaw.bat to start Core and open Companion.
  echo.
  echo MODELS ^(not included^)
  echo   Put your model files ^(e.g. .gguf^) in:
  echo     %%USERPROFILE%%\HomeClaw\models
  echo   Edit config\core.yml — set model_path to that path if needed.
  echo.
  echo RUN
  echo   Double-click RunHomeClaw.bat. It will:
  echo   1. Start HomeClaw Core ^(embedded Python, no install needed^).
  echo   2. Open the Companion app; set Core URL to http://127.0.0.1:9000 if prompted.
  echo.
  echo SYSTEM PLUGIN ^(homeclaw-browser^)
  echo   Node.js is bundled; npm install was run for system_plugins/homeclaw-browser.
  echo   For Playwright browser automation, run "npx playwright install chromium" from
  echo   system_plugins\homeclaw-browser if needed.
  echo.
  echo CONFIG
  echo   config\core.yml and config\user.yml. Edit as needed ^(LLM, ports, model_path, etc.^).
  echo.
  echo LLAMA.CPP ^(if included^)
  echo   llama.cpp-master\win_cpu or win_cuda contains llama-server for local GGUF. win_cuda requires
  echo   an NVIDIA GPU and drivers; CUDA runtime is not bundled ^(install CUDA Toolkit/redist if needed^).
) > "%OUTPUT_DIR%\PACKAGE_README.txt"

echo Wrote %OUTPUT_DIR%\PACKAGE_README.txt

REM ---------- Archive ----------
if %CREATE_ARCHIVE%==1 (
  echo Creating archive...
  for %%A in ("%OUTPUT_DIR%") do set "ARCHIVE_BASE=%%~nxA"
  set "ARCHIVE_PATH=%OUTPUT_DIR%\..\%ARCHIVE_BASE%.zip"
  powershell -NoProfile -Command "Compress-Archive -Path '%OUTPUT_DIR%' -DestinationPath '%ARCHIVE_PATH%' -Force"
  echo Created %ARCHIVE_PATH%
)

echo Done. Package directory: %OUTPUT_DIR%
echo Run: %OUTPUT_DIR%\RunHomeClaw.bat to start Core and open Companion.
endlocal
exit /b 0
