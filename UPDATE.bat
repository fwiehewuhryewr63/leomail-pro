@echo off
chcp 65001 >nul
title Leomail — UPDATE
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║          LEOMAIL v3 — ОБНОВЛЕНИЕ                  ║
echo ║   Сохраняет user_data/, обновляет код             ║
echo ╚══════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM === 1. Stop running services ===
echo [1/6] Останавливаем сервисы...
taskkill /f /im "python.exe" >nul 2>&1
taskkill /f /im "node.exe" >nul 2>&1
timeout /t 2 /nobreak >nul
echo [OK] Сервисы остановлены

REM === 2. Backup user_data ===
echo.
echo [2/6] Бэкап user_data...
if exist "user_data" (
    set "BACKUP_DIR=user_data_backup_%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%"
    set "BACKUP_DIR=%BACKUP_DIR: =0%"
    xcopy /E /I /Y "user_data" "%BACKUP_DIR%" >nul 2>&1
    echo [OK] Бэкап: %BACKUP_DIR%
) else (
    echo [SKIP] user_data не найден
)

REM === 3. Pull latest code ===
echo.
echo [3/6] Обновление кода...
where git >nul 2>&1
if %errorlevel% equ 0 (
    git stash >nul 2>&1
    git pull origin main
    if %errorlevel% neq 0 (
        echo [WARN] git pull не удался, пробуем force...
        git fetch --all
        git reset --hard origin/main
    )
    echo [OK] Код обновлён
) else (
    echo [WARN] Git не установлен — пропускаем git pull
    echo        Скопируйте обновлённые файлы вручную
)

REM === 4. Update Python dependencies ===
echo.
echo [4/6] Обновление Python зависимостей...
pip install -r requirements.txt --quiet
echo [OK] Python зависимости обновлены

REM === 5. Update and build frontend ===
echo.
echo [5/6] Обновление frontend...
cd frontend
call npm install --silent
call npm run build
cd ..
echo [OK] Frontend пересобран

REM === 6. Restore user_data (safety check) ===
echo.
echo [6/6] Проверка user_data...
if exist "user_data\leomail.db" (
    echo [OK] user_data на месте (%~dp0user_data\leomail.db)
) else (
    echo [WARN] БД не найдена! Восстанавливаем из бэкапа...
    if defined BACKUP_DIR (
        xcopy /E /I /Y "%BACKUP_DIR%" "user_data" >nul 2>&1
        echo [OK] Восстановлено из бэкапа
    )
)

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║          ОБНОВЛЕНИЕ ЗАВЕРШЕНО!                    ║
echo ║                                                   ║
echo ║   user_data/ сохранена                            ║
echo ║   Запустите START.bat для запуска                 ║
echo ╚══════════════════════════════════════════════════╝
echo.
pause
