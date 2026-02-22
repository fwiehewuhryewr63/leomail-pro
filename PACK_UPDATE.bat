@echo off
chcp 65001 >nul
title LEOMAIL v3.0 — Pack Update
color 0e

set "ROOT=%~dp0"
set "PACK_DIR=%ROOT%_update_pack"
set "ZIP_OUT=%USERPROFILE%\Desktop\leomail_v3_update.zip"

echo.
echo  ════════════════════════════════════════
echo   LEOMAIL v3.0 — PACK UPDATE
echo  ════════════════════════════════════════
echo.
echo  ZIP будет: %ZIP_OUT%
echo.

:: Step 1: Build frontend
echo  [1/3] Собираю фронтенд...
cd /d "%ROOT%frontend"
call npm run build
if errorlevel 1 (
    echo  [ERROR] npm run build — ошибка!
    pause
    exit /b 1
)
echo        Build OK.
cd /d "%ROOT%"

:: Step 2: Create update pack folder
echo  [2/3] Пакую файлы...
if exist "%PACK_DIR%" rmdir /s /q "%PACK_DIR%"
mkdir "%PACK_DIR%"

:: Copy backend (without __pycache__)
xcopy "%ROOT%backend" "%PACK_DIR%\backend\" /E /I /Q >nul
for /d /r "%PACK_DIR%\backend" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d"
)

:: Copy frontend src + dist + configs
xcopy "%ROOT%frontend\src" "%PACK_DIR%\frontend\src\" /E /I /Q >nul
xcopy "%ROOT%frontend\dist" "%PACK_DIR%\frontend\dist\" /E /I /Q >nul
copy /y "%ROOT%frontend\package.json" "%PACK_DIR%\frontend\package.json" >nul
copy /y "%ROOT%frontend\vite.config.js" "%PACK_DIR%\frontend\vite.config.js" >nul
copy /y "%ROOT%frontend\index.html" "%PACK_DIR%\frontend\index.html" >nul

:: Copy START.bat и requirements.txt
copy /y "%ROOT%START.bat" "%PACK_DIR%\START.bat" >nul
copy /y "%ROOT%requirements.txt" "%PACK_DIR%\requirements.txt" >nul

:: Step 3: Create ZIP on Desktop
echo  [3/3] Создаю ZIP на Desktop...
if exist "%ZIP_OUT%" del "%ZIP_OUT%"
powershell -Command "Compress-Archive -Path '%PACK_DIR%\*' -DestinationPath '%ZIP_OUT%' -Force"

:: Cleanup temp folder
rmdir /s /q "%PACK_DIR%"

echo.
echo  ════════════════════════════════════════
echo   ГОТОВО!
echo  ════════════════════════════════════════
echo.
echo  ZIP на Desktop: leomail_v3_update.zip
echo.
echo  Что делать:
echo   1. Скопируй ZIP на VPS
echo   2. Распакуй в любую папку
echo   3. Перенеси папку user_data из старой версии
echo   4. pip install -r requirements.txt
echo   5. Запусти START.bat
echo.
pause
