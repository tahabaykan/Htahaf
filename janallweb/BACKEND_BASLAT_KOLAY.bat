@echo off
echo ========================================
echo BACKEND BASLATMA (FLASK)
echo ========================================
echo.

cd /d %~dp0

echo [OK] Backend baslatiliyor...
echo Backend: http://127.0.0.1:5000
echo Durdurmak icin Ctrl+C basin
echo.

python app.py

pause









