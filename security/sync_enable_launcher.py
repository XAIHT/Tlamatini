"""Regenerate the standalone enable launcher from its reviewed PowerShell sources.

Created by Angela López Mendoza · @angelahack1 — Tlamatini Author Banner.
Run from a verified visible development console. This only writes the BAT file;
it never runs the launcher or changes Windows settings.
"""
from pathlib import Path


HEADER = r'''@echo off
setlocal EnableExtensions DisableDelayedExpansion
REM Created by Angela Lopez Mendoza (@angelahack1) - Tlamatini Author Banner.
REM Generated from tlamatini_whitelist_v2.ps1 + windows_access_helpers.ps1.
REM This BAT is self-contained. --check checks syntax without elevation/changes.
set "TLAMATINI_LAUNCHER=%~f0"
set "TLAMATINI_SECURITY_DIR=%~dp0"
set "TLAMATINI_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if /I "%~1"=="--check" goto check
title Enable Tlamatini - verified Windows access
echo.
echo Enable Tlamatini - Python, commands, documents and network access
echo Created by Angela Lopez Mendoza (@angelahack1)
echo.
echo This adds exceptions for the installations and exact executables listed
echo in the next window, including shared Python and command interpreters.
echo It repairs exact local app firewall blocks and saves a recovery baseline.
echo Defender and the firewall remain running. Review every ATTENTION item.
echo.
"%TLAMATINI_POWERSHELL%" -NoProfile -Command "$p=[Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent(); if($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){exit 0}; exit 1"
if errorlevel 1 goto elevate
"%TLAMATINI_POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:TLAMATINI_LAUNCHER,[Text.Encoding]::UTF8);$m='#PSCODE'+'_BEGIN';$i=$t.LastIndexOf($m);if($i -lt 0){throw 'Missing embedded payload'};& ([scriptblock]::Create($t.Substring($i+$m.Length))) -NoPause"
set "TLAMATINI_EXIT=%errorlevel%"
echo.
if "%TLAMATINI_EXIT%"=="0" (echo Settings verified. Restart Tlamatini.) else (echo Some settings need attention. Read the report above. Exit code: %TLAMATINI_EXIT%)
pause
exit /b %TLAMATINI_EXIT%
:elevate
echo Please approve the Windows UAC prompt to apply the listed exceptions.
"%TLAMATINI_POWERSHELL%" -NoProfile -Command "try {$p=Start-Process -FilePath $env:TLAMATINI_LAUNCHER -Verb RunAs -Wait -PassThru;exit $p.ExitCode} catch {Write-Error $_;exit 1}"
set "TLAMATINI_EXIT=%errorlevel%"
if not "%TLAMATINI_EXIT%"=="0" echo Enablement did not finish successfully. No success is assumed.
if not "%TLAMATINI_EXIT%"=="0" pause
exit /b %TLAMATINI_EXIT%
:check
"%TLAMATINI_POWERSHELL%" -NoProfile -Command "$t=[IO.File]::ReadAllText($env:TLAMATINI_LAUNCHER,[Text.Encoding]::UTF8);$m='#PSCODE'+'_BEGIN';$i=$t.LastIndexOf($m);if($i -lt 0){exit 1};$e=$null;$k=$null;[void][Management.Automation.Language.Parser]::ParseInput($t.Substring($i+$m.Length),[ref]$k,[ref]$e);$e | ForEach-Object {Write-Host $_};Write-Host ('Embedded parse errors: '+@($e).Count);if(@($e).Count){exit 1};exit 0"
exit /b %errorlevel%
#PSCODE_BEGIN
'''


def launcher_text(directory):
    directory = Path(directory)
    source = (directory / 'tlamatini_whitelist_v2.ps1').read_text(encoding='utf-8-sig')
    helpers = (directory / 'windows_access_helpers.ps1').read_text(encoding='utf-8-sig')
    anchor = '$securityDir = if ($PSScriptRoot)'
    if source.count(anchor) != 1:
        raise ValueError('Expected one helper insertion point after the param block')
    return HEADER + source.replace(anchor, helpers + '\n' + anchor, 1)


if __name__ == '__main__':
    directory = Path(__file__).resolve().parent
    path = directory / 'enable_tlamatini_v2.bat'
    path.write_text(launcher_text(directory), encoding='utf-8', newline='\r\n')
    print(f'Wrote self-contained launcher: {path}')
