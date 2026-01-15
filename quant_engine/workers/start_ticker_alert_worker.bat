@echo off
REM Ticker Alert Worker - Windows Script

echo ========================================
echo Ticker Alert Worker Starting...
echo ========================================
echo.
echo This worker runs in a SEPARATE process.
echo FastAPI will NOT be blocked.
echo.
echo Press Ctrl+C to stop the worker.
echo.

cd /d "%~dp0\.."
python workers\run_ticker_alert_worker.py

pause


