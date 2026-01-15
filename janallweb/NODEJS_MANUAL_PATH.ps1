# Node.js'i PATH'e manuel ekle (geçici)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NODE.JS PATH EKLEME (GECICI)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Node.js konumlarını kontrol et
$nodePaths = @(
    "C:\Program Files\nodejs",
    "C:\Program Files (x86)\nodejs"
)

$foundPath = $null
foreach ($path in $nodePaths) {
    if (Test-Path "$path\node.exe") {
        $foundPath = $path
        Write-Host "[OK] Node.js bulundu: $path" -ForegroundColor Green
        break
    }
}

if (-not $foundPath) {
    Write-Host "[HATA] Node.js bulunamadi!" -ForegroundColor Red
    Write-Host "Lutfen Node.js'i yukleyin: https://nodejs.org/" -ForegroundColor Yellow
    pause
    exit
}

# PATH'e ekle (sadece bu session için)
Write-Host ""
Write-Host "PATH'e ekleniyor (gecici)..." -ForegroundColor Yellow
$env:PATH += ";$foundPath"

Write-Host ""
Write-Host "Test ediliyor..." -ForegroundColor Yellow
Write-Host ""

# Test et
try {
    $nodeVersion = & "$foundPath\node.exe" --version
    $npmVersion = & "$foundPath\npm.cmd" --version
    
    Write-Host "[OK] Node.js calisiyor!" -ForegroundColor Green
    Write-Host "  Node.js: $nodeVersion" -ForegroundColor Green
    Write-Host "  npm: $npmVersion" -ForegroundColor Green
    Write-Host ""
    Write-Host "NOT: Bu PATH eklemesi sadece bu PowerShell session'i icin gecerli!" -ForegroundColor Yellow
    Write-Host "     Kalici yapmak icin bilgisayari yeniden baslat veya sistem PATH'ine ekle" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Simdi frontend'i baslatabilirsin:" -ForegroundColor Cyan
    Write-Host "  cd frontend" -ForegroundColor White
    Write-Host "  npm install" -ForegroundColor White
    Write-Host "  npm run dev" -ForegroundColor White
    
} catch {
    Write-Host "[HATA] Node.js calistirilamadi: $_" -ForegroundColor Red
}

Write-Host ""
pause









