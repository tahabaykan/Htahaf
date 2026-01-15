# ✅ ÇÖZÜM - PowerShell Komutları

## ❌ SORUN

PowerShell'de tırnak içindeki komutla argüman geçemiyoruz.

## ✅ ÇÖZÜM

### Yöntem 1: PowerShell Script (Önerilen)

**Terminal 2'de:**
```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb
powershell -ExecutionPolicy Bypass -File FRONTEND_POWERSHELL.ps1
```

### Yöntem 2: Batch Dosyası

**Terminal 2'de:**
```bash
cd janallweb
.\FRONTEND_BASLAT_SON.bat
```

### Yöntem 3: Manuel (PowerShell'de)

**Terminal 2'de (frontend klasöründeyken):**
```powershell
$NPM = "C:\Program Files\nodejs\npm.cmd"
& $NPM install
& $NPM run dev
```

---

## 🎯 EN KOLAY: Batch Dosyası

```bash
cd janallweb
.\FRONTEND_BASLAT_SON.bat
```

Bu script:
- ✅ Node.js'i bulur
- ✅ npm install yapar
- ✅ npm run dev başlatır

---

## 📋 ÖZET

- ✅ Node.js bulundu: v24.12.0
- ✅ npm bulundu: 11.6.2
- ⏳ Frontend başlatılacak

**Şimdi dene:**
```bash
cd janallweb
.\FRONTEND_BASLAT_SON.bat
```









