# 🚀 Uygulamayı Çalıştırma Kılavuzu

## 📋 Hızlı Başlangıç

### 1. Şifre Ayarlama (İlk Kez)

`.env` dosyası zaten oluşturuldu ve şifreniz kaydedildi. Artık her seferinde şifre girmenize gerek yok!

### 2. Uygulamayı Çalıştırma

**PowerShell'de `quant_engine` klasörüne gidin:**

```powershell
cd quant_engine
```

**Sonra istediğiniz modu çalıştırın:**

#### 📊 ADIM 1: Sadece Data Testi (Emir Yok)

```powershell
python main.py live --execution-broker HAMMER --no-trading
```

#### 🧪 ADIM 2: Test Emri (Dry-Run)

```powershell
python main.py live --execution-broker HAMMER --test-order
```

#### 🚀 Canlı Trading (Dikkatli!)

```powershell
python main.py live --execution-broker HAMMER
```

#### 🔄 IBKR ile Execution

```powershell
python main.py live --execution-broker IBKR --ibkr-account DU123456
```

## 📝 Komut Parametreleri

### Zorunlu Parametreler

- **Yok!** Şifre `.env` dosyasından otomatik yükleniyor.

### Opsiyonel Parametreler

- `--execution-broker HAMMER` veya `IBKR` (default: HAMMER)
- `--hammer-account ALARIC:TOPI002240A7` (default: ALARIC:TOPI002240A7)
- `--ibkr-account DU123456` (IBKR kullanıyorsanız gerekli)
- `--no-trading` - Sadece data, emir yok
- `--test-order` - Test emri gönder

## 🔧 Şifreyi Değiştirme

`.env` dosyasını düzenleyin:

```
HAMMER_PASSWORD=YeniŞifreniz
```

## ⚠️ Önemli Notlar

1. **Her zaman `quant_engine` klasöründen çalıştırın**
2. **Şifre `.env` dosyasında saklanıyor** - güvenli tutun!
3. **`--no-trading` ile başlayın** - önce test edin
4. **Hammer Pro çalışıyor olmalı** (ws://127.0.0.1:16400)

## 🎯 Örnek Kullanım Senaryoları

### Senaryo 1: İlk Test (Sadece Data)

```powershell
cd quant_engine
python main.py live --execution-broker HAMMER --no-trading
```

### Senaryo 2: Hammer ile Test Emri

```powershell
cd quant_engine
python main.py live --execution-broker HAMMER --test-order
```

### Senaryo 3: IBKR ile Test Emri

```powershell
cd quant_engine
python main.py live --execution-broker IBKR --ibkr-account DU123456 --test-order
```

### Senaryo 4: Canlı Trading (Hammer)

```powershell
cd quant_engine
python main.py live --execution-broker HAMMER
```

## 🐛 Sorun Giderme

### "Hammer Pro password required!" hatası

`.env` dosyasını kontrol edin:
```powershell
type .env
```

Şifre doğru mu? `HAMMER_PASSWORD=Nl201090.` şeklinde olmalı.

### "Failed to connect to Hammer Pro" hatası

1. Hammer Pro çalışıyor mu?
2. Port 16400 açık mı?
3. Şifre doğru mu?

### "No such file or directory" hatası

`quant_engine` klasöründe olduğunuzdan emin olun:
```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine
```

## 📚 Daha Fazla Bilgi

- `TESTING_CHECKLIST.md` - Test adımları
- `docs/EXECUTION_ADAPTER.md` - Mimari detaylar






