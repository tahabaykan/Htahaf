# Node.js Kurulum Rehberi

## ❌ Sorun: npm bulunamıyor

Node.js sisteminde yüklü değil veya PATH'e eklenmemiş.

## ✅ Çözüm: Node.js Yükle

### Yöntem 1: Resmi Web Sitesinden İndir (Önerilen)

1. **Node.js İndir**: https://nodejs.org/ adresine git
2. **LTS Versiyonu İndir** (Long Term Support - önerilen)
3. **Kurulum Dosyasını Çalıştır** (.msi dosyası)
4. **Kurulum Sihirbazını Takip Et** (Next, Next, Install)
5. **Terminal'i Yeniden Başlat** (PowerShell'i kapat ve aç)
6. **Kontrol Et**: `node --version` ve `npm --version` komutlarını çalıştır

### Yöntem 2: Chocolatey ile (Eğer yüklüyse)

```powershell
choco install nodejs
```

### Yöntem 3: Winget ile (Windows 10/11)

```powershell
winget install OpenJS.NodeJS.LTS
```

## ✅ Kurulum Sonrası Kontrol

Terminal'i **YENİDEN BAŞLAT** ve şunu çalıştır:

```powershell
node --version
npm --version
```

Her ikisi de versiyon numarası göstermeli.

## 🚀 Sonraki Adım

Node.js yüklendikten sonra:

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janallweb\frontend
npm install
npm run dev
```

## ⚠️ Önemli

- Kurulumdan sonra **mutlaka terminal'i yeniden başlat**
- PATH güncellemesi için restart gerekebilir
- Eğer hala çalışmıyorsa, bilgisayarı yeniden başlat







