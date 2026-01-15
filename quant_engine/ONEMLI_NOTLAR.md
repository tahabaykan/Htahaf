# Önemli Notlar - Node.js PATH Sorunu

## ✅ Çözüldü (Bu Oturum İçin)

1. **PATH Eklendi**: `C:\Program Files\nodejs\` PATH'e eklendi (sadece bu PowerShell oturumu için)
2. **Execution Policy Düzeltildi**: `RemoteSigned` olarak ayarlandı (kalıcı - CurrentUser scope)
3. **Node.js Çalışıyor**: v24.12.0
4. **npm Çalışıyor**: 11.6.2

## ⚠️ Dikkat

### PATH Sadece Bu Oturum İçin
- Yeni bir PowerShell penceresi açarsanız, PATH tekrar eklenmesi gerekir
- Veya `fix_nodejs_path.ps1` scriptini çalıştırın

### Kalıcı Çözüm İçin
1. PowerShell'i **Yönetici olarak** aç
2. `fix_nodejs_path_permanent.ps1` scriptini çalıştır
3. Veya manuel olarak:
   - Windows Ayarlar → Sistem → Hakkında → Gelişmiş sistem ayarları
   - Ortam Değişkenleri → Sistem değişkenleri → Path → Düzenle
   - `C:\Program Files\nodejs\` ekle

## 🚀 Frontend Başlatma

```powershell
cd quant_engine\frontend
npm run dev
```

Tarayıcıda http://localhost:3000 açılacak.

## 📝 Hızlı PATH Ekleme (Her Yeni PowerShell İçin)

Yeni bir PowerShell açtığınızda:

```powershell
$env:PATH += ";C:\Program Files\nodejs\"
```

Veya `fix_nodejs_path.ps1` scriptini çalıştırın.








