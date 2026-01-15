# 🎯 JanAll Web - Tam Entegrasyon Planı

## 📋 Durum
Kullanıcı janall uygulamasının **birebir aynısını** web'de istiyor. 20000+ satırlık main_window.py ve tüm modüller analiz edildi.

## ✅ Yapılacaklar

### 1. Tüm Butonlar ve Kontroller
- [x] Hammer Pro'ya Bağlan
- [ ] Live Data Başlat/Durdur
- [ ] Prev Close Çek
- [ ] BDATA Export
- [ ] BEFDAY Export
- [ ] BDATA Clear
- [ ] Exception List
- [ ] Stock Data Status
- [ ] Port Adjuster
- [ ] Pozisyonlarım
- [ ] Take Profit Longs
- [ ] Take Profit Shorts
- [ ] Spreadkusu
- [ ] Emirlerim (3 sekmeli)
- [ ] BEFHAM
- [ ] jdata Analiz
- [ ] Top Ten Bid Buy
- [ ] Bottom Ten Ask Sell
- [ ] mini450
- [ ] MAJBINA
- [ ] Psfalgo
- [ ] Compare It
- [ ] Lot Bölücü
- [ ] SRPAN
- [ ] Pressure Analiz
- [ ] BGGG
- [ ] Ticker Alerts
- [ ] ETF Cardinal
- [ ] TGFilterer

### 2. Emir Butonları
- [x] Bid Buy
- [x] Front Buy
- [x] Ask Buy
- [x] Ask Sell
- [x] Front Sell
- [x] Bid Sell
- [x] SoftFront Buy
- [x] SoftFront Sell

### 3. Lot Yönetimi
- [x] Lot Input
- [x] %25, %50, %75, %100
- [x] Avg Adv

### 4. Mod Sistemi
- [x] HAMPRO MOD
- [x] IBKR GUN MOD
- [x] IBKR PED MOD

### 5. CSV Dosya Butonları
20 adet janek_ssfinek CSV dosyası butonları

### 6. Paneller
- [ ] Take Profit Longs Panel
- [ ] Take Profit Shorts Panel
- [ ] Spreadkusu Panel
- [ ] Port Adjuster Panel
- [ ] Pozisyonlar Penceresi
- [ ] Emirler Penceresi (3 sekmeli: Pending, Completed, JDataLog)
- [ ] MAJBINA Filtreleme Penceresi
- [ ] mini450 Görünümü
- [ ] Psfalgo Robot Paneli
- [ ] Compare It Paneli
- [ ] SRPAN Analiz Paneli
- [ ] Pressure Analiz Paneli
- [ ] BGGG Analiz Paneli
- [ ] Ticker Alerts Paneli
- [ ] ETF Cardinal Paneli
- [ ] TGFilterer Paneli
- [ ] Exception List Penceresi
- [ ] Stock Data Status Penceresi
- [ ] jdata Analiz Penceresi
- [ ] ETF Panel

### 7. Tablo Özellikleri
- [ ] Tüm CSV kolonlarını göster (97 kolon)
- [ ] Sıralama (her kolona göre)
- [ ] Sayfalama (15 hisse/sayfa)
- [ ] Checkbox seçimi
- [ ] Çift tıklama (OrderBook aç)
- [ ] Real-time güncellemeler
- [ ] Skor hesaplamaları
- [ ] Benchmark hesaplamaları

### 8. Backend API Endpoint'leri
- [ ] Tüm butonlar için endpoint'ler
- [ ] Tüm paneller için endpoint'ler
- [ ] CSV yükleme ve işleme
- [ ] Emir gönderme (lot bölme mantığı ile)
- [ ] SoftFront koşulları (LRPAN fiyatı)
- [ ] Benchmark hesaplamaları
- [ ] Skor hesaplamaları
- [ ] Pozisyon yönetimi
- [ ] Emir yönetimi
- [ ] BDATA/BEFDAY export
- [ ] Exception list yönetimi

## 🚀 Uygulama Stratejisi

Bu çok büyük bir iş. Adım adım yapacağız:

1. **Faz 1**: Tüm butonları HTML'e ekle (şimdi)
2. **Faz 2**: Backend API'lerini genişlet
3. **Faz 3**: Panelleri ekle (modal/window olarak)
4. **Faz 4**: Tablo özelliklerini tamamla
5. **Faz 5**: Test ve düzeltmeler

## ⚠️ Notlar

- Tüm özellikler birebir aynı olacak
- Tkinter mantığı korunacak
- Web teknolojileri ile uyumlu hale getirilecek
- Performans optimizasyonları yapılacak









