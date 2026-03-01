@echo off
chcp 65001 >nul
title LEOMAIL — Build Electron App
color 0e

set "ROOT=%~dp0"

echo.
echo  ════════════════════════════════════════
echo   LEOMAIL v4.0 — BUILD ELECTRON APP
echo  ════════════════════════════════════════
echo.

:: Step 1: Build frontend
echo  [1/3] Building frontend...
cd /d "%ROOT%frontend"
call npm run build
if errorlevel 1 (
    echo  [ERROR] Frontend build failed!
    pause
    exit /b 1
)
echo        Frontend build OK.

:: Step 2: Install Electron deps
echo  [2/3] Installing Electron dependencies...
cd /d "%ROOT%electron"
call npm install
if errorlevel 1 (
    echo  [ERROR] npm install failed!
    pause
    exit /b 1
)
echo        Dependencies installed.

:: Step 3: Build Electron app
echo  [3/3] Packaging Electron app...
call npm run build
if errorlevel 1 (
    echo  [ERROR] Electron build failed!
    pause
    exit /b 1
)

echo.
echo  ════════════════════════════════════════
echo   BUILD COMPLETE!
echo  ════════════════════════════════════════
echo.
echo  Output: electron\dist\
echo.
echo  Look for "Leomail Setup *.exe" in the dist folder
echo.
pause
