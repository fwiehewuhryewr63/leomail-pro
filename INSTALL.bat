@echo off
chcp 65001 >nul 2>nul
title LEOMAIL — STEP 1: Install Python and Node.js
color 0a
cd /d "%~dp0"

echo.
echo  ========================================
echo   STEP 1: Install Python and Node.js
echo  ========================================
echo.
echo  This script will open download pages.
echo  Install both, then run INSTALL.bat
echo.

where python >nul 2>&1
if %errorLevel% neq 0 (
    echo  [!] Python NOT FOUND
    echo  [*] Opening Python download page...
    echo  [*] IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    start https://www.python.org/downloads/
    echo  After installing Python, close this window
    echo  and run INSTALL.bat
    echo.
    set /p dummy=Press ENTER when Python is installed...
    exit /b
) else (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo  [OK] %%i
)

where node >nul 2>&1
if %errorLevel% neq 0 (
    echo  [!] Node.js NOT FOUND
    echo  [*] Opening Node.js download page...
    echo.
    start https://nodejs.org
    echo  After installing Node.js, close this window
    echo  and run INSTALL.bat
    echo.
    set /p dummy=Press ENTER when Node.js is installed...
    exit /b
) else (
    for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo  [OK] Node.js %%i
)

echo.
echo  [OK] Python and Node.js ready!
echo.
echo  ========================================
echo   STEP 2: Installing dependencies...
echo  ========================================
echo.

echo  [2/4] Python packages...
python -m pip install --upgrade pip 2>nul
python -m pip install -r requirements.txt
if %errorLevel% neq 0 (
    echo.
    echo  [ERROR] pip install failed!
    set /p dummy=Press ENTER to exit...
    exit /b 1
)
echo  [OK] Python packages installed

echo  [3/4] Frontend packages...
cd /d "%~dp0frontend"
call npm install
if %errorLevel% neq 0 (
    echo.
    echo  [ERROR] npm install failed!
    set /p dummy=Press ENTER to exit...
    exit /b 1
)

echo  [4/4] Building frontend...
call npm run build
if %errorLevel% neq 0 (
    echo.
    echo  [ERROR] Build failed!
    set /p dummy=Press ENTER to exit...
    exit /b 1
)
cd /d "%~dp0"

echo.
echo  ========================================
echo   INSTALLATION COMPLETE!
echo  ========================================
echo.
echo  Now run START.bat to launch Leomail
echo  Then open http://localhost:8000
echo.
set /p dummy=Press ENTER to close...
