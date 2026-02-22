@echo off
chcp 65001 >nul
title Leomail — START
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║           LEOMAIL v3 — ЗАПУСК                     ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM === Refresh PATH from registry (in case opened in stale cmd) ===
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%b"
set "PATH=%SYS_PATH%;%USR_PATH%;%ALLUSERSPROFILE%\chocolatey\bin;%APPDATA%\npm"

REM === Verify tools ===
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python не найден! Запустите SETUP.bat сначала.
    pause
    exit /b 1
)

REM === Kill old processes ===
echo [1/3] Останавливаем старые процессы...
taskkill /f /im "python.exe" >nul 2>&1
taskkill /f /im "node.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

REM === Check uvicorn installed ===
python -c "import uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo [FIX] uvicorn не найден, устанавливаем зависимости...
    python -m pip install -r requirements.txt
)

REM === Check frontend node_modules ===
if not exist "frontend\node_modules" (
    echo [FIX] node_modules не найден, устанавливаем...
    cd frontend
    call npm install
    cd ..
)

REM === Start Backend ===
echo [2/3] Запуск Backend (порт 8000)...
start "Leomail Backend" cmd /k "cd /d "%~dp0" && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

REM === Start Frontend ===
echo [3/3] Запуск Frontend (порт 5173)...
if exist "frontend\dist\index.html" (
    REM Production build exists — serve it
    start "Leomail Frontend" cmd /k "cd /d "%~dp0\frontend" && npx -y serve dist -l 5173 --cors"
) else (
    REM Dev mode
    start "Leomail Frontend" cmd /k "cd /d "%~dp0\frontend" && npx -y vite --host 0.0.0.0 --port 5173"
)

timeout /t 3 /nobreak >nul

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║           LEOMAIL ЗАПУЩЕН!                        ║
echo ║                                                   ║
echo ║   Web UI:  http://localhost:5173                  ║
echo ║   API:     http://localhost:8000/docs             ║
echo ║                                                   ║
echo ║   Для доступа с другого ПК используйте:          ║
echo ║   http://ВАШ_IP:5173                             ║
echo ╚══════════════════════════════════════════════════╝
echo.

REM === Open browser ===
timeout /t 2 /nobreak >nul
start http://localhost:5173

pause
