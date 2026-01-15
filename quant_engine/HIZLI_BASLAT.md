# Hızlı Başlatma Rehberi

## ✅ Node.js Kurulu ve PATH'te

Artık her yeni PowerShell penceresinde Node.js otomatik çalışacak.

## 🚀 Frontend Başlatma

```powershell
cd quant_engine\frontend
npm run dev
```

Tarayıcıda: http://localhost:3000

## 🔧 Backend Başlatma (Ayrı PowerShell Penceresi)

```powershell
cd quant_engine
python main.py api
```

Backend: http://localhost:8000

## ⚡ PATH Yenileme (Gerekirse)

Eğer yeni bir PowerShell'de hala çalışmıyorsa:

```powershell
$env:PATH = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

Veya `quant_engine\refresh_path.ps1` scriptini çalıştır.

## 📝 Not

PowerShell profile'ına PATH yenileme komutu eklendi. Artık her yeni PowerShell açıldığında otomatik PATH yenilenecek.






