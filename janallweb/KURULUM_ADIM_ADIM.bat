@echo off
echo ========================================
echo JANALL WEB - TAM KURULUM
echo ========================================
echo.

echo [1/4] Node.js kontrol ediliyor...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Node.js yuklu degil!
    echo.
    echo Node.js yuklemek icin:
    echo 1. https://nodejs.org/ adresine git
    echo 2. LTS versiyonu indir
    echo 3. Kur ve PowerShell'i yeniden baslat
    echo.
    pause
    exit /b 1
) else (
    echo [OK] Node.js yuklu
    node --version
)

echo.
echo [2/4] Python kontrol ediliyor...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Python yuklu degil!
    pause
    exit /b 1
) else (
    echo [OK] Python yuklu
    python --version
)

echo.
echo [3/4] Python bagimliliklari yukleniyor...
cd /d %~dp0
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [HATA] Python bagimliliklari yuklenemedi!
    pause
    exit /b 1
) else (
    echo [OK] Python bagimliliklari yuklendi
)

echo.
echo [4/4] Frontend bagimliliklari yukleniyor...
cd frontend
if not exist node_modules (
    echo npm install calistiriliyor...
    call npm install
    if %errorlevel% neq 0 (
        echo [HATA] Frontend bagimliliklari yuklenemedi!
        pause
        exit /b 1
    )
) else (
    echo [OK] Frontend bagimliliklari zaten yuklu
)

echo.
echo ========================================
echo KURULUM TAMAMLANDI!
echo ========================================
echo.
echo Simdi baslatmak icin:
echo.
echo Terminal 1 (Backend):
echo   cd janallweb
echo   python app.py
echo.
echo Terminal 2 (Frontend):
echo   cd janallweb\frontend
echo   npm run dev
echo.
pause









