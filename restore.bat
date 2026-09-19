@echo off
REM Antigravity Migrate - One-Click Windows Restorer Launcher
cd /d "%~dp0"

echo ================================================================================
echo           Starting Antigravity Restoration on Windows Target System             
echo ================================================================================

where python >nul 2>&1
if %errorlevel% equ 0 (
    python restore.py %*
) else (
    echo.
    echo [ERROR] Python 3 was not found in your PATH.
    echo Please install Python 3 from python.org or the Microsoft Store and ensure
    echo "Add python.exe to PATH" is checked.
    pause
    exit /b 1
)
