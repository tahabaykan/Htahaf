@echo off
echo ========================================
echo FRONTEND BASLATMA (SON VERSIYON)
echo ========================================
echo.

REM Script'in bulunduğu dizin
set "SCRIPT_DIR=%~dp0"
set "FRONTEND_DIR=%SCRIPT_DIR%frontend"

REM Frontend klasörüne git
cd /d "%FRONTEND_DIR%"

if not exist "%FRONTEND_DIR%" (
    echo [HATA] frontend klasoru bulunamadi: %FRONTEND_DIR%
    pause
    exit /b 1
)

echo [OK] Frontend dizini: %FRONTEND_DIR%
echo.

set "NODE_PATH=C:\Program Files\nodejs"

echo [OK] Node.js: %NODE_PATH%
echo.

echo Node.js versiyonu:
"%NODE_PATH%\node.exe" --version
if errorlevel 1 (
    echo [HATA] Node.js calistirilamadi!
    pause
    exit /b 1
)
echo.

echo npm versiyonu:
"%NODE_PATH%\npm.cmd" --version
if errorlevel 1 (
    echo [HATA] npm calistirilamadi!
    pause
    exit /b 1
)
echo.

echo [1] npm install calistiriliyor...
echo Bu biraz surebilir (ilk kez calistiriyorsan)...
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

echo [2] npm run dev baslatiliyor...
echo Frontend: http://127.0.0.1:3000
echo Durdurmak icin Ctrl+C basin
echo.
call "%NODE_PATH%\npm.cmd" run dev

pause

