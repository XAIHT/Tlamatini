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
echo This script adds monitoring visibility and security exceptions.
echo Core services remain enabled, but exclusions and selected ASR
echo Audit settings reduce enforcement around Tlamatini.
echo.
echo A UAC prompt will appear. Click YES to allow.
echo.

REM --- Check if running as admin ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    echo.
    set "TLAMATINI_LAUNCHER=%~f0"
    powershell -NoProfile -Command "Start-Process -FilePath $env:TLAMATINI_LAUNCHER -Verb RunAs"
    exit /b
)

REM --- Running as admin ---
echo [OK] Administrator privileges confirmed.
echo.
echo Running Tlamatini Whitelist v2...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tlamatini_whitelist_v2.ps1"
set "TLAMATINI_EXIT=%errorlevel%"

echo.
echo ================================================================
echo   WHITELIST v2 COMPLETE
echo   Now run run_defender.bat to scan for hacker activity.
echo ================================================================
echo.
pause
exit /b %TLAMATINI_EXIT%
