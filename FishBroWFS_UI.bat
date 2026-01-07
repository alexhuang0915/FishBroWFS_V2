@echo off
REM =========================================================
REM FishBroWFS Desktop UI Launcher for Windows + WSL
REM Sole human entrypoint. Approved by constitution.
REM =========================================================
title FishBroWFS Desktop UI

REM Configurable WSL distribution (default: Ubuntu)
set WSL_DISTRO=Ubuntu

REM Project path inside WSL
set PROJECT_PATH=/home/fishbro/FishBroWFS_V2

REM Log file for debugging
set LOG_FILE=%TEMP%\FishBroWFS_UI_launcher.log

echo ========================================================= > "%LOG_FILE%"
echo FishBroWFS Desktop UI Launcher >> "%LOG_FILE%"
echo ========================================================= >> "%LOG_FILE%"
echo Timestamp: %DATE% %TIME% >> "%LOG_FILE%"
echo WSL Distribution: %WSL_DISTRO% >> "%LOG_FILE%"
echo Project Path: %PROJECT_PATH% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

echo =========================================================
echo FishBroWFS Desktop UI Launcher
echo =========================================================
echo WSL Distribution: %WSL_DISTRO%
echo Project Path: %PROJECT_PATH%
echo Log file: %LOG_FILE%
echo.

REM Check if WSL is installed and available
where wsl >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: WSL (Windows Subsystem for Linux) is not installed or not in PATH. >> "%LOG_FILE%"
    echo ERROR: WSL (Windows Subsystem for Linux) is not installed or not in PATH.
    echo Please install WSL from Microsoft Store or enable it via:
    echo   wsl --install
    echo.
    echo See log file for details: %LOG_FILE%
    pause
    exit /b 1
)
echo WSL found in PATH. >> "%LOG_FILE%"

REM Check if the specified WSL distribution exists
wsl -d %WSL_DISTRO% -- echo "Checking WSL distribution..." >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: WSL distribution "%WSL_DISTRO%" not found. >> "%LOG_FILE%"
    echo ERROR: WSL distribution "%WSL_DISTRO%" not found.
    echo Available distributions:
    wsl --list --quiet
    echo.
    echo Please update WSL_DISTRO variable in this script or install the distribution.
    echo.
    echo See log file for details: %LOG_FILE%
    pause
    exit /b 1
)
echo WSL distribution "%WSL_DISTRO%" verified. >> "%LOG_FILE%"

REM Check if project path exists in WSL
wsl -d %WSL_DISTRO% -- bash -c "if [ -d '%PROJECT_PATH%' ]; then exit 0; else exit 1; fi" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Project path "%PROJECT_PATH%" does not exist in WSL. >> "%LOG_FILE%"
    echo ERROR: Project path "%PROJECT_PATH%" does not exist in WSL.
    echo Please ensure the project is cloned to the correct location.
    echo.
    echo See log file for details: %LOG_FILE%
    pause
    exit /b 1
)
echo Project path "%PROJECT_PATH%" verified. >> "%LOG_FILE%"

REM Check if .venv exists in project
wsl -d %WSL_DISTRO% -- bash -c "if [ -d '%PROJECT_PATH%/.venv' ]; then exit 0; else exit 1; fi" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo WARNING: Virtual environment (.venv) not found at "%PROJECT_PATH%/.venv". >> "%LOG_FILE%"
    echo WARNING: Virtual environment (.venv) not found at "%PROJECT_PATH%/.venv".
    echo Attempting to continue anyway...
    echo.
)

echo Launching FishBroWFS Desktop UI via WSL... >> "%LOG_FILE%"
echo Launching FishBroWFS Desktop UI via WSL...
echo.

REM Command to run inside WSL:
REM 1. Change to project directory
REM 2. Activate virtual environment (.venv)
REM 3. Run the canonical desktop launcher
set WSL_COMMAND=cd "%PROJECT_PATH%" && if [ -f .venv/bin/activate ]; then source .venv/bin/activate; fi && python scripts/desktop_launcher.py

echo Executing: wsl -d %WSL_DISTRO% -- bash -lc "%WSL_COMMAND%" >> "%LOG_FILE%"

REM Execute via WSL with stdout/stderr redirected to log
wsl -d %WSL_DISTRO% -- bash -lc "%WSL_COMMAND%" 1>> "%LOG_FILE%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo Exit code: %EXIT_CODE% >> "%LOG_FILE%"

REM Check exit code
if %EXIT_CODE% neq 0 (
    echo. >> "%LOG_FILE%"
    echo ERROR: Desktop UI exited with error code %EXIT_CODE% >> "%LOG_FILE%"
    echo.
    echo ERROR: Desktop UI exited with error code %EXIT_CODE%
    echo.
    echo Check log file for details: %LOG_FILE%
) else (
    echo. >> "%LOG_FILE%"
    echo Desktop UI closed successfully. >> "%LOG_FILE%"
    echo.
    echo Desktop UI closed successfully.
    echo.
)

echo ========================================================= >> "%LOG_FILE%"
echo Launcher finished at %DATE% %TIME% >> "%LOG_FILE%"
echo ========================================================= >> "%LOG_FILE%"

pause
exit /b %EXIT_CODE%