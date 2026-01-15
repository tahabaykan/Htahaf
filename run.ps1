# Quant Engine - Single Command Starter
# Starts both backend and frontend in separate windows

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Quant Engine - Starting Services" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory (repo root)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = $scriptDir
$frontendDir = Join-Path $scriptDir "quant_engine\frontend"

Write-Host "Backend directory: $backendDir\quant_engine" -ForegroundColor Yellow
Write-Host "Frontend directory: $frontendDir" -ForegroundColor Yellow
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python not found!" -ForegroundColor Red
    Write-Host "Please install Python and add it to PATH" -ForegroundColor Yellow
    exit 1
}

# Check Node.js
Write-Host "Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version 2>&1
    Write-Host "Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Node.js not found!" -ForegroundColor Red
    Write-Host "Please install Node.js and add it to PATH" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Start Backend
Write-Host "Starting Backend (new window)..." -ForegroundColor Green
$backendCmd = "cd /d `"$backendDir\quant_engine`" && python main.py api"
Start-Process cmd -ArgumentList "/k", $backendCmd -WindowStyle Normal

# Wait a bit
Start-Sleep -Seconds 3

# Start Frontend
Write-Host "Starting Frontend (new window)..." -ForegroundColor Green
$frontendCmd = "cd /d `"$frontendDir`" && npm run dev"
Start-Process cmd -ArgumentList "/k", $frontendCmd -WindowStyle Normal

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Services Started!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backend API:  http://localhost:8000" -ForegroundColor Cyan
Write-Host "Backend Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Health Check: http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "Status:       http://localhost:8000/api/status" -ForegroundColor Cyan
Write-Host ""
Write-Host "Frontend UI:  http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop services, close the terminal windows or press Ctrl+C" -ForegroundColor Yellow
Write-Host ""
Write-Host "This window can be closed." -ForegroundColor Gray








