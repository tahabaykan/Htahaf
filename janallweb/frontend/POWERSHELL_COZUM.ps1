# Frontend Temiz Kurulum - PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TEMIZ KURULUM - Frontend" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Node.js yolu
$NODE_PATH = "C:\Program Files\nodejs"
$NODE_EXE = Join-Path $NODE_PATH "node.exe"
$NPM_EXE = Join-Path $NODE_PATH "npm.cmd"

# PATH'e Node.js ekle
$env:PATH = "$NODE_PATH;$env:PATH"

# Frontend dizinine git
Set-Location $PSScriptRoot

Write-Host "[1] node_modules klasoru siliniyor..." -ForegroundColor Yellow
if (Test-Path "node_modules") {
    Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
    Write-Host "[OK] node_modules silindi" -ForegroundColor Green
} else {
    Write-Host "[OK] node_modules zaten yok" -ForegroundColor Gray
}
Write-Host ""

Write-Host "[2] package-lock.json siliniyor..." -ForegroundColor Yellow
if (Test-Path "package-lock.json") {
    Remove-Item -Force "package-lock.json" -ErrorAction SilentlyContinue
    Write-Host "[OK] package-lock.json silindi" -ForegroundColor Green
}
Write-Host ""

Write-Host "[3] npm cache temizleniyor..." -ForegroundColor Yellow
& $NPM_EXE cache clean --force
Write-Host ""

Write-Host "[4] npm install calistiriliyor..." -ForegroundColor Yellow
Write-Host "Bu biraz surebilir..." -ForegroundColor Gray
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

Write-Host "[5] npm run dev baslatiliyor..." -ForegroundColor Yellow
Write-Host "Frontend: http://127.0.0.1:3000" -ForegroundColor Cyan
Write-Host ""

& $NPM_EXE run dev









