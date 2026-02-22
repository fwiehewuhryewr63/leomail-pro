@echo off
chcp 65001 >nul
title Leomail — Full Setup
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║          LEOMAIL v3 — FULL SETUP                 ║
echo ║   Installs Python, Node.js, dependencies         ║
echo ╚══════════════════════════════════════════════════╝
echo.

REM === Check if running as admin ===
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Запустите от имени Администратора!
    echo         ПКМ → Запуск от имени администратора
    pause
    exit /b 1
)

cd /d "%~dp0"
set "ROOT=%~dp0"

REM === 1. Install Chocolatey (package manager) ===
echo [1/7] Установка Chocolatey...
where choco >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    echo [OK] Chocolatey установлен
    SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"
) else (
    echo [OK] Chocolatey уже установлен
)

REM === 2. Install Python ===
echo.
echo [2/7] Установка Python 3.11...
where python >nul 2>&1
if %errorlevel% neq 0 (
    choco install python311 -y --no-progress
    echo [OK] Python установлен
    refreshenv
) else (
    echo [OK] Python уже установлен
    python --version
)

REM === 3. Install Node.js ===
echo.
echo [3/7] Установка Node.js 20 LTS...
where node >nul 2>&1
if %errorlevel% neq 0 (
    choco install nodejs-lts -y --no-progress
    echo [OK] Node.js установлен
    refreshenv
) else (
    echo [OK] Node.js уже установлен
    node --version
)

REM === 4. Install Git ===
echo.
echo [4/7] Установка Git...
where git >nul 2>&1
if %errorlevel% neq 0 (
    choco install git -y --no-progress
    echo [OK] Git установлен
    refreshenv
) else (
    echo [OK] Git уже установлен
)

REM === 5. Python dependencies ===
echo.
echo [5/7] Установка Python зависимостей...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARN] Некоторые зависимости не установились, продолжаем...
)
echo [OK] Python зависимости установлены

REM === 6. Playwright browsers ===
echo.
echo [6/7] Установка Playwright браузеров...
python -m playwright install chromium
python -m playwright install-deps
echo [OK] Playwright браузеры установлены

REM === 7. Frontend dependencies + build ===
echo.
echo [7/7] Установка frontend и сборка...
cd frontend
call npm install
call npm run build
cd ..

REM === Create user_data directory ===
if not exist "user_data" mkdir user_data

REM === Open firewall ports ===
echo.
echo [FIREWALL] Открываем порты 8000, 5173...
netsh advfirewall firewall add rule name="Leomail Backend" dir=in action=allow protocol=tcp localport=8000 >nul 2>&1
netsh advfirewall firewall add rule name="Leomail Frontend" dir=in action=allow protocol=tcp localport=5173 >nul 2>&1
echo [OK] Порты открыты

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║          УСТАНОВКА ЗАВЕРШЕНА!                     ║
echo ║                                                   ║
echo ║   Запустите START.bat для запуска Leomail          ║
echo ║   Web UI: http://localhost:5173                   ║
echo ║   API:    http://localhost:8000                   ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
