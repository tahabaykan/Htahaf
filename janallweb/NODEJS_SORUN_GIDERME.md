# 🔧 Node.js Sorun Giderme

## ❌ Sorun: Node.js yüklü ama çalışmıyor

## ✅ Çözüm Adımları

### 1. Node.js Gerçekten Yüklü mü?

**Kontrol et:**
```powershell
Get-Command node -ErrorAction SilentlyContinue
```

VEYA manuel kontrol:
```powershell
Test-Path "C:\Program Files\nodejs\node.exe"
Test-Path "C:\Program Files (x86)\nodejs\node.exe"
```

### 2. PATH'e Eklendi mi?

**Kontrol et:**
```powershell
$env:PATH -split ';' | Select-String nodejs
```

**Eğer yoksa, manuel ekle:**
```powershell
$env:PATH += ";C:\Program Files\nodejs"
```

### 3. PowerShell'i YENİDEN BAŞLAT

**ÖNEMLİ:** PATH güncellemesi için mutlaka PowerShell'i kapat ve yeni bir tane aç!

### 4. Alternatif: Tam Yol ile Çalıştır

```powershell
& "C:\Program Files\nodejs\node.exe" --version
& "C:\Program Files\nodejs\npm.cmd" --version
```

### 5. Kurulumu Kontrol Et

**Program Files'da var mı?**
```powershell
dir "C:\Program Files\nodejs"
```

**Eğer yoksa:**
- Node.js kurulumu tamamlanmamış olabilir
- Tekrar kur

### 6. Sistem PATH'ini Güncelle

**Eğer hala çalışmıyorsa:**

1. Windows tuşu + R
2. `sysdm.cpl` yaz ve Enter
3. "Advanced" sekmesi → "Environment Variables"
4. "System variables" altında "Path" seç → "Edit"
5. "New" → `C:\Program Files\nodejs` ekle
6. OK → OK → OK
7. **Tüm PowerShell pencerelerini kapat ve yeniden aç**

### 7. Kurulumu Tekrar Yap

**Eğer hiçbiri çalışmıyorsa:**

1. Node.js'i kaldır (Control Panel → Programs)
2. https://nodejs.org/ → LTS indir
3. Kurulum sırasında **mutlaka** "Add to PATH" işaretle
4. Kurulum bitince **bilgisayarı yeniden başlat** (en garantili yöntem)







