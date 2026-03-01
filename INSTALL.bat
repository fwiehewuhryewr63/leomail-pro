@echo off
chcp 65001 >nul
title LEOMAIL — Install Dependencies
color 0e

echo.
echo  ════════════════════════════════════════
echo   LEOMAIL v4.0 — INSTALL DEPENDENCIES
echo  ════════════════════════════════════════
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found!
    echo  Please install Python 3.10+ from https://python.org
    echo  Make sure to check "Add Python to PATH"
    pause
    exit /b 1
)

echo  [1/2] Python found:
python --version
echo.

:: Install requirements
echo  [2/2] Installing Python dependencies...
pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo  [ERROR] pip install failed!
    pause
    exit /b 1
)

echo.
echo  ════════════════════════════════════════
echo   DONE! All dependencies installed.
echo  ════════════════════════════════════════
echo.
echo  You can now run Leomail.exe
echo.
pause
