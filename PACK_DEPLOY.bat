@echo off
chcp 65001 >nul
echo ==========================================
echo   LEOMAIL — PACKING FOR VPS
echo ==========================================
echo.

set "SRC=c:\Users\admin\.gemini\antigravity\playground\Leomail"
set "OUT=%USERPROFILE%\Desktop\Leomail_v3_deploy.zip"

:: Delete old zip if exists
if exist "%OUT%" del "%OUT%"

:: Use PowerShell to create zip with only needed files
powershell -NoProfile -Command ^
 "$src='%SRC%';" ^
 "$out='%OUT%';" ^
 "$tmp=Join-Path $env:TEMP 'leomail_pack';" ^
 "if(Test-Path $tmp){Remove-Item $tmp -Recurse -Force};" ^
 "New-Item $tmp -ItemType Directory | Out-Null;" ^
 "Copy-Item \"$src\backend\" \"$tmp\backend\" -Recurse -Exclude '__pycache__','*.pyc';" ^
 "Get-ChildItem \"$tmp\backend\" -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue;" ^
 "if(Test-Path \"$src\frontend\dist\"){Copy-Item \"$src\frontend\dist\" \"$tmp\frontend\dist\" -Recurse};" ^
 "foreach($f in @('START.bat','SETUP.bat','UPDATE.bat','requirements.txt','.env','LEOMAIL_TEMPLATE_FORMAT.txt')){" ^
 "  $p=Join-Path $src $f; if(Test-Path $p){Copy-Item $p $tmp}};" ^
 "Compress-Archive -Path \"$tmp\*\" -DestinationPath $out -Force;" ^
 "Remove-Item $tmp -Recurse -Force;" ^
 "$sz=(Get-Item $out).Length/1MB;" ^
 "Write-Host \"`nDone! Size: $([math]::Round($sz,1)) MB`nSaved: $out\""

echo.
echo ==========================================
echo   ZIP is on your Desktop!
echo ==========================================
pause
