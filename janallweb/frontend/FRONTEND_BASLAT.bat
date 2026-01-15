@echo off
echo ========================================
echo FRONTEND BASLATILIYOR
echo ========================================
echo.

cd /d %~dp0

REM Node.js'i PATH'e ekle (başa ekle ki öncelikli olsun)
set "PATH=C:\Program Files\nodejs;%PATH%"

echo Node.js PATH'e eklendi
echo.

echo npm run dev baslatiliyor...
echo.

REM npm.cmd'i direkt çağır (PowerShell execution policy sorununu önler)
call "C:\Program Files\nodejs\npm.cmd" run dev

pause

