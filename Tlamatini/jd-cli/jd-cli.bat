@echo off

:: 1. Set Environment Variables
set "JAVA_HOME=D:\devenv\Sun\GlassFish706\JDK17.0.6_10"
set "PATH=%JAVA_HOME%\bin;%PATH%"

:: 2. Check if user provided arguments
:: %1 is the first parameter, %2 is the second
if "%~1"=="" goto :usage
if "%~2"=="" goto :usage

:: 3. Run the Command
:: "%~1" removes quotes from the input (if any) and adds fresh ones to handle spaces safely
echo Processing %~1 outputting to %~2 ...
java -jar jd-cli.jar "%~1" -od "%~2"

:: Exit successfully
goto :eof

:usage
echo.
echo Usage: jd-cli.bat [WarOrJarFile] [OutputDir]
echo Example: jd-cli.bat FrameWorkApp.war FrameworkApp
echo.