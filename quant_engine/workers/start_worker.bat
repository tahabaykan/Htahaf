@echo off
REM Deeper Analysis Worker - Windows Script

echo ========================================
echo Deeper Analysis Worker Starting...
echo ========================================
echo.
echo This worker runs in a SEPARATE process.
echo FastAPI will NOT be blocked.
echo.
echo Press Ctrl+C to stop the worker.
echo.

cd /d "%~dp0\.."
python workers\run_deeper_worker.py

pause


