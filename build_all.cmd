@echo off
setlocal EnableExtensions
REM ===========================================================================
REM  build_all.cmd  —  Build Tlamatini end-to-end.
REM
REM  IMPORTANT: build.py must be launched with a SEPARATE *system* Python, NOT
REM  the carried "<repo>\python". build.py provisions/copies that carried tree
REM  itself (ensure_local_build_python + bundle_carried_python) and ABORTS early
REM  if it detects it was started with it:
REM      "ERROR: build.py was launched WITH the carried Python (...). Aborting."
REM  That guard is exactly why the old version of this script failed while the
REM  manual "python build.py ..." (which used C:\Program Files\Python312) worked.
REM
REM  - Works from ANY location: it resolves its own folder.
REM  - Runs, in order:  1) build.py --self-modify   2) build_uninstaller.py
REM                     3) build_installer.py
REM ===========================================================================

REM --- Repo root = the folder this script sits in (drive-independent) ---
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

set "CARRIED_PY_DIR=%REPO_ROOT%\python"

REM --- Pick a SYSTEM Python to RUN the build scripts (never the carried one) ---
set "BUILD_PY="
if exist "%PROGRAMFILES%\Python312\python.exe" set "BUILD_PY=%PROGRAMFILES%\Python312\python.exe"

REM  Fallback: first "python" on PATH that is NOT under <repo>\python.
if not defined BUILD_PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined BUILD_PY (
            echo %%~dpP| findstr /I /C:"%CARRIED_PY_DIR%\\" >nul || set "BUILD_PY=%%P"
        )
    )
)

if not defined BUILD_PY (
    echo [ERROR] No system Python 3.12 found to run the build.
    echo         Install Python 3.12.10 ^(e.g. "%PROGRAMFILES%\Python312\python.exe"^)
    echo         and re-run, or run the scripts manually.
    exit /b 1
)

REM --- Safety: refuse if BUILD_PY somehow points at the carried tree ---
echo %BUILD_PY%| findstr /I /C:"%CARRIED_PY_DIR%\\" >nul && (
    echo [ERROR] Selected build Python is the carried "<repo>\python":
    echo            %BUILD_PY%
    echo         build.py forbids this. Use a separate system Python 3.12.10.
    exit /b 1
)

REM --- Clear PYTHON* env so the build Python uses its OWN packages cleanly ---
REM  (PYTHONPATH / PYTHONHOME pointing at the carried tree would leak the wrong
REM   site-packages into the build interpreter.)
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="

echo ===========================================================================
echo  Tlamatini full build
echo  Repo root  : %REPO_ROOT%
echo  Build Py   : %BUILD_PY%   ^(runs the scripts^)
echo  Carried Py : %CARRIED_PY_DIR%   ^(provisioned by build.py^)
echo ===========================================================================
"%BUILD_PY%" -c "import sys; print('Interpreter :', sys.executable); print('Version     :', sys.version.split()[0])"
if errorlevel 1 ( echo [ERROR] The build Python failed to run. & exit /b 1 )
echo.

cd /d "%REPO_ROOT%" || ( echo [ERROR] Cannot enter repo root "%REPO_ROOT%". & exit /b 1 )

echo === [1/3] build.py --self-modify ===
"%BUILD_PY%" build.py --self-modify
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" ( echo [ERROR] build.py --self-modify FAILED ^(exit %RC%^). & goto :fail )
echo.

echo === [2/3] build_uninstaller.py ===
"%BUILD_PY%" build_uninstaller.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" ( echo [ERROR] build_uninstaller.py FAILED ^(exit %RC%^). & goto :fail )
echo.

echo === [3/3] build_installer.py ===
"%BUILD_PY%" build_installer.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" ( echo [ERROR] build_installer.py FAILED ^(exit %RC%^). & goto :fail )
echo.

echo ===========================================================================
echo  ALL BUILDS COMPLETED SUCCESSFULLY
echo ===========================================================================
endlocal
exit /b 0

:fail
echo ===========================================================================
echo  BUILD ABORTED — see the error above.
echo ===========================================================================
endlocal
exit /b %RC%
