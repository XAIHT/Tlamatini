@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM  uncommit-keys.bat  -  Angela's secret-leak seatbelt for the Tlamatini repo.
REM  Created for Angela Lopez Mendoza (@angelahack1), creator of Tlamatini.
REM
REM  THE FREQUENT MISTAKE THIS CATCHES
REM  ---------------------------------
REM  config.json and 8 agent config.yaml files are TRACKED, and your local copies
REM  legitimately hold REAL keys (keyed mode, from data.keys). GitHub's copy holds
REM  "<KEY goes here>" placeholders (push-able mode). Those files are SUPPOSED to
REM  sit permanently "modified" in git status. A `git add -A` / `git commit -a`
REM  sweeps them into a commit -> real keys committed.
REM
REM  HOW IT DETECTS IT
REM  -----------------
REM  It counts "goes here" placeholders in each secret file and compares your blob
REM  against the upstream blob. FEWER placeholders than upstream = real keys leaked
REM  in. This auto-adapts when you add a new key (no hardcoded counts to maintain).
REM
REM  SAFETY CONTRACT (matches CLAUDE.md's PRIVATE DATA GUARD)
REM  --------------------------------------------------------
REM    * Only ever touches UNPUSHED, local-only commits.
REM    * REFUSES to act if the leak is already on the remote (that would need a
REM      force-push, which is FORBIDDEN). It tells you to rotate the key instead.
REM    * Uses `git reset --soft` ONLY. Never --hard, never rebase, never amend,
REM      never filter-branch, never force-push. NO file content is ever lost.
REM    * The recovered commit stays in `git reflog` for ~90 days regardless.
REM
REM  USAGE
REM    uncommit-keys.bat          scan, then ask before fixing
REM    uncommit-keys.bat /y       scan and fix without asking
REM    uncommit-keys.bat /scan    report only, never change anything
REM    uncommit-keys.bat /?       this help
REM
REM  EXIT CODES   0 = clean   1 = leak found (scan mode)   2 = leak already pushed
REM               3 = not a git repo / git missing
REM ============================================================================

cd /d "%~dp0"

set "MODE=fix"
set "ASSUME_YES=0"
for %%A in (%*) do (
    if /i "%%~A"=="/scan"   set "MODE=scan"
    if /i "%%~A"=="/y"      set "ASSUME_YES=1"
    if /i "%%~A"=="/?"      goto :usage
    if /i "%%~A"=="-h"      goto :usage
    if /i "%%~A"=="--help"  goto :usage
)

REM --- the tracked files that legitimately carry real secrets locally ---------
set "SECRETS=Tlamatini/agent/config.json Tlamatini/agent/agents/telegrammer/config.yaml Tlamatini/agent/agents/whatsapper/config.yaml Tlamatini/agent/agents/teletlamatini/config.yaml Tlamatini/agent/agents/emailer/config.yaml Tlamatini/agent/agents/recmailer/config.yaml Tlamatini/agent/agents/zavuerer/config.yaml Tlamatini/agent/agents/discoverer/config.yaml"

echo(
echo ============================================================
echo   uncommit-keys  -  secret-leak check for %CD%
echo ============================================================

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo   [X] Not a git repository ^(or git is not on PATH^).
    exit /b 3
)

REM --- resolve the upstream branch we compare against -------------------------
set "UP="
for /f "delims=" %%U in ('git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2^>nul') do set "UP=%%U"
if not defined UP set "UP=origin/main"

git rev-parse --verify --quiet "%UP%" >nul 2>&1
if errorlevel 1 (
    echo   [X] Cannot resolve upstream '%UP%'. Run: git fetch origin
    exit /b 3
)

set "AHEAD=0"
for /f %%N in ('git rev-list --count %UP%..HEAD 2^>nul') do set "AHEAD=%%N"

echo   upstream        : %UP%
echo   unpushed commits: %AHEAD%
echo(

REM --- safety: data.keys must never be tracked --------------------------------
git ls-files --error-unmatch data.keys >nul 2>&1
if not errorlevel 1 (
    echo   [!!] data.keys is TRACKED by git. It must be gitignored. Fix that first.
    echo(
)

call :scan
if "%PUSHEDLEAK%"=="1" (
    echo(
    echo ============================================================
    echo   STOP  -  a secret is ALREADY on the remote ^(%UP%^).
    echo ============================================================
    echo   This CANNOT be fixed by uncommitting: the commit is published,
    echo   and rewriting/force-pushing published history is FORBIDDEN.
    echo(
    echo   Do this instead:
    echo     1. ROTATE / REVOKE the exposed key at the provider NOW.
    echo     2. python regen_secrets.py --mode push-able
    echo     3. git add ^<the scrubbed files^>
    echo     4. git commit -m "Redact leaked key, by angelahack1"
    echo     5. git push origin main          ^(a NEW forward commit^)
    echo   The past stays untouched. Tell Angela before doing anything else.
    exit /b 2
)

if "%NLEAK%"=="0" if "%NSTAGED%"=="0" (
    echo   [OK] No real keys in your unpushed commits or staged changes.
    echo   [OK] Safe to push.
    exit /b 0
)

echo(
echo   Found %NLEAK% leaked file^(s^) in unpushed commits, %NSTAGED% staged.

if /i "%MODE%"=="scan" (
    echo   ^(scan mode - nothing changed^)
    exit /b 1
)

if "%ASSUME_YES%"=="0" (
    echo(
    echo   Planned fix ^(local only, NOTHING is deleted^):
    if not "%NLEAK%"=="0" echo     git reset --soft %UP%        ^<- undo unpushed commit^(s^), keep every change
    echo     git reset HEAD -- ^<secret files^>   ^<- unstage them back to normal
    if "%AHEAD%"=="1" echo     git commit -m "^<your original message^>"
    echo(
    set /p "ANS=  Proceed? [y/N] "
    if /i not "!ANS!"=="y" (
        echo   Aborted. Nothing changed.
        exit /b 1
    )
)

REM --- save the FULL original commit message (subject + body + trailers) ------
REM     A message FILE + `git commit -F` preserves multi-line messages exactly
REM     and sidesteps every batch quote-escaping trap.
set "MSGFILE=%~dp0Temp\uncommit-keys-msg.txt"
set "HAVEMSG="
if not exist "%~dp0Temp" mkdir "%~dp0Temp" >nul 2>&1
if not "%AHEAD%"=="0" (
    git log -1 --pretty=%%B > "!MSGFILE!" 2>nul
    if exist "!MSGFILE!" set "HAVEMSG=1"
)

echo(
if not "%NLEAK%"=="0" (
    echo   -^> git reset --soft %UP%
    git reset --soft %UP%
    if errorlevel 1 ( echo   [X] reset failed - nothing else attempted. & exit /b 3 )
)

echo   -^> unstaging the secret files
git reset -q HEAD -- %SECRETS%

if "%AHEAD%"=="1" (
    if defined HAVEMSG (
        echo   -^> git commit -F ^(your original message, preserved verbatim^)
        git commit -q -F "!MSGFILE!"
        del "!MSGFILE!" >nul 2>&1
    ) else (
        echo   [!] Could not read the original message. Your safe changes stay STAGED.
        echo       Commit them yourself with: git commit -m "your message"
    )
) else (
    if not "%AHEAD%"=="0" (
        echo   [!] %AHEAD% commits were folded back into the staging area.
        echo       Your safe changes stay STAGED - commit them yourself:
        echo         git commit -m "your message"
    )
)

REM --- prove it worked --------------------------------------------------------
echo(
echo   verifying...
call :scan
if "%NLEAK%"=="0" if "%NSTAGED%"=="0" (
    echo   [OK] Clean. The secret files are back to normal 'modified, not staged'.
    echo   [OK] Your keys are untouched on disk. Safe to push.
    exit /b 0
)
echo   [X] Still dirty - do NOT push. Show this output to Claude/Angela.
exit /b 1


REM ===========================================================================
:scan
REM  Sets NLEAK (leaks in unpushed commits), NSTAGED (leaks staged),
REM       PUSHEDLEAK (1 if the remote itself already holds real keys).
set "NLEAK=0"
set "NSTAGED=0"
set "PUSHEDLEAK=0"

for %%F in (%SECRETS%) do (
    REM placeholders the upstream (correct, push-able) copy has
    set "REF=0"
    for /f %%C in ('git show %UP%:%%F 2^>nul ^| find /c "goes here"') do set "REF=%%C"

    if !REF! EQU 0 (
        git cat-file -e %UP%:%%F 2>nul && (
            echo   [!!] PUSHED LEAK: %%F has 0 placeholders on %UP%
            set "PUSHEDLEAK=1"
        )
    ) else (
        REM ---- is it inside an unpushed commit, and is it dirty? -------------
        set "INDIFF="
        for /f "delims=" %%D in ('git diff --name-only %UP%..HEAD -- %%F 2^>nul') do set "INDIFF=1"
        if defined INDIFF (
            set "CUR=0"
            for /f %%C in ('git show HEAD:%%F 2^>nul ^| find /c "goes here"') do set "CUR=%%C"
            if !CUR! LSS !REF! (
                echo   [LEAK] committed: %%F   ^(placeholders !CUR! ^< !REF! expected^)
                set /a NLEAK+=1
            )
        )
        REM ---- is it staged right now (catches it BEFORE you commit)? --------
        git diff --cached --quiet -- %%F 2>nul || (
            set "SCUR=0"
            for /f %%C in ('git show :%%F 2^>nul ^| find /c "goes here"') do set "SCUR=%%C"
            if !SCUR! LSS !REF! (
                echo   [LEAK] STAGED:    %%F   ^(placeholders !SCUR! ^< !REF! expected^)
                set /a NSTAGED+=1
            )
        )
    )
)
exit /b 0


REM ===========================================================================
:usage
echo(
echo   uncommit-keys.bat  -  undo an UNPUSHED commit that contains real API keys.
echo(
echo     uncommit-keys.bat          scan, then ask before fixing
echo     uncommit-keys.bat /y       scan and fix without asking
echo     uncommit-keys.bat /scan    report only, never change anything
echo     uncommit-keys.bat /?       this help
echo(
echo   Never rewrites pushed history. Never force-pushes. Never loses a file.
exit /b 0
