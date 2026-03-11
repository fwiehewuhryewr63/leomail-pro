@echo off
chcp 65001 >nul
title LEOMAIL - Build EXE
color 0e

set "ROOT=%~dp0"
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(Get-Content '%ROOT%version.json' -Raw | ConvertFrom-Json).version"`) do set "APP_VERSION=%%v"
set "RUNTIME_ARCHIVE=%USERPROFILE%\Desktop\Leomail_runtime_v%APP_VERSION%.zip"

echo.
echo  ========================================
echo   LEOMAIL - BUILD NATIVE EXE
echo   PyInstaller + pywebview = native app
echo  ========================================
echo.

:: Step 1: Install build dependencies
echo  [1/4] Installing build dependencies...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo  [ERROR] Failed to install pyinstaller.
    pause
    exit /b 1
)
echo        pyinstaller OK.

:: Step 2: Build frontend
echo  [2/4] Building frontend...
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    call npm install --silent
)
call npm run build
if errorlevel 1 (
    echo  [ERROR] npm run build failed.
    pause
    exit /b 1
)
echo        Frontend build OK.
cd /d "%ROOT%"

:: Step 3: Build EXE with PyInstaller
echo  [3/4] Building EXE with PyInstaller...
python -m PyInstaller --clean --noconfirm Leomail.spec
if errorlevel 1 (
    echo  [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)
echo        PyInstaller build OK.

:: Step 4: Prepare boxed runtime + archive
echo  [4/4] Preparing boxed runtime...
if not exist "dist\Leomail\user_data" mkdir "dist\Leomail\user_data"
if not exist "dist\Leomail\user_data\sessions" mkdir "dist\Leomail\user_data\sessions"
if not exist "dist\Leomail\user_data\logs" mkdir "dist\Leomail\user_data\logs"
if not exist "dist\Leomail\user_data\exports" mkdir "dist\Leomail\user_data\exports"
copy /y "%ROOT%version.json" "dist\Leomail\version.json" >nul 2>&1

if exist "%RUNTIME_ARCHIVE%" del /f /q "%RUNTIME_ARCHIVE%" >nul 2>&1
powershell -NoProfile -Command "Compress-Archive -Path '%ROOT%dist\Leomail' -DestinationPath '%RUNTIME_ARCHIVE%' -Force"
if errorlevel 1 (
    echo  [ERROR] Failed to create runtime archive.
    pause
    exit /b 1
)
echo        Runtime archive OK.

echo.
echo  ========================================
echo   BUILD COMPLETE!
echo  ========================================
echo.
echo   EXE: dist\Leomail\Leomail.exe
echo   RUNTIME ZIP: %RUNTIME_ARCHIVE%
echo.
echo   EXE SHA-256:
certutil -hashfile "dist\Leomail\Leomail.exe" SHA256 2>nul | findstr /v "hash CertUtil"
echo.
echo   ZIP SHA-256:
certutil -hashfile "%RUNTIME_ARCHIVE%" SHA256 2>nul | findstr /v "hash CertUtil"
echo.
echo   For GitHub Release, use the ZIP hash above:
echo     sha256: ^<hash^>
echo.
echo   Inside dist\Leomail\:
echo     Leomail.exe      - main app
echo     _internal\       - bundled runtime
echo     user_data\       - empty template folders
echo     version.json     - current version
echo.
echo   Mega / VPS flow:
echo     1. Upload %RUNTIME_ARCHIVE% to Mega
echo     2. Download and unpack it on the VPS
echo     3. Run Leomail.exe
echo.
pause
