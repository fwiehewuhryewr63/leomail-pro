@echo off
title Leomail Remote Updater
color 0b

echo.
echo ========================================
echo   LEOMAIL v3.0 - REMOTE UPDATE TOOL
echo ========================================
echo.

set /p UPDATE_URL="Enter direct URL to the update ZIP (or press Enter to use default): "

if "%UPDATE_URL%"=="" (
    python remote_updater.py
) else (
    python remote_updater.py "%UPDATE_URL%"
)

echo.
pause
