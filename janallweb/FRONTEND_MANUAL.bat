@echo off
echo ========================================
echo FRONTEND MANUEL BASLATMA
echo ========================================
echo.

cd /d %~dp0frontend

REM Node.js yolu
set "NODE_PATH=C:\Program Files\nodejs"

echo Node.js: %NODE_PATH%\node.exe
echo.

echo [1] npm install...
"%NODE_PATH%\npm.cmd" install

echo.
echo [2] npm run dev...
echo Frontend: http://127.0.0.1:3000
echo.
"%NODE_PATH%\npm.cmd" run dev

pause









