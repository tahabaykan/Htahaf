@echo off
echo ========================================
echo NODE.JS SORUN GIDERME
echo ========================================
echo.

cd /d %~dp0

echo [1] Node.js kontrol ediliyor...
echo.

REM Node.js'in yaygın konumlarını kontrol et
set NODE_FOUND=0

if exist "C:\Program Files\nodejs\node.exe" (
    echo [OK] Node.js bulundu: C:\Program Files\nodejs\node.exe
    "C:\Program Files\nodejs\node.exe" --version
    set NODE_FOUND=1
    set NODE_PATH=C:\Program Files\nodejs
)

if exist "C:\Program Files (x86)\nodejs\node.exe" (
    echo [OK] Node.js bulundu: C:\Program Files (x86)\nodejs\node.exe
    "C:\Program Files (x86)\nodejs\node.exe" --version
    set NODE_FOUND=1
    set NODE_PATH=C:\Program Files (x86)\nodejs
)

if %NODE_FOUND%==0 (
    echo [HATA] Node.js bulunamadi!
    echo.
    echo Cozum:
    echo 1. https://nodejs.org/ adresine git
    echo 2. LTS versiyonu indir
    echo 3. Kur (Add to PATH isaretle)
    echo 4. Bilgisayari yeniden baslat
    echo.
    pause
    exit /b 1
)

echo.
echo [2] PATH kontrolu...
echo.

REM PATH'te var mı kontrol et
echo %PATH% | findstr /i "nodejs" >nul
if %errorlevel%==0 (
    echo [OK] Node.js PATH'te var
) else (
    echo [UYARI] Node.js PATH'te yok!
    echo.
    echo PATH'e eklemek icin:
    echo 1. Windows tusu + R
    echo 2. sysdm.cpl yaz ve Enter
    echo 3. Advanced ^> Environment Variables
    echo 4. System variables ^> Path ^> Edit
    echo 5. New ^> %NODE_PATH% ekle
    echo 6. OK ^> OK ^> OK
    echo 7. Bilgisayari yeniden baslat
    echo.
)

echo.
echo [3] Test...
echo.

REM Node.js'i direkt yol ile test et
if defined NODE_PATH (
    echo Node.js versiyonu:
    "%NODE_PATH%\node.exe" --version
    echo.
    echo npm versiyonu:
    "%NODE_PATH%\npm.cmd" --version
    echo.
    echo [OK] Node.js calisiyor!
    echo.
    echo NOT: Eger 'node' komutu calismiyorsa, PowerShell'i YENIDEN BASLAT
    echo      veya bilgisayari yeniden baslat
)

echo.
pause









