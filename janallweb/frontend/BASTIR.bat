@echo off
echo ========================================
echo FRONTEND BASLATMA (FRONTEND KLASORUNDEN)
echo ========================================
echo.

REM Bu dosya frontend klasorunde, direkt calistir
cd /d %~dp0

set "NODE_PATH=C:\Program Files\nodejs"

echo [OK] Node.js: %NODE_PATH%
echo.

echo Node.js: 
"%NODE_PATH%\node.exe" --version
echo.

echo npm:
"%NODE_PATH%\npm.cmd" --version
echo.

if not exist "node_modules" (
    echo [1] npm install calistiriliyor...
    echo Bu biraz surebilir...
    echo.
    call "%NODE_PATH%\npm.cmd" install
    if errorlevel 1 (
        echo [HATA] npm install basarisiz!
        pause
        exit /b 1
    )
    echo [OK] npm install tamamlandi!
    echo.
) else (
    echo [OK] node_modules zaten var, npm install atlaniyor...
    echo.
)

echo [2] npm run dev baslatiliyor...
echo Frontend: http://127.0.0.1:3000
echo.
call "%NODE_PATH%\npm.cmd" run dev

pause









