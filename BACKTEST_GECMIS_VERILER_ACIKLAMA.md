# Geçmiş Sistem Çıktıları ve Backtest İçin Kullanımı

## 🔍 Geçmiş Sistem Çıktıları Nedir?

Geçmiş sistem çıktıları, daha önce `run_anywhere_n.py` veya benzeri scriptler çalıştırıldığında oluşturulan CSV dosyalarıdır.

### Önemli CSV Dosyaları:

1. **`janalldata.csv`**: Tüm hisselerin FINAL_THG, SHORT_FINAL skorları ve diğer metrikleri
2. **`tumcsvlong.csv`**: LONG pozisyonlar için seçilen hisseler
3. **`tumcsvshort.csv`**: SHORT pozisyonlar için seçilen hisseler

## ❌ Problem: Geçmiş Veriler Yok

**Gerçek durum**: Muhtemelen geçmiş 3 ay için sistem çıktılarınız yok çünkü:
- Sistem her gün çalıştırılmıyor
- Geçmiş tarihler için CSV dosyaları kaydedilmemiş
- Her çalıştırmada mevcut veriler üzerine yazılıyor

## ✅ Çözümler

### Çözüm 1: Geçmiş Tarihler İçin Sistem Çalıştırma (EN GERÇEKÇİ)

**Nasıl çalışır:**
1. 3 ay önceden başla
2. Her gün için o güne kadar olan IBKR verilerini çek
3. Sistem çalıştır (run_anywhere_n.py)
4. CSV dosyalarını tarihli olarak kaydet
5. Backtest'te bu dosyaları kullan

**Avantajlar:**
- ✅ En gerçekçi sonuçlar
- ✅ Gerçek geçmiş verilerle çalışır

**Dezavantajlar:**
- ❌ Çok yavaş (10-22 saat)
- ❌ Her gün için IBKR'den veri çekmek gerekir
- ❌ Her gün için tüm sistem çalışmalı

### Çözüm 2: Mevcut Verilerle Simülasyon (HIZLI)

**Nasıl çalışır:**
1. Mevcut `janalldata.csv`, `tumcsvlong.csv`, `tumcsvshort.csv` dosyalarını kullan
2. Her gün için skorlara küçük rastgele değişiklikler ekle
3. Backtest'i çalıştır

**Avantajlar:**
- ✅ Çok hızlı (5-10 dakika)
- ✅ Kolay kullanım

**Dezavantajlar:**
- ❌ Gerçekçi değil
- ❌ Geçmiş verileri yansıtmaz

### Çözüm 3: Hibrit Yaklaşım (ÖNERİLEN)

**Nasıl çalışır:**
1. Geçmiş tarihler için IBKR'den fiyat verilerini çek
2. Bu fiyat verilerinden basitleştirilmiş skorlar hesapla
3. Backtest'i çalıştır

**Avantajlar:**
- ✅ Orta hız (1-2 saat)
- ✅ Gerçek fiyat verilerini kullanır
- ✅ Gerçekçi sonuçlar

**Dezavantajlar:**
- ❌ Tam sistem çıktıları kadar gerçekçi değil

## 🚀 Önerilen Yaklaşım

**En iyi çözüm**: Geçmiş tarihler için IBKR'den fiyat verilerini çekip, bu verilerden skorları hesaplamak.

Bu yaklaşım için `backtest_walkforward.py` scripti hazır. Bu script:
- Her gün için o güne kadar olan IBKR fiyat verilerini çeker
- Bu verilerden FINAL_THG ve SHORT_FINAL skorlarını hesaplar
- Backtest'i çalıştırır

## 📝 Gelecek İçin Öneri

Eğer gelecekte gerçekçi backtest yapmak istiyorsanız:

1. **Günlük CSV Yedekleme**: Her gün sistem çalıştıktan sonra CSV dosyalarını tarihli olarak kaydedin:
   ```python
   # Örnek: janalldata_20240101.csv, janalldata_20240102.csv, vb.
   ```

2. **Otomatik Yedekleme Scripti**: Sistem çalıştıktan sonra otomatik yedekleme yapan bir script oluşturun

3. **Veritabanı Kullanımı**: CSV yerine veritabanı kullanarak geçmiş verileri saklayın

## 🔧 Şu An İçin Ne Yapmalıyız?

**Seçenek 1**: `backtest_walkforward.py` kullanın (geçmiş fiyat verilerinden skor hesaplar)
- Süre: 1-2 saat
- Gerçekçilik: Orta-Yüksek

**Seçenek 2**: `backtest_realistic.py` kullanın (simüle edilmiş veriler)
- Süre: 5-10 dakika
- Gerçekçilik: Düşük-Orta

**Seçenek 3**: Geçmiş tarihler için sistem çalıştırın (en gerçekçi ama çok yavaş)
- Süre: 10-22 saat
- Gerçekçilik: Çok Yüksek

## 💡 Pratik Çözüm

En pratik çözüm: `backtest_walkforward.py` kullanmak. Bu script:
- Geçmiş IBKR fiyat verilerini çeker
- Bu verilerden skorları hesaplar
- Gerçekçi backtest yapar
- 1-2 saat içinde tamamlanır

Hangi yaklaşımı tercih edersiniz?



