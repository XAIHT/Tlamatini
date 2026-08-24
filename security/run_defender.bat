@echo off
REM =============================================================================
REM TLAMATINI ACTIVE DEFENDER - BATCH LAUNCHER
REM =============================================================================
REM Double-click this file to run the defender script as Administrator.
REM It will request UAC elevation automatically.
REM
REM Created by Angela Lopez Mendoza (@angelahack1)
REM =============================================================================

title Tlamatini Active Defender

echo.
echo ================================================================
echo   TLAMATINI ACTIVE DEFENDER LAUNCHER
echo   Created by Angela Lopez Mendoza (@angelahack1)
echo ================================================================
echo.
echo This script will scan your system for hacker activity.
echo It monitors logons, network, processes, tasks, services,
echo registry, and critical directories for threats.
echo.
echo A UAC prompt will appear. Click YES to allow.
echo.

REM --- Check if running as admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    echo.
    REM Self-elevate: relaunch this script with admin rights
    powershell -Command "Start-Process cmd -ArgumentList '/c %~dp0run_defender.bat' -Verb RunAs"
    exit /b
)

REM --- Running as admin - execute the PowerShell defender script ---
echo [OK] Administrator privileges confirmed.
echo.
echo Running Tlamatini Active Defender...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tlamatini_defender.ps1"

echo.
echo ================================================================
echo   DEFENDER SCAN COMPLETE
echo   Check %~dp0security_logs\alerts.log
echo   for any CRITICAL or ALERT entries - those are your hackers.
echo ================================================================
echo.
pause