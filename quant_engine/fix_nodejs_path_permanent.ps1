# Node.js PATH Kalıcı Düzeltme Scripti (Yönetici olarak çalıştırılmalı)
# Bu script Node.js'i sistem PATH'ine kalıcı olarak ekler

Write-Host "Node.js PATH kalıcı düzeltme..." -ForegroundColor Yellow
Write-Host "NOT: Bu script YÖNETİCİ olarak çalıştırılmalıdır!" -ForegroundColor Red
Write-Host "`nYönetici olarak çalıştırmak için:" -ForegroundColor Yellow
Write-Host "1. PowerShell'i sağ tıkla" -ForegroundColor Cyan
Write-Host "2. 'Run as Administrator' seç" -ForegroundColor Cyan
Write-Host "3. Bu scripti çalıştır" -ForegroundColor Cyan
Write-Host "`nDevam etmek için Enter'a basın (iptal için Ctrl+C)..." -ForegroundColor Yellow
Read-Host

# Yönetici kontrolü
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "HATA: Bu script yönetici yetkisi gerektirir!" -ForegroundColor Red
    Write-Host "Lütfen PowerShell'i 'Run as Administrator' olarak açın." -ForegroundColor Yellow
    exit 1
}

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
    # Sistem PATH'ine ekle
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    
    if ($currentPath -notlike "*$nodePath*") {
        $newPath = $currentPath + ";$nodePath"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
        Write-Host "PATH'e kalıcı olarak eklendi!" -ForegroundColor Green
        Write-Host "`nLütfen PowerShell'i yeniden açın (PATH değişiklikleri için gerekli)" -ForegroundColor Yellow
    } else {
        Write-Host "Node.js zaten PATH'te!" -ForegroundColor Green
    }
} else {
    Write-Host "Node.js bulunamadı! Lütfen Node.js'i yükleyin." -ForegroundColor Red
    Write-Host "https://nodejs.org/" -ForegroundColor Cyan
}








