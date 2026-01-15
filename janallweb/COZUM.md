# 🔧 ÇÖZÜM - Blueprint Hatası

## ❌ SORUN

Backend başlatılamıyor - Blueprint hatası:
```
AssertionError: The setup method 'route' can no longer be called on the blueprint 'api'
```

## ✅ ÇÖZÜM 1: Basit Backend (Hızlı Test)

**Terminal 1'de:**
```bash
cd janallweb
python app_simple.py
```

VEYA:
```bash
cd janallweb
BASLAT_BASIT.bat
```

Bu versiyon:
- ✅ Blueprint hatası YOK
- ✅ Temel API endpoint'leri var
- ✅ Test için yeterli

## ✅ ÇÖZÜM 2: Ana Backend'i Düzelt

Ana `app.py` dosyasını düzeltmek için farklı bir yaklaşım deniyoruz.

**Şimdi test et:**
```bash
cd janallweb
python app_simple.py
```

Eğer bu çalışırsa, ana app.py'yi de aynı şekilde düzeltiriz.

## 📋 TERMINAL 2 (FRONTEND)

Node.js yükle:
1. https://nodejs.org/ → LTS indir
2. Kur (Add to PATH işaretle)
3. PowerShell'i yeniden başlat
4. `node --version` kontrol et

Sonra:
```bash
cd janallweb\frontend
npm install
npm run dev
```

## 🎯 ÖNCELİK

1. **Önce basit backend'i test et:** `python app_simple.py`
2. **Çalışırsa:** Ana app.py'yi düzeltiriz
3. **Node.js yükle:** Frontend için
4. **Frontend başlat:** `npm run dev`







