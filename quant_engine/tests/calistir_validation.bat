@echo off
REM KARBOTU Validation Runner - Windows Batch Script

echo ================================================================================
echo KARBOTU v1 VALIDATION RUNNER
echo ================================================================================
echo.

REM Quant_Engine dizinine git
cd /d "%~dp0.."

REM Python path'i ayarla
set PYTHONPATH=%CD%

REM Validation'ı çalıştır
python -m tests.karbotu_validation_runner

REM Hata kontrolü
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ================================================================================
    echo ERROR: Validation failed with exit code %ERRORLEVEL%
    echo ================================================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ================================================================================
echo Validation complete! Check karbotu_validation_report.txt for details.
echo ================================================================================
pause






