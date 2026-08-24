@echo off
REM =============================================================================
REM TLAMATINI SECURITY WHITELIST v2 - BATCH LAUNCHER
REM =============================================================================
REM Double-click this file to run the expanded whitelist script as Admin.
REM It will request UAC elevation automatically.
REM
REM Created by Angela Lopez Mendoza (@angelahack1)
REM =============================================================================

title Tlamatini Security Whitelist v2

echo.
echo ================================================================
echo   TLAMATINI SECURITY WHITELIST v2 LAUNCHER
echo   Created by Angela Lopez Mendoza (@angelahack1)
echo ================================================================
echo.
echo This script grants Tlamatini full monitoring privileges.
echo All security protections remain ACTIVE.
echo Tlamatini gets a pass - hackers still get blocked.
echo.
echo A UAC prompt will appear. Click YES to allow.
echo.

REM --- Check if running as admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    echo.
    powershell -Command "Start-Process cmd -ArgumentList '/c %~dp0enable_tlamatini_v2.bat' -Verb RunAs"
    exit /b
)

REM --- Running as admin ---
echo [OK] Administrator privileges confirmed.
echo.
echo Running Tlamatini Whitelist v2...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tlamatini_whitelist_v2.ps1"

echo.
echo ================================================================
echo   WHITELIST v2 COMPLETE
echo   Now run run_defender.bat to scan for hacker activity.
echo ================================================================
echo.
pause