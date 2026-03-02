@rem
@rem Copyright 2015 the original author or authors.
@rem
@rem Licensed under the Apache License, Version 2.0 (the "License");
@rem you may not use this file except in compliance with the License.
@rem You may obtain a copy of the License at
@rem
@rem      https://www.apache.org/licenses/LICENSE-2.0
@rem
@rem Unless required by applicable law or agreed to in writing, software
@rem distributed under the License is distributed on an "AS IS" BASIS,
@rem WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
@rem See the License for the specific language governing permissions and
@rem limitations under the License.
@rem
@rem SPDX-License-Identifier: Apache-2.0
@rem

@if "%DEBUG%"=="" @echo off
@rem ##########################################################################
@rem
@rem  signal-cli startup script for Windows
@rem
@rem ##########################################################################

@rem Set local scope for the variables with windows NT shell
if "%OS%"=="Windows_NT" setlocal

set DIRNAME=%~dp0
if "%DIRNAME%"=="" set DIRNAME=.
@rem This is normally unused
set APP_BASE_NAME=%~n0
set APP_HOME=%DIRNAME%..

@rem Resolve any "." and ".." in APP_HOME to make it shorter.
for %%i in ("%APP_HOME%") do set APP_HOME=%%~fi

@rem Add default JVM options here. You can also use JAVA_OPTS and SIGNAL_CLI_OPTS to pass JVM options to this script.
set DEFAULT_JVM_OPTS="--enable-native-access=ALL-UNNAMED"

@rem Find java.exe
if defined JAVA_HOME goto findJavaFromJavaHome

set JAVA_EXE=java.exe
%JAVA_EXE% -version >NUL 2>&1
if %ERRORLEVEL% equ 0 goto execute

echo. 1>&2
echo ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH. 1>&2
echo. 1>&2
echo Please set the JAVA_HOME variable in your environment to match the 1>&2
echo location of your Java installation. 1>&2

goto fail

:findJavaFromJavaHome
set JAVA_HOME=%JAVA_HOME:"=%
set JAVA_EXE=%JAVA_HOME%/bin/java.exe

if exist "%JAVA_EXE%" goto execute

echo. 1>&2
echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME% 1>&2
echo. 1>&2
echo Please set the JAVA_HOME variable in your environment to match the 1>&2
echo location of your Java installation. 1>&2

goto fail

:execute
@rem Setup the command line

set CLASSPATH=%APP_HOME%\lib\signal-cli-0.14.0.jar;%APP_HOME%\lib\libsignal-cli-0.14.0.jar;%APP_HOME%\lib\bcprov-jdk18on-1.83.jar;%APP_HOME%\lib\jackson-core-2.20.2.jar;%APP_HOME%\lib\signal-service-java-2.15.3_unofficial_140.jar;%APP_HOME%\lib\jackson-module-kotlin-2.20.2.jar;%APP_HOME%\lib\jackson-databind-2.20.2.jar;%APP_HOME%\lib\argparse4j-0.9.0.jar;%APP_HOME%\lib\dbus-java-transport-native-unixsocket-5.0.0.jar;%APP_HOME%\lib\jul-to-slf4j-2.0.17.jar;%APP_HOME%\lib\logback-classic-1.5.32.jar;%APP_HOME%\lib\dbus-java-core-5.0.0.jar;%APP_HOME%\lib\HikariCP-7.0.2.jar;%APP_HOME%\lib\slf4j-api-2.0.17.jar;%APP_HOME%\lib\core-3.5.4.jar;%APP_HOME%\lib\jackson-annotations-2.20.jar;%APP_HOME%\lib\logback-core-1.5.32.jar;%APP_HOME%\lib\sqlite-jdbc-3.51.2.0.jar;%APP_HOME%\lib\jsr305-3.0.2.jar;%APP_HOME%\lib\models-jvm-2.15.3_unofficial_140.jar;%APP_HOME%\lib\util-jvm-2.15.3_unofficial_140.jar;%APP_HOME%\lib\rxkotlin-3.0.1.jar;%APP_HOME%\lib\wire-runtime-jvm-4.9.11.jar;%APP_HOME%\lib\libsignal-client-0.87.4.jar;%APP_HOME%\lib\kotlin-stdlib-jdk7-2.1.0.jar;%APP_HOME%\lib\okhttp-jvm-5.3.2.jar;%APP_HOME%\lib\kotlin-reflect-2.1.0.jar;%APP_HOME%\lib\kotlinx-coroutines-core-jvm-1.10.2.jar;%APP_HOME%\lib\kotlinx-serialization-core-jvm-1.9.0.jar;%APP_HOME%\lib\kotlinx-serialization-json-jvm-1.9.0.jar;%APP_HOME%\lib\okio-jvm-3.16.4.jar;%APP_HOME%\lib\kotlin-stdlib-2.2.21.jar;%APP_HOME%\lib\kotlin-stdlib-jdk8-2.1.0.jar;%APP_HOME%\lib\libphonenumber-8.13.50.jar;%APP_HOME%\lib\rxjava-3.0.13.jar;%APP_HOME%\lib\annotations-23.0.0.jar;%APP_HOME%\lib\reactive-streams-1.0.3.jar


@rem Execute signal-cli
"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %SIGNAL_CLI_OPTS%  -classpath "%CLASSPATH%" org.asamk.signal.Main %*

:end
@rem End local scope for the variables with windows NT shell
if %ERRORLEVEL% equ 0 goto mainEnd

:fail
rem Set variable SIGNAL_CLI_EXIT_CONSOLE if you need the _script_ return code instead of
rem the _cmd.exe /c_ return code!
set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% equ 0 set EXIT_CODE=1
if not ""=="%SIGNAL_CLI_EXIT_CONSOLE%" exit %EXIT_CODE%
exit /b %EXIT_CODE%

:mainEnd
if "%OS%"=="Windows_NT" endlocal

:omega
