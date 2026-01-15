@echo off
echo ========================================
echo FRONTEND BASLATMA (NODE.JS PATH EKLEME)
echo ========================================
echo.

cd /d %~dp0frontend

REM Node.js'i bul ve PATH'e ekle
set NODE_PATH=

if exist "C:\Program Files\nodejs\node.exe" (
    set "NODE_PATH=C:\Program Files\nodejs"
)

if exist "C:\Program Files (x86)\nodejs\node.exe" (
    set "NODE_PATH=C:\Program Files (x86)\nodejs"
)

if not defined NODE_PATH (
    echo [HATA] Node.js bulunamadi!
    echo.
    echo Node.js yuklemek icin:
    echo 1. https://nodejs.org/ adresine git
    echo 2. LTS versiyonu indir
    echo 3. Kur (Add to PATH isaretle)
    echo 4. Bilgisayari yeniden baslat
    echo.
    pause
    exit /b 1
)

echo [OK] Node.js bulundu: %NODE_PATH%
echo.

REM PATH'e ekle (gecici) - tırnak içinde
set "PATH=%PATH%;%NODE_PATH%"

echo Node.js versiyonu:
"%NODE_PATH%\node.exe" --version
echo.

echo npm versiyonu:
"%NODE_PATH%\npm.cmd" --version
echo.

echo [1] npm install calistiriliyor...
echo.
call "%NODE_PATH%\npm.cmd" install

if %errorlevel% neq 0 (
    echo [HATA] npm install basarisiz!
    pause
    exit /b 1
)

echo.
echo [2] npm run dev baslatiliyor...
echo.
call "%NODE_PATH%\npm.cmd" run dev

pause

