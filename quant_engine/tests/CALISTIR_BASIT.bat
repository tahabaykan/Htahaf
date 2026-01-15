@echo off
chcp 65001 >nul
cd /d "%~dp0.."
python -m tests.karbotu_validation_runner
pause






