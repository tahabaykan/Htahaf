# Node.js PATH Düzeltme Scripti
# Bu script Node.js'i PATH'e ekler (sadece bu PowerShell oturumu için)

Write-Host "Node.js PATH düzeltiliyor..." -ForegroundColor Yellow

# Node.js'in standart kurulum yollarını kontrol et
$nodePaths = @(
    "C:\Program Files\nodejs",
    "$env:LOCALAPPDATA\Programs\nodejs",
    "$env:ProgramFiles\nodejs"
)

$nodePath = $null
foreach ($path in $nodePaths) {
    if (Test-Path "$path\node.exe") {
        $nodePath = $path
        Write-Host "Node.js bulundu: $nodePath" -ForegroundColor Green
        break
    }
}

if ($nodePath) {
    # Mevcut PATH'e ekle (sadece bu oturum için)
    $env:PATH += ";$nodePath"
    Write-Host "PATH'e eklendi (bu oturum için)" -ForegroundColor Green
    
    # Doğrula
    Write-Host "`nKontrol ediliyor..." -ForegroundColor Yellow
    $nodeVersion = node --version 2>&1
    $npmVersion = npm --version 2>&1
    
    if ($nodeVersion -match "v\d+") {
        Write-Host "✓ Node.js: $nodeVersion" -ForegroundColor Green
    } else {
        Write-Host "✗ Node.js bulunamadı" -ForegroundColor Red
    }
    
    if ($npmVersion -match "\d+") {
        Write-Host "✓ npm: $npmVersion" -ForegroundColor Green
    } else {
        Write-Host "✗ npm bulunamadı" -ForegroundColor Red
    }
    
    Write-Host "`nNot: Bu değişiklik sadece bu PowerShell oturumu için geçerlidir." -ForegroundColor Yellow
    Write-Host "Kalıcı olması için sistem PATH'ine eklemeniz gerekir." -ForegroundColor Yellow
} else {
    Write-Host "Node.js bulunamadı! Lütfen Node.js'i yükleyin." -ForegroundColor Red
    Write-Host "https://nodejs.org/" -ForegroundColor Cyan
}








