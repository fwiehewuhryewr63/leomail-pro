@echo off
chcp 65001 >nul
title LEOMAIL v4.1 — Build EXE
color 0e

set "ROOT=%~dp0"

echo.
echo  ════════════════════════════════════════
echo   LEOMAIL v4.1 — BUILD NATIVE EXE
echo   PyInstaller + pywebview = native app
echo  ════════════════════════════════════════
echo.

:: Step 1: Install build dependencies
echo  [1/4] Установка зависимостей для сборки...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo  [ERROR] Не удалось установить pyinstaller!
    pause
    exit /b 1
)
echo        pyinstaller OK.

:: Step 2: Build frontend
echo  [2/4] Сборка фронтенда...
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    call npm install --silent
)
call npm run build
if errorlevel 1 (
    echo  [ERROR] npm run build — ошибка!
    pause
    exit /b 1
)
echo        Frontend build OK.
cd /d "%ROOT%"

:: Step 3: Build EXE with PyInstaller
echo  [3/4] Сборка EXE через PyInstaller...
python -m PyInstaller --clean --noconfirm Leomail.spec
if errorlevel 1 (
    echo  [ERROR] PyInstaller — ошибка!
    echo  Проверьте логи выше.
    pause
    exit /b 1
)
echo        PyInstaller build OK.

:: Step 4: Copy user_data template
echo  [4/4] Подготовка дистрибутива...
if not exist "dist\Leomail\user_data" mkdir "dist\Leomail\user_data"
if not exist "dist\Leomail\user_data\sessions" mkdir "dist\Leomail\user_data\sessions"
if not exist "dist\Leomail\user_data\logs" mkdir "dist\Leomail\user_data\logs"
if not exist "dist\Leomail\user_data\exports" mkdir "dist\Leomail\user_data\exports"
copy /y "%ROOT%version.json" "dist\Leomail\version.json" >nul 2>&1

echo.
echo  ════════════════════════════════════════
echo   BUILD COMPLETE!
echo  ════════════════════════════════════════
echo.
echo   EXE: dist\Leomail\Leomail.exe
echo.
echo   EXE SHA-256:
certutil -hashfile "dist\Leomail\Leomail.exe" SHA256 2>nul | findstr /v "hash CertUtil"
echo.
echo   NOTE: For GitHub Release, hash the ZIP (not EXE):
echo     certutil -hashfile Leomail-vX.X.XX.zip SHA256
echo   Then paste into release notes as: sha256: ^<hash^>
echo.
echo   Что в папке dist\Leomail\:
echo     Leomail.exe      — основной файл
echo     backend\          — серверная логика
echo     frontend\dist\    — UI
echo     user_data\        — данные (БД, сессии)
echo     version.json      — версия
echo.
echo   Для деплоя на VPS:
echo     1. Скопируйте папку dist\Leomail\ на VPS
echo     2. Запустите Leomail.exe
echo     3. Готово!
echo.
pause
