@echo off
echo njanall API Server arka planda baslatiliyor...
cd /d "%~dp0"
start "njanall API Server" python start_api.py
echo Server baslatildi! Terminal penceresini kapatabilirsiniz.
timeout /t 3












