@echo off
echo ========================================
echo BACKEND TEST
echo ========================================
echo.

cd /d %~dp0

echo [1] Python import testi...
python -c "from app import app; print('   OK - App import edildi')" 2>nul
if %errorlevel% neq 0 (
    echo [HATA] App import edilemedi!
    pause
    exit /b 1
)

echo.
echo [2] Backend baslatiliyor...
echo     Port: 5000
echo     URL: http://127.0.0.1:5000
echo.
echo     Durdurmak icin Ctrl+C basin
echo.
echo ========================================
echo.

python app.py

pause









