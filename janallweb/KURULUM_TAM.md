# 🚀 Tam Kurulum Rehberi - Algoritma Çalıştırma Sistemi

## 📦 Adım 1: Node.js Kurulumu

### Yöntem 1: Resmi Web Sitesi (Önerilen)

1. **https://nodejs.org/** adresine git
2. **LTS versiyonu** indir (v20.x.x veya üzeri)
3. `.msi` dosyasını çalıştır
4. Kurulum sırasında:
   - ✅ "Add to PATH" seçeneğini işaretle
   - ✅ "npm package manager" seçeneğini işaretle
5. Kurulum bitince **PowerShell'i YENİDEN BAŞLAT**
6. Kontrol et:
   ```powershell
   node --version
   npm --version
   ```

### Yöntem 2: Winget (Hızlı)

```powershell
winget install OpenJS.NodeJS.LTS
```

Kurulumdan sonra **PowerShell'i yeniden başlat!**

## 📦 Adım 2: Python Bağımlılıkları

```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb
pip install -r requirements.txt
```

## 📦 Adım 3: Frontend Bağımlılıkları

```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb\frontend
npm install
```

## 🚀 Adım 4: Sistemi Başlat

### Terminal 1: Backend
```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb
python app.py
```

### Terminal 2: Frontend
```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb\frontend
npm run dev
```

## ✅ Kontrol

- Backend: http://127.0.0.1:5000
- Frontend: http://127.0.0.1:3000

## 🎯 Algoritma Çalıştırma Özellikleri

Sistem şunları destekleyecek:
- ✅ Real-time market data
- ✅ Pozisyon yönetimi
- ✅ Emir gönderme/iptal
- ✅ CSV işlemleri
- ✅ Algoritma çalıştırma (backend'de)
- ✅ WebSocket ile real-time güncellemeler







