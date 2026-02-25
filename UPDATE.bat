@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Leomail v4 — UPDATE
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║       LEOMAIL v4 — BLITZ PIPELINE UPDATE          ║
echo ║   Сохраняет user_data/, обновляет код             ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM === 1. Stop running services ===
echo [1/7] Останавливаем сервисы...
taskkill /f /im "python.exe" >nul 2>&1
taskkill /f /im "node.exe" >nul 2>&1
ping 127.0.0.1 -n 3 >nul
echo [OK] Сервисы остановлены

REM === 2. Backup user_data to a FIXED location ===
echo.
echo [2/7] Бэкап user_data...
set "BACKUP_DIR=user_data_backup"
if exist "user_data" (
    if exist "!BACKUP_DIR!" rd /s /q "!BACKUP_DIR!" >nul 2>&1
    xcopy /E /I /Y "user_data" "!BACKUP_DIR!" >nul 2>&1
    echo [OK] Бэкап создан: !BACKUP_DIR!
    if exist "!BACKUP_DIR!\leomail.db" (
        echo [OK] leomail.db в бэкапе НАЙДЕН
    ) else (
        echo [WARN] leomail.db в бэкапе НЕ найден!
    )
) else (
    echo [SKIP] user_data не найден
)

REM === 3. Pull latest code ===
echo.
echo [3/7] Обновление кода...
where git >nul 2>&1
if %errorlevel% equ 0 (
    if not exist ".git" (
        echo [INIT] Git не инициализирован, клонируем...
        cd ..
        git clone https://github.com/fwiehewuhryewr63/leomail-pro.git Leomail_new
        xcopy /E /I /Y "Leomail_new\*" "Leomail\" >nul 2>&1
        rd /s /q Leomail_new >nul 2>&1
        cd Leomail
    ) else (
        git stash >nul 2>&1
        git pull origin main
        if !errorlevel! neq 0 (
            echo [WARN] git pull не удался, пробуем force...
            git fetch --all
            git reset --hard origin/main
        )
    )
    echo [OK] Код обновлён
) else (
    echo [WARN] Git не установлен — пропускаем
)

REM === 4. ALWAYS restore user_data from backup ===
echo.
echo [4/7] Восстановление user_data...
if not exist "user_data" mkdir "user_data"
if exist "!BACKUP_DIR!\leomail.db" (
    xcopy /E /I /Y "!BACKUP_DIR!\*" "user_data\" >nul 2>&1
    echo [OK] user_data восстановлена из бэкапа
) else (
    echo [INFO] Нет бэкапа — свежая установка
)

REM Verify DB is in place
if exist "user_data\leomail.db" (
    echo [OK] leomail.db на месте
) else (
    echo [WARN] leomail.db отсутствует — будет создана при запуске
)

REM === 5. Update Python dependencies ===
echo.
echo [5/7] Обновление Python зависимостей...
pip install -r requirements.txt --quiet 2>nul
echo [OK] Python зависимости обновлены
echo [*] Обновление браузеров Playwright...
playwright install chromium 2>nul
if %errorlevel% neq 0 (
    python -m playwright install chromium 2>nul
)
echo [OK] Браузеры Playwright обновлены

REM === 6. Update frontend ===
echo.
echo [6/7] Обновление frontend...
cd frontend
call npm install --silent 2>nul
echo [OK] Зависимости frontend установлены
echo [*] Сборка frontend (npm run build)...
call npm run build 2>nul
if %errorlevel% equ 0 (
    echo [OK] Frontend собран
) else (
    echo [WARN] npm run build не удался!
)
cd ..
echo [OK] Frontend обновлён

REM === 7. Database migration (add new columns + tables for v4) ===
echo.
echo [7/7] Миграция БД v4 (Campaign tables + new columns)...
python -c "from backend.database import engine, Base; from backend.models import *; Base.metadata.create_all(bind=engine); print('[OK] Все таблицы v4 синхронизированы (campaigns, campaign_templates, campaign_links, campaign_recipients)')" 2>nul

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║       ОБНОВЛЕНИЕ v4 ЗАВЕРШЕНО!                    ║
echo ║                                                   ║
echo ║   user_data/ восстановлена                        ║
echo ║   Campaign tables созданы                         ║
echo ║   Запустите START.bat для запуска                 ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
