@echo off

:: 1. Resolve Java WITHOUT any hardcoded developer path.
::    Prefer an ambient JAVA_HOME (manage.py pins it to the carried
::    <install_dir>\jre in frozen mode). If unset, fall back to the JRE carried
::    next to this payload (<install_dir>\jre = one level up from this folder).
if not defined JAVA_HOME (
    if exist "%~dp0..\jre\bin\java.exe" set "JAVA_HOME=%~dp0..\jre"
)
if defined JAVA_HOME set "PATH=%JAVA_HOME%\bin;%PATH%"

:: 2. Check if user provided arguments
:: %1 is the first parameter, %2 is the second
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

:: 3. Run the Command (jd-cli.jar sits next to this .bat)
:: "%~1" removes quotes from the input (if any) and adds fresh ones to handle spaces safely
echo Processing %~1 outputting to %~2 ...
java -jar "%~dp0jd-cli.jar" "%~1" -od "%~2"

:: Exit successfully
goto :eof

:usage
echo.
echo Usage: jd-cli.bat [WarOrJarFile] [OutputDir]
echo Example: jd-cli.bat FrameWorkApp.war FrameworkApp
echo.