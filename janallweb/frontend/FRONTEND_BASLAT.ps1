# PowerShell script - Frontend başlatma
Write-Host "========================================"
Write-Host "FRONTEND BASLATILIYOR"
Write-Host "========================================"
Write-Host ""

# Dizine git
Set-Location $PSScriptRoot

# Node.js'i PATH'e ekle
$env:PATH = "C:\Program Files\nodejs;$env:PATH"

Write-Host "Node.js PATH'e eklendi"
Write-Host ""

Write-Host "npm run dev baslatiliyor..."
Write-Host ""

# npm.cmd'i direkt çağır (execution policy sorununu önler)
& "C:\Program Files\nodejs\npm.cmd" run dev









