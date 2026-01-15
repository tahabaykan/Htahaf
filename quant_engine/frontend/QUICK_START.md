# Frontend Quick Start

## Node.js Kurulumu Gerekli

Node.js yüklü değilse önce yükle:
- https://nodejs.org/ adresinden LTS versiyonunu indir
- Kurulum sihirbazını takip et
- PowerShell'i yeniden aç

## Hızlı Başlangıç

```powershell
# 1. Dependencies yükle
npm install

# 2. Development server başlat
npm run dev
```

Tarayıcıda http://localhost:3000 açılacak.

## Alternatif: Build ve Static Serving

Eğer npm kullanmak istemiyorsanız, build edilmiş versiyonu FastAPI'den serve edebilirsiniz:

```powershell
# Build (bir kez)
npm run build

# Build edilmiş dosyalar dist/ klasöründe olacak
# FastAPI static file serving ile serve edilebilir
```

## Sorun Giderme

### "npm is not recognized"
- Node.js kurulu mu kontrol et: `node --version`
- PowerShell'i yeniden aç
- PATH'e Node.js eklendi mi kontrol et

### Port 3000 kullanımda
- Vite config'de port değiştirilebilir
- Veya başka bir port kullan: `npm run dev -- --port 3001`








