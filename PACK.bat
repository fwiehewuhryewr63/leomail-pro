@echo off
chcp 65001 >nul
title LEOMAIL v3.0 — Create Deploy Package
color 0e

set "ROOT=%~dp0"
set "PACK=leomail_v3.0"
set "PACK_DIR=%ROOT%_pack_temp"
set "ZIP=%ROOT%%PACK%.zip"

echo.
echo  ════════════════════════════════════════
echo   LEOMAIL v3.0 — CREATE DEPLOY PACKAGE
echo  ════════════════════════════════════════
echo.

:: Build frontend
echo  [1/3] Building frontend...
cd /d "%ROOT%frontend"
call npm run build
if errorlevel 1 (
    echo  [ERROR] Build failed!
    pause
    exit /b 1
)
cd /d "%ROOT%"
echo        Build OK.

:: Create temp folder
echo  [2/3] Packing files...
if exist "%PACK_DIR%" rmdir /s /q "%PACK_DIR%"
mkdir "%PACK_DIR%\%PACK%"

:: Copy everything needed
xcopy "%ROOT%backend" "%PACK_DIR%\%PACK%\backend\" /E /I /Q >nul
xcopy "%ROOT%frontend\src" "%PACK_DIR%\%PACK%\frontend\src\" /E /I /Q >nul
xcopy "%ROOT%frontend\dist" "%PACK_DIR%\%PACK%\frontend\dist\" /E /I /Q >nul
xcopy "%ROOT%frontend\public" "%PACK_DIR%\%PACK%\frontend\public\" /E /I /Q >nul 2>&1
copy /y "%ROOT%frontend\package.json" "%PACK_DIR%\%PACK%\frontend\package.json" >nul
copy /y "%ROOT%frontend\vite.config.js" "%PACK_DIR%\%PACK%\frontend\vite.config.js" >nul
copy /y "%ROOT%frontend\index.html" "%PACK_DIR%\%PACK%\frontend\index.html" >nul
copy /y "%ROOT%frontend\.eslintrc.cjs" "%PACK_DIR%\%PACK%\frontend\.eslintrc.cjs" >nul 2>&1

copy /y "%ROOT%requirements.txt" "%PACK_DIR%\%PACK%\requirements.txt" >nul
copy /y "%ROOT%START.bat" "%PACK_DIR%\%PACK%\START.bat" >nul
copy /y "%ROOT%INSTALL.bat" "%PACK_DIR%\%PACK%\INSTALL.bat" >nul
copy /y "%ROOT%DEPLOY.bat" "%PACK_DIR%\%PACK%\DEPLOY.bat" >nul

:: Remove __pycache__
for /d /r "%PACK_DIR%" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

:: Create ZIP
echo  [3/3] Creating ZIP...
if exist "%ZIP%" del /f "%ZIP%"
powershell -Command "Compress-Archive -Path '%PACK_DIR%\%PACK%' -DestinationPath '%ZIP%' -Force"

:: Cleanup
rmdir /s /q "%PACK_DIR%"

echo.
echo  ════════════════════════════════════════
echo   DONE!
echo  ════════════════════════════════════════
echo.
echo  Package: %ZIP%
echo.
echo  ┌─────────────────────────────────────┐
echo  │  КАК ИСПОЛЬЗОВАТЬ:                  │
echo  │                                     │
echo  │  1. Скопируй %PACK%.zip на VPS      │
echo  │  2. Распакуй на Desktop             │
echo  │  3. Открой папку %PACK%             │
echo  │  4. Запусти DEPLOY.bat              │
echo  │  5. Запусти START.bat               │
echo  │                                     │
echo  │  Данные сохраняются автоматически!   │
echo  └─────────────────────────────────────┘
echo.
pause
