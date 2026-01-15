# ✅ ÇÖZÜM - Node.js PATH Sorunu

## 🔴 SORUN

- `npm install` çalışırken `node` komutu bulunamıyor
- `node_modules` klasörü eksik/bozuk
- `vite` komutu bulunamıyor

## ✅ ÇÖZÜM

### Yöntem 1: Temiz Kurulum (Batch) - ÖNERİLEN

**Terminal 2'de (frontend klasöründeyken):**
```bash
.\TEMIZ_KURULUM.bat
```

Bu script:
- ✅ `node_modules` klasörünü siler
- ✅ `package-lock.json` siler
- ✅ npm cache temizler
- ✅ PATH'e Node.js ekler
- ✅ `npm install` yapar
- ✅ `npm run dev` başlatır

---

### Yöntem 2: PowerShell Script

**Terminal 2'de:**
```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb\frontend
powershell -ExecutionPolicy Bypass -File POWERSHELL_COZUM.ps1
```

---

### Yöntem 3: Manuel (Adım Adım)

**Terminal 2'de (frontend klasöründeyken):**

1. **PATH'e Node.js ekle:**
   ```powershell
   $env:PATH = "C:\Program Files\nodejs;$env:PATH"
   ```

2. **node_modules sil:**
   ```powershell
   Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
   ```

3. **npm install:**
   ```powershell
   & "C:\Program Files\nodejs\npm.cmd" install
   ```

4. **npm run dev:**
   ```powershell
   & "C:\Program Files\nodejs\npm.cmd" run dev
   ```

---

## 🎯 EN KOLAY: Batch Dosyası

```bash
cd janallweb\frontend
.\TEMIZ_KURULUM.bat
```

---

## ⚠️ NOT

- `npm install` biraz sürebilir (5-10 dakika)
- İlk kurulumda tüm paketler indirilecek







