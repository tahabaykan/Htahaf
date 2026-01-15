@echo off
echo ========================================
echo JANALL WEB - BACKEND VE FRONTEND BASLATILIYOR
echo ========================================
echo.

REM Script'in bulunduğu dizine git
cd /d %~dp0

echo [1/2] Backend (Flask) baslatiliyor...
start "JanAll Web - Backend" cmd /k "cd /d %~dp0 && python app.py"
timeout /t 2 /nobreak >nul

echo [2/2] Frontend (React) baslatiliyor...
REM Node.js'i PATH'e ekle ve frontend'i baslat
start "JanAll Web - Frontend" cmd /k "cd /d %~dp0frontend && set "PATH=%PATH%;C:\Program Files\nodejs" && "C:\Program Files\nodejs\npm.cmd" run dev"

echo.
echo ========================================
echo HER IKI SERVER DE BASLATILDI!
echo ========================================
echo.
echo Backend: http://127.0.0.1:5000
echo Frontend: http://localhost:3000
echo.
echo Iki ayri pencere acildi:
echo - Backend penceresi: Flask server loglari
echo - Frontend penceresi: React dev server loglari
echo.
echo Kapatmak icin her iki pencereyi de kapatin.
echo.
pause

