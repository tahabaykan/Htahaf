@echo off
REM Batch script to start live trading engine
REM Usage: start_live.bat [--no-trading|--test-order]

echo.
echo ========================================
echo  Live Trading Engine Starter
echo ========================================
echo.

REM Check if .env exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Please create .env file with HAMMER_PASSWORD
    pause
    exit /b 1
)

REM Default mode
set MODE=%1
if "%MODE%"=="" set MODE=--no-trading

if "%MODE%"=="--no-trading" (
    echo Mode: Data subscribe only (no orders)
    python main.py live --execution-broker HAMMER --no-trading
) else if "%MODE%"=="--test-order" (
    echo Mode: Test order (dry-run)
    python main.py live --execution-broker HAMMER --test-order
) else (
    echo Mode: LIVE TRADING (orders enabled)
    echo WARNING: Real orders will be sent!
    pause
    python main.py live --execution-broker HAMMER
)

pause








