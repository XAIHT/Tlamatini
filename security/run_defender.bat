@echo off
setlocal EnableExtensions DisableDelayedExpansion
REM Created by Angela Lopez Mendoza (@angelahack1) - Tlamatini Author Banner.
REM Default is report-only: no process kills and no firewall block additions.
title Tlamatini Defender - report only
set "TLAMATINI_LAUNCHER=%~f0"
set "TLAMATINI_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
echo Tlamatini Defender: report-only scan. Legitimate tools will not be stopped.
"%TLAMATINI_POWERSHELL%" -NoProfile -Command "$p=[Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent();if($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){exit 0};exit 1"
if errorlevel 1 goto elevate
"%TLAMATINI_POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0tlamatini_defender.ps1" -DetectOnly -NoPause
set "TLAMATINI_EXIT=%errorlevel%"
if "%TLAMATINI_EXIT%"=="0" (echo Scan finished. Review security_logs for findings.) else (echo Scan needs attention. Exit code: %TLAMATINI_EXIT%)
pause
exit /b %TLAMATINI_EXIT%
:elevate
"%TLAMATINI_POWERSHELL%" -NoProfile -Command "try {$p=Start-Process -FilePath $env:TLAMATINI_LAUNCHER -Verb RunAs -Wait -PassThru;exit $p.ExitCode} catch {Write-Error $_;exit 1}"
set "TLAMATINI_EXIT=%errorlevel%"
if not "%TLAMATINI_EXIT%"=="0" pause
exit /b %TLAMATINI_EXIT%
