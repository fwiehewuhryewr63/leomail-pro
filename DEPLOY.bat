@echo off
chcp 65001 >nul
title LEOMAIL — DEPLOY
color 0e

set "SCRIPT_DIR=%~dp0"
set "INSTALL_DIR=%USERPROFILE%\Desktop\Leomail"
set "BACKUP_DIR=%USERPROFILE%\Desktop\_leomail_backup"

echo.
echo  ════════════════════════════════════════════
echo          LEOMAIL v2.3 — AUTO DEPLOY
echo  ════════════════════════════════════════════
echo.
echo  Install dir: %INSTALL_DIR%
echo.

:: ═══════════════════════════════════════════
:: STEP 1: Stop running Leomail
:: ═══════════════════════════════════════════
echo  [1/6] Stopping Leomail if running...
taskkill /f /fi "WINDOWTITLE eq LEOMAIL*" >nul 2>&1
taskkill /f /im "python.exe" /fi "WINDOWTITLE eq LEOMAIL*" >nul 2>&1
timeout /t 2 >nul
echo        Done.

:: ═══════════════════════════════════════════
:: STEP 2: Backup user_data if exists
:: ═══════════════════════════════════════════
echo  [2/6] Checking for existing data...
if exist "%INSTALL_DIR%\user_data" (
    echo        Found user_data — backing up...
    if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
    mkdir "%BACKUP_DIR%"
    xcopy "%INSTALL_DIR%\user_data" "%BACKUP_DIR%\user_data\" /E /I /Q >nul
    echo        Backup saved to: %BACKUP_DIR%
) else (
    echo        No existing data found (fresh install)
)

:: ═══════════════════════════════════════════
:: STEP 3: Remove old installation
:: ═══════════════════════════════════════════
echo  [3/6] Removing old installation...
if exist "%INSTALL_DIR%" (
    rmdir /s /q "%INSTALL_DIR%"
    timeout /t 1 >nul
)
echo        Done.

:: ═══════════════════════════════════════════
:: STEP 4: Copy new files
:: ═══════════════════════════════════════════
echo  [4/6] Installing new version...
mkdir "%INSTALL_DIR%" 2>nul
xcopy "%SCRIPT_DIR%backend" "%INSTALL_DIR%\backend\" /E /I /Q >nul
xcopy "%SCRIPT_DIR%frontend" "%INSTALL_DIR%\frontend\" /E /I /Q >nul
copy /y "%SCRIPT_DIR%requirements.txt" "%INSTALL_DIR%\requirements.txt" >nul 2>&1
copy /y "%SCRIPT_DIR%START.bat" "%INSTALL_DIR%\START.bat" >nul 2>&1
copy /y "%SCRIPT_DIR%INSTALL.bat" "%INSTALL_DIR%\INSTALL.bat" >nul 2>&1
copy /y "%SCRIPT_DIR%DEPLOY.bat" "%INSTALL_DIR%\DEPLOY.bat" >nul 2>&1
echo        Files copied.

:: ═══════════════════════════════════════════
:: STEP 5: Restore user_data
:: ═══════════════════════════════════════════
echo  [5/6] Restoring data...
if exist "%BACKUP_DIR%\user_data" (
    xcopy "%BACKUP_DIR%\user_data" "%INSTALL_DIR%\user_data\" /E /I /Q >nul
    echo        Data restored! (accounts, farms, proxies, keys)
    rmdir /s /q "%BACKUP_DIR%"
) else (
    mkdir "%INSTALL_DIR%\user_data" 2>nul
    echo        Fresh install — empty data created.
)

:: ═══════════════════════════════════════════
:: STEP 6: Install dependencies
:: ═══════════════════════════════════════════
echo  [6/6] Installing dependencies...

:: Check Python
where python >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo  [!] Python NOT FOUND — install Python 3.10+ first!
    echo  [!] https://www.python.org/downloads/
    echo  [!] IMPORTANT: Check "Add Python to PATH"
    start https://www.python.org/downloads/
    echo.
    set /p dummy=Press ENTER after installing Python...
)

:: Check Node.js
where node >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo  [!] Node.js NOT FOUND — install Node.js 18+ first!
    echo  [!] https://nodejs.org
    start https://nodejs.org
    echo.
    set /p dummy=Press ENTER after installing Node.js...
)

:: Python packages
echo        Installing Python packages...
cd /d "%INSTALL_DIR%"
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt >nul 2>&1

:: Frontend packages
echo        Installing frontend packages...
cd /d "%INSTALL_DIR%\frontend"
call npm install --silent >nul 2>&1

:: Build frontend (если dist уже есть — пересобирает)
echo        Building frontend...
call npm run build >nul 2>&1
if errorlevel 1 (
    echo  [!] Frontend build had issues, but dist/ may already be included.
)

cd /d "%INSTALL_DIR%"

:: Remove __pycache__
for /d /r "%INSTALL_DIR%\backend" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

echo.
echo  ════════════════════════════════════════════
echo          DEPLOY COMPLETE!
echo  ════════════════════════════════════════════
echo.
echo  Location: %INSTALL_DIR%
echo  Data:     %INSTALL_DIR%\user_data
echo.
echo  Run START.bat to launch Leomail!
echo  Open: http://localhost:8000
echo.
pause
