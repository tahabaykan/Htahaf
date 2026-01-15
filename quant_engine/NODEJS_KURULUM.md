# Node.js Kurulum Rehberi

## Windows'ta Node.js Kurulumu

### Yöntem 1: Resmi Web Sitesinden İndirme (Önerilen)

1. **Node.js İndir**
   - https://nodejs.org/ adresine git
   - LTS (Long Term Support) versiyonunu indir (önerilen)
   - Örnek: `node-v20.x.x-x64.msi` (Windows Installer)

2. **Kurulum**
   - İndirilen `.msi` dosyasını çalıştır
   - Kurulum sihirbazını takip et
   - "Add to PATH" seçeneğinin işaretli olduğundan emin ol
   - "Install" butonuna tıkla

3. **Kurulumu Doğrula**
   - PowerShell veya Command Prompt'u yeniden aç (önemli!)
   - Şu komutları çalıştır:
   ```powershell
   node --version
   npm --version
   ```
   - Her ikisi de versiyon numarası göstermeli

### Yöntem 2: Chocolatey ile Kurulum (Eğer Chocolatey yüklüyse)

```powershell
choco install nodejs-lts
```

### Yöntem 3: Winget ile Kurulum (Windows 11/10)

```powershell
winget install OpenJS.NodeJS.LTS
```

## Kurulum Sonrası

1. **PowerShell'i Yeniden Aç**
   - Önemli: PATH değişikliklerinin uygulanması için terminal'i kapatıp aç

2. **Frontend Dependencies Yükle**
   ```powershell
   cd quant_engine\frontend
   npm install
   ```

3. **Development Server Başlat**
   ```powershell
   npm run dev
   ```

## Sorun Giderme

### "npm is not recognized" Hatası

1. PowerShell'i yönetici olarak aç
2. PATH'i kontrol et:
   ```powershell
   $env:PATH
   ```
3. Node.js'in kurulu olduğu yolu kontrol et (genellikle `C:\Program Files\nodejs\`)
4. PATH'e ekle (gerekirse):
   ```powershell
   $env:PATH += ";C:\Program Files\nodejs\"
   ```

### Alternatif: NVM (Node Version Manager)

Eğer birden fazla Node.js versiyonu yönetmek istiyorsanız:

1. **NVM-Windows İndir**: https://github.com/coreybutler/nvm-windows/releases
2. **Kur ve Kullan**:
   ```powershell
   nvm install lts
   nvm use lts
   ```

## Hızlı Test

Kurulum başarılı mı kontrol et:

```powershell
node --version    # v20.x.x gibi bir versiyon göstermeli
npm --version     # 10.x.x gibi bir versiyon göstermeli
```

## Frontend Başlatma

Node.js kurulduktan sonra:

```powershell
cd quant_engine\frontend
npm install
npm run dev
```

Tarayıcıda http://localhost:3000 adresine git.








