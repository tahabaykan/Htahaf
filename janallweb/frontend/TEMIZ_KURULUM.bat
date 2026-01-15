@echo off
echo ========================================
echo TEMIZ KURULUM - Frontend
echo ========================================
echo.

cd /d %~dp0

set "NODE_PATH=C:\Program Files\nodejs"

REM PATH'e Node.js ekle
set "PATH=%NODE_PATH%;%PATH%"

echo [1] node_modules klasoru siliniyor...
if exist "node_modules" (
    rmdir /s /q "node_modules" 2>nul
    echo [OK] node_modules silindi
) else (
    echo [OK] node_modules zaten yok
)
echo.

echo [2] package-lock.json siliniyor...
if exist "package-lock.json" (
    del /q "package-lock.json" 2>nul
    echo [OK] package-lock.json silindi
)
echo.

echo [3] npm cache temizleniyor...
call "%NODE_PATH%\npm.cmd" cache clean --force
echo.

echo [4] npm install calistiriliyor...
echo Bu biraz surebilir...
echo.
call "%NODE_PATH%\npm.cmd" install
if errorlevel 1 (
    echo [HATA] npm install basarisiz!
    pause
    exit /b 1
)

echo.
echo [OK] npm install tamamlandi!
echo.

echo [5] npm run dev baslatiliyor...
echo Frontend: http://127.0.0.1:3000
echo.
call "%NODE_PATH%\npm.cmd" run dev

pause









