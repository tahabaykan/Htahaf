# PATH Yenileme Scripti
# Her yeni PowerShell açıldığında otomatik çalışacak (profile'a eklendi)

$env:PATH = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "PATH yenilendi" -ForegroundColor Green








