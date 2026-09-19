@echo off
REM Antigravity Migrate - One-Click Windows Export Launcher
cd /d "%~dp0"
title Antigravity Migration Tool

where python >nul 2>&1
if %errorlevel% equ 0 (
    python -m antigravity_migrate
) else (
    echo.
    echo [ERROR] Python 3 was not found in your PATH.
    echo Please install Python 3 from python.org or Microsoft Store and ensure
    echo "Add python.exe to PATH" is checked.
    pause
    exit /b 1
)
