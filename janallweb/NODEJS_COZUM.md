# 🔧 Node.js Sorun Çözümü

## ✅ Hızlı Çözüm

### Yöntem 1: Otomatik Script (Önerilen)

**Terminal 2'de:**
```bash
cd janallweb
FRONTEND_BASLAT.bat
```

Bu script:
- ✅ Node.js'i otomatik bulur
- ✅ PATH'e ekler (geçici)
- ✅ npm install yapar
- ✅ npm run dev başlatır

### Yöntem 2: Manuel PATH Ekleme (Geçici)

**PowerShell'de:**
```powershell
cd janallweb
powershell -ExecutionPolicy Bypass -File NODEJS_MANUAL_PATH.ps1
```

Sonra:
```powershell
cd frontend
npm install
npm run dev
```

### Yöntem 3: Kalıcı PATH Ekleme

**Eğer her seferinde eklemek istemiyorsan:**

1. **Windows tuşu + R** → `sysdm.cpl` yaz → Enter
2. **Advanced** sekmesi → **Environment Variables**
3. **System variables** altında **Path** seç → **Edit**
4. **New** → Node.js yolunu ekle:
   - `C:\Program Files\nodejs` VEYA
   - `C:\Program Files (x86)\nodejs`
5. **OK** → **OK** → **OK**
6. **Bilgisayarı yeniden başlat** (en garantili)

## 🎯 Önerilen: FRONTEND_BASLAT.bat

**En kolay yöntem:**
```bash
cd janallweb
FRONTEND_BASLAT.bat
```

Bu script her şeyi otomatik yapar!

## 📋 Durum

- ✅ Backend çalışıyor (Terminal 1)
- ⏳ Frontend için Node.js düzeltiliyor (Terminal 2)







