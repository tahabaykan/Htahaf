# Node.js Kontrol Scripti

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NODE.JS KONTROL" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Node.js komutunu ara
Write-Host "[1] Node.js komutu araniyor..." -ForegroundColor Yellow
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    Write-Host "   OK - Node.js bulundu: $($nodeCmd.Source)" -ForegroundColor Green
    Write-Host "   Versiyon: $(& $nodeCmd.Source --version)" -ForegroundColor Green
} else {
    Write-Host "   HATA - Node.js komutu bulunamadi!" -ForegroundColor Red
}

Write-Host ""

# 2. Node.js dosyasını ara
Write-Host "[2] Node.js dosyasi araniyor..." -ForegroundColor Yellow
$nodePaths = @(
    "C:\Program Files\nodejs\node.exe",
    "C:\Program Files (x86)\nodejs\node.exe",
    "$env:USERPROFILE\AppData\Roaming\npm\node.exe"
)

$found = $false
foreach ($path in $nodePaths) {
    if (Test-Path $path) {
        Write-Host "   OK - Node.js bulundu: $path" -ForegroundColor Green
        Write-Host "   Versiyon: $(& $path --version)" -ForegroundColor Green
        $found = $true
        break
    }
}

if (-not $found) {
    Write-Host "   HATA - Node.js dosyasi bulunamadi!" -ForegroundColor Red
    Write-Host "   Node.js yuklu degil veya farkli bir konumda!" -ForegroundColor Red
}

Write-Host ""

# 3. PATH kontrolü
Write-Host "[3] PATH kontrolu..." -ForegroundColor Yellow
$pathEntries = $env:PATH -split ';'
$nodeInPath = $pathEntries | Where-Object { $_ -like "*nodejs*" }
if ($nodeInPath) {
    Write-Host "   OK - Node.js PATH'te:" -ForegroundColor Green
    foreach ($entry in $nodeInPath) {
        Write-Host "     $entry" -ForegroundColor Green
    }
} else {
    Write-Host "   HATA - Node.js PATH'te degil!" -ForegroundColor Red
    Write-Host "   Cozum: PowerShell'i yeniden baslat veya PATH'e manuel ekle" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "COZUM ONERILERI" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. PowerShell'i KAPAT ve YENIDEN AC" -ForegroundColor Yellow
Write-Host "2. Eger hala calismiyorsa, bilgisayari YENIDEN BASLAT" -ForegroundColor Yellow
Write-Host "3. Node.js kurulumunu tekrar yap (Add to PATH isaretle)" -ForegroundColor Yellow
Write-Host ""









