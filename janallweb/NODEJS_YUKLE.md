# 📦 Node.js Yükleme Rehberi

## ❌ DURUM: Node.js Yüklü Değil

Script Node.js'i bulamadı. Yüklemen gerekiyor.

## ✅ ADIM ADIM YÜKLEME

### 1. Node.js İndir

1. **Tarayıcıda aç:** https://nodejs.org/
2. **Yeşil "LTS" butonuna tıkla** (Recommended For Most Users)
   - Örnek: "v20.11.0 LTS" veya üzeri
3. **İndirme başlayacak** (.msi dosyası)

### 2. Node.js Kur

1. **İndirilen .msi dosyasını çalıştır**
2. **Kurulum sihirbazı:**
   - Welcome → **Next**
   - License Agreement → **Accept** → **Next**
   - Destination Folder → **Next** (varsayılan kalabilir)
   - **ÖNEMLİ:** Custom Setup ekranında:
     - ✅ **"Add to PATH"** seçeneğinin işaretli olduğundan emin ol
     - ✅ **"npm package manager"** seçeneğinin işaretli olduğundan emin ol
   - **Next** → **Install**
   - Kurulum bitince **Finish**

### 3. Bilgisayarı Yeniden Başlat

**ÖNEMLİ:** PATH güncellemesi için **mutlaka bilgisayarı yeniden başlat!**

### 4. Kontrol Et

**Yeni PowerShell aç:**
```bash
node --version
npm --version
```

Her ikisi de versiyon numarası göstermeli.

### 5. Frontend'i Başlat

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb
.\FRONTEND_BASLAT.bat
```

---

## 🔍 Node.js Nerede Olabilir?

**Kontrol et:**
```bash
cd janallweb
.\NODEJS_BUL.bat
```

Bu script Node.js'in nerede olduğunu bulur.

---

## ⚠️ ÖNEMLİ NOTLAR

- ✅ Kurulum sırasında **"Add to PATH"** mutlaka işaretle
- ✅ Kurulum bitince **bilgisayarı yeniden başlat**
- ✅ PowerShell'i yeniden başlatmak yeterli olmayabilir, bilgisayarı restart et

---

## 🎯 ÖZET

1. https://nodejs.org/ → LTS indir
2. Kur (Add to PATH işaretle)
3. **Bilgisayarı yeniden başlat**
4. `node --version` kontrol et
5. Frontend'i başlat







