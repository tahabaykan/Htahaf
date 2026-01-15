# 🚀 HIZLI BAŞLATMA

## TERMINAL 1 - BACKEND

### Seçenek A: Basit Backend (Önerilen - Hızlı)
```bash
cd janallweb
python app_simple.py
```

### Seçenek B: Ana Backend (Düzeltildi)
```bash
cd janallweb
python app.py
```

**Beklenen çıktı:**
```
Server initialized for threading.
 * Running on http://127.0.0.1:5000
Press CTRL+C to quit
```

**Test:**
- Tarayıcıda: http://127.0.0.1:5000/api/health
- Başarılıysa: `{"status":"healthy",...}` görmelisin

---

## TERMINAL 2 - FRONTEND

**Node.js yükle:**
1. https://nodejs.org/ → LTS indir
2. Kur (Add to PATH işaretle)
3. PowerShell'i YENİDEN BAŞLAT
4. Kontrol: `node --version`

**Frontend başlat:**
```bash
cd janallweb\frontend
npm install
npm run dev
```

---

## ✅ BAŞARILI OLDU MU?

- ✅ Backend: http://127.0.0.1:5000 çalışıyor
- ✅ Frontend: http://127.0.0.1:3000 çalışıyor
- ✅ Tarayıcı: http://127.0.0.1:3000 açılıyor

---

## 🆘 HALA HATA VARSA

**Backend hatası:**
- `python app_simple.py` dene (basit versiyon)
- Hata mesajını gönder

**Frontend hatası:**
- Node.js yüklü mü? (`node --version`)
- PowerShell'i yeniden başlattın mı?









