@echo off
echo ========================================
echo NODE.JS ARAMA
echo ========================================
echo.

echo [1] Yaygin konumlar kontrol ediliyor...
echo.

set FOUND=0

REM Program Files
if exist "C:\Program Files\nodejs\node.exe" (
    echo [BULUNDU] C:\Program Files\nodejs\node.exe
    "C:\Program Files\nodejs\node.exe" --version
    set FOUND=1
)

REM Program Files (x86)
if exist "C:\Program Files (x86)\nodejs\node.exe" (
    echo [BULUNDU] C:\Program Files (x86)\nodejs\node.exe
    "C:\Program Files (x86)\nodejs\node.exe" --version
    set FOUND=1
)

REM AppData Local
if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" (
    echo [BULUNDU] %LOCALAPPDATA%\Programs\nodejs\node.exe
    "%LOCALAPPDATA%\Programs\nodejs\node.exe" --version
    set FOUND=1
)

REM AppData Roaming
if exist "%APPDATA%\npm\node.exe" (
    echo [BULUNDU] %APPDATA%\npm\node.exe
    "%APPDATA%\npm\node.exe" --version
    set FOUND=1
)

echo.
if %FOUND%==0 (
    echo [HATA] Node.js hicbir yerde bulunamadi!
    echo.
    echo Node.js yuklu degil!
    echo.
    echo YUKLEME:
    echo 1. https://nodejs.org/ adresine git
    echo 2. LTS versiyonu indir (v20.x.x veya uzeri)
    echo 3. .msi dosyasini calistir
    echo 4. Kurulum sirasinda "Add to PATH" isaretle
    echo 5. Kurulum bitince BILGISAYARI YENIDEN BASLAT
    echo 6. Tekrar dene
) else (
    echo [OK] Node.js bulundu!
    echo.
    echo NOT: Eger 'node' komutu calismiyorsa:
    echo - PowerShell'i YENIDEN BASLAT
    echo - Veya bilgisayari YENIDEN BASLAT
)

echo.
pause









