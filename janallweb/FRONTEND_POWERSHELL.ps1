# Frontend Başlatma - PowerShell Script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "FRONTEND BASLATMA" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Node.js yolu
$NODE_PATH = "C:\Program Files\nodejs"

# Frontend dizinine git
$FRONTEND_DIR = Join-Path $PSScriptRoot "frontend"
Set-Location $FRONTEND_DIR

Write-Host "[OK] Frontend dizini: $FRONTEND_DIR" -ForegroundColor Green
Write-Host ""

# Node.js kontrolü
$NODE_EXE = Join-Path $NODE_PATH "node.exe"
$NPM_EXE = Join-Path $NODE_PATH "npm.cmd"

if (-not (Test-Path $NODE_EXE)) {
    Write-Host "[HATA] Node.js bulunamadi: $NODE_EXE" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "Node.js versiyonu:" -ForegroundColor Yellow
& $NODE_EXE --version
Write-Host ""

Write-Host "npm versiyonu:" -ForegroundColor Yellow
& $NPM_EXE --version
Write-Host ""

# npm install
Write-Host "[1] npm install calistiriliyor..." -ForegroundColor Yellow
Write-Host "Bu biraz surebilir (ilk kez calistiriyorsan)..." -ForegroundColor Gray
Write-Host ""

& $NPM_EXE install

if ($LASTEXITCODE -ne 0) {
    Write-Host "[HATA] npm install basarisiz!" -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "[OK] npm install tamamlandi!" -ForegroundColor Green
Write-Host ""

# npm run dev
Write-Host "[2] npm run dev baslatiliyor..." -ForegroundColor Yellow
Write-Host "Frontend: http://127.0.0.1:3000" -ForegroundColor Cyan
Write-Host "Durdurmak icin Ctrl+C basin" -ForegroundColor Gray
Write-Host ""

& $NPM_EXE run dev









