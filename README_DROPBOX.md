# Dropbox Otomatik Dosya Yükleyici Kurulum Talimatları

## 1. Gerekli Kütüphaneleri Yükleyin
```bash
pip install -r requirements.txt
```

## 2. Dropbox Access Token Alın

### Adım 1: Dropbox Developer Console'a gidin
- https://www.dropbox.com/developers/apps adresine gidin
- "Create app" butonuna tıklayın

### Adım 2: App oluşturun
- "Choose API": "Dropbox API" seçin
- "Choose the type of access you need": "Full Dropbox" seçin
- App adını girin (örn: "StockTracker Uploader")

### Adım 3: Access Token alın
- Oluşturulan app'in "Settings" sekmesine gidin
- "OAuth 2" bölümünde "Generated access token" butonuna tıklayın
- Çıkan token'ı kopyalayın (bu token'ı .env dosyasında kullanacaksınız)

## 3. Konfigürasyon Dosyasını Oluşturun

### .env dosyası oluşturun:
1. `.env.example` dosyasını `.env` olarak kopyalayın
2. `.env` dosyasını açın ve aşağıdaki değerleri doldurun:

```
DROPBOX_ACCESS_TOKEN=buraya_dropbox_token_yapistirin
LOCAL_FILE_PATH=C:\Users\User\Documents\your_file.csv
DROPBOX_FOLDER=/StockTracker
DROPBOX_FILENAME=your_file.csv
```

## 4. Scripti Çalıştırın

### Komut satırından:
```bash
python dropbox_uploader.py
```

### Script özellikleri:
- Her 3 dakikada bir local dosyayı kontrol eder
- Dosya değiştiyse Dropbox'a yükler
- Tüm işlemler log dosyasına kaydedilir (`dropbox_uploader.log`)
- Ctrl+C ile durdurabilirsiniz

## 5. Sorun Giderme

### Yaygın hatalar:
1. **"DROPBOX_ACCESS_TOKEN bulunamadı"**: .env dosyasını kontrol edin
2. **"Local dosya bulunamadı"**: LOCAL_FILE_PATH'ı kontrol edin
3. **"Dropbox bağlantı hatası"**: Token'ın geçerli olduğundan emin olun

### Log dosyası:
Tüm işlemler `dropbox_uploader.log` dosyasına kaydedilir. Sorun yaşarsanız bu dosyayı kontrol edin.

## 6. Otomatik Başlatma (Opsiyonel)

### Windows'ta otomatik başlatma için:
1. Windows Task Scheduler'ı açın
2. "Create Basic Task" seçin
3. Script'in tam yolunu girin
4. Bilgisayar açıldığında çalışacak şekilde ayarlayın

