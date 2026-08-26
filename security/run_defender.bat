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
echo This launcher runs one ARMED heuristic security sweep.
echo It checks ten monitor families and may block repeated-logon IPs
echo or stop selected process-name matches outside Tlamatini roots.
echo Use the PowerShell script with -DetectOnly for a safe baseline.
echo.
echo A UAC prompt will appear. Click YES to allow.
echo.

REM --- Check if running as admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    echo.
    REM Self-elevate: relaunch this script with admin rights
    set "TLAMATINI_LAUNCHER=%~f0"
    powershell -NoProfile -Command "Start-Process -FilePath $env:TLAMATINI_LAUNCHER -Verb RunAs"
    exit /b
)

REM --- Running as admin - execute the PowerShell defender script ---
echo [OK] Administrator privileges confirmed.
echo.
echo Running Tlamatini Active Defender...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tlamatini_defender.ps1"
set "TLAMATINI_EXIT=%errorlevel%"

echo.
echo ================================================================
echo   DEFENDER SCAN COMPLETE
echo   Check %~dp0security_logs\alerts.log
echo   and investigate CRITICAL or ALERT entries before acting.
echo ================================================================
echo.
pause
exit /b %TLAMATINI_EXIT%
