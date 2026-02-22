@echo off
chcp 65001 >nul
title Leomail — START
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║           LEOMAIL v3 — ЗАПУСК                     ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM === Kill old processes ===
echo [1/3] Останавливаем старые процессы...
taskkill /f /im "python.exe" >nul 2>&1
timeout /t 1 /nobreak >nul

REM === Start Backend ===
echo [2/3] Запуск Backend (порт 8000)...
start "Leomail Backend" cmd /k "cd /d "%~dp0" && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

REM === Start Frontend (dev mode or serve build) ===
echo [3/3] Запуск Frontend (порт 5173)...
if exist "frontend\dist\index.html" (
    REM Production build exists — serve it
    start "Leomail Frontend" cmd /k "cd /d "%~dp0\frontend" && npx -y serve dist -l 5173 --cors"
) else (
    REM Dev mode
    start "Leomail Frontend" cmd /k "cd /d "%~dp0\frontend" && npm run dev -- --host 0.0.0.0"
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
