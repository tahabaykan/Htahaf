@echo off
echo ========================================
echo FRONTEND BASLATMA v2 (DUZELTILMIS)
echo ========================================
echo.

REM Mevcut dizini al
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%frontend"

REM Node.js'i bul
set "NODE_PATH="

if exist "C:\Program Files\nodejs\node.exe" (
    set "NODE_PATH=C:\Program Files\nodejs"
    goto :found
)

if exist "C:\Program Files (x86)\nodejs\node.exe" (
    set "NODE_PATH=C:\Program Files (x86)\nodejs"
    goto :found
)

echo [HATA] Node.js bulunamadi!
pause
exit /b 1

:found
echo [OK] Node.js bulundu: %NODE_PATH%
echo.

REM PATH'e ekle
set "PATH=%PATH%;%NODE_PATH%"

REM Test
echo Node.js versiyonu:
"%NODE_PATH%\node.exe" --version
echo.

echo npm versiyonu:
"%NODE_PATH%\npm.cmd" --version
echo.

REM Frontend dizinine git
if not exist "frontend" (
    echo [HATA] frontend klasoru bulunamadi!
    pause
    exit /b 1
)

cd /d "%SCRIPT_DIR%frontend"

echo [1] npm install calistiriliyor...
echo Bu biraz surebilir (ilk kez calistiriyorsan)...
echo.
call "%NODE_PATH%\npm.cmd" install
if %errorlevel% neq 0 (
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

