@echo off
echo ========================================
echo JANALL WEB - BACKEND BASLATILIYOR
echo ========================================
echo.

cd /d %~dp0

echo Backend baslatiliyor...
echo Port: 5000
echo URL: http://127.0.0.1:5000
echo.
echo Durdurmak icin Ctrl+C basin
echo.

python app.py

pause









