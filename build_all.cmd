@echo off
setlocal EnableExtensions
REM ===========================================================================
REM  build_all.cmd  —  Build Tlamatini end-to-end using ONLY the repo-local
REM  Python ("<this-folder>\python", copied from C:\Tlamatini\python).
REM
REM  - Works from ANY location: it resolves its own folder, so it is identical
REM    whether the dev tree lives in C:\Development\Tlamatini or F:\Jajaja\Devsz\Tlamatini.
REM  - IGNORES every other Python on the machine (system C:\Program Files\Python,
REM    per-user C:\Users\...\AppData, IDE / Antigravity / VSCode interpreters):
REM    the interpreter is always invoked by ABSOLUTE path, the user site-packages
REM    are disabled, and PYTHON* env vars are cleared, so PyInstaller collects its
REM    assets from the LOCAL python's site-packages and nothing else.
REM  - Runs, in order:  1) build.py --self-modify   2) build_uninstaller.py
REM                     3) build_installer.py
REM ===========================================================================

REM --- Repo root = the folder this script sits in (drive-independent) ---
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

set "LOCAL_PY_DIR=%REPO_ROOT%\python"
set "LOCAL_PY=%LOCAL_PY_DIR%\python.exe"

REM --- The local python MUST exist; refuse to fall back to any other one ---
if not exist "%LOCAL_PY%" (
    echo [ERROR] Local Python not found at "%LOCAL_PY%".
    echo         Copy the runtime python into the dev tree first, e.g.:
    echo            xcopy /E /I /H /Y "C:\Tlamatini\python" "%REPO_ROOT%\python"
    exit /b 1
)

REM --- ISOLATION: make the local python the ONLY python that can be seen ---
REM  Prepend the local python dirs to PATH so any bare "python" resolves here,
REM  while keeping the rest of PATH so git / makensis (NSIS) stay reachable.
set "PATH=%LOCAL_PY_DIR%;%LOCAL_PY_DIR%\Scripts;%PATH%"
REM  Neutralize anything that could leak an EXTERNAL python's packages in:
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONSTARTUP="
set "PYTHONNOUSERSITE=1"
REM  If a build step needs to pip-install a lib, force it into the LOCAL python's
REM  own site-packages (NOT the shared per-user C:\Users\...\AppData site, which
REM  PYTHONNOUSERSITE=1 hides from the build). Keeps the local python self-contained.
set "PIP_USER=0"
set "PIP_REQUIRE_VIRTUALENV=0"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo ===========================================================================
echo  Tlamatini full build  —  LOCAL python only
echo  Repo root : %REPO_ROOT%
echo  Python    : %LOCAL_PY%
echo ===========================================================================
"%LOCAL_PY%" -c "import sys; print('Interpreter :', sys.executable); print('Version     :', sys.version.split()[0])"
if errorlevel 1 ( echo [ERROR] The local python failed to run. & exit /b 1 )
echo.

cd /d "%REPO_ROOT%" || ( echo [ERROR] Cannot enter repo root "%REPO_ROOT%". & exit /b 1 )

echo === [1/3] build.py --self-modify ===
"%LOCAL_PY%" build.py --self-modify
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" ( echo [ERROR] build.py --self-modify FAILED ^(exit %RC%^). & goto :fail )
echo.

echo === [2/3] build_uninstaller.py ===
"%LOCAL_PY%" build_uninstaller.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" ( echo [ERROR] build_uninstaller.py FAILED ^(exit %RC%^). & goto :fail )
echo.

echo === [3/3] build_installer.py ===
"%LOCAL_PY%" build_installer.py
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
