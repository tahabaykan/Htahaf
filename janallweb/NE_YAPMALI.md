# 🚀 NE YAPMALI? - ADIM ADIM

## 📋 ŞU AN DURUM

- ✅ Backend kodu hazır (hatası düzeltildi)
- ❌ Backend başlatılmadı (Terminal 1'de çalıştırılmalı)
- ❌ Node.js yüklü değil (Frontend için gerekli)

---

## 🎯 ADIM 1: BACKEND'İ BAŞLAT

**Terminal 1 aç** ve şunu çalıştır:

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb
python app.py
```

**Beklenen çıktı:**
```
Server initialized for threading.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
```

**Eğer hata varsa:**
- Hata mesajını kopyala ve gönder
- `BACKEND_TEST.bat` çalıştır

**Test et:**
- Tarayıcıda: http://127.0.0.1:5000/api/health
- Başarılıysa: `{"status":"healthy",...}` görmelisin

---

## 🎯 ADIM 2: NODE.JS YÜKLE

1. **https://nodejs.org/** adresine git
2. **"LTS"** butonuna tıkla (v20.x.x veya üzeri)
3. **İndirilen .msi dosyasını çalıştır**
4. **Kurulum sırasında:**
   - ✅ "Add to PATH" seçeneğini işaretle
   - ✅ "npm package manager" seçeneğini işaretle
5. **Kurulum bitince PowerShell'i KAPAT ve YENİDEN AÇ**
6. **Kontrol et:**
   ```bash
   node --version
   npm --version
   ```
   Her ikisi de versiyon numarası göstermeli.

---

## 🎯 ADIM 3: FRONTEND'İ BAŞLAT

**Yeni Terminal 2 aç** (Terminal 1 açık kalsın!) ve:

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb\frontend
npm install
```

Bu biraz sürebilir (ilk kez çalıştırıyorsan).

Sonra:
```bash
npm run dev
```

**Beklenen çıktı:**
```
VITE v5.x.x  ready in xxx ms
➜  Local:   http://127.0.0.1:3000/
```

---

## ✅ BAŞARILI OLDU MU?

- ✅ Backend: http://127.0.0.1:5000 çalışıyor
- ✅ Frontend: http://127.0.0.1:3000 çalışıyor
- ✅ Tarayıcıda: http://127.0.0.1:3000 açılıyor

---

## 🆘 SORUN MU VAR?

**Backend başlamıyor:**
- Hata mesajını gönder
- `python test_backend_fixed.py` çalıştır

**Node.js yüklenmedi:**
- PowerShell'i yeniden başlattın mı?
- PATH'e eklendi mi kontrol et

**Frontend başlamıyor:**
- Node.js yüklü mü? (`node --version`)
- `npm install` başarılı oldu mu?







