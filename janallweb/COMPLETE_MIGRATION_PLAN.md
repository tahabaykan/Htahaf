# 🎯 JanAll Web - TAM MIGRATION PLANI

## 📊 UYGULAMA ANALİZİ

### Ana Özellikler (main_window.py - 21,000+ satır)

#### 1. **Bağlantılar ve Veri Akışı**
- ✅ Hammer Pro bağlantısı (WebSocket)
- ✅ IBKR TWS/Gateway bağlantısı (ib_insync)
- ✅ IBKR Native Client (TWS API)
- ✅ Live Data streaming
- ✅ ETF Data streaming (PFF, TLT, IEF, IEI, SPY)
- ✅ Market Data güncellemeleri (Bid, Ask, Last Price)
- ✅ Prev Close verileri

#### 2. **Ana Tablo Özellikleri**
- CSV yükleme (janalldata.csv - 97 sütun)
- Tüm sütunları göster
- Seçim checkbox'ları
- Sıralama (her sütuna göre)
- Sayfalama (15 hisse/sayfa)
- Skor hesaplamaları (Final_FB_skor, Final_SFS_skor)
- Benchmark hesaplamaları (C400, C425, C450, vb.)
- Live data ile skor güncellemeleri
- Mini450 görünümü
- Background data update (performans için)

#### 3. **Emir Yönetimi (OrderManager)**
- Bid Buy
- Front Buy
- Ask Buy
- Ask Sell
- Front Sell
- Bid Sell
- SoftFront Buy (LRPAN fiyatı ile koşullu)
- SoftFront Sell (LRPAN fiyatı ile koşullu)
- Lot bölme mantığı (0-399: direkt, 400+: 200'ün katları)
- Emir onay penceresi
- Trades.csv kaydetme

#### 4. **Lot Yönetimi**
- Manuel lot girişi
- %25, %50, %75, %100 butonları
- Avg Adv butonu
- Seçili hisselere lot uygulama

#### 5. **Mod Sistemi (ModeManager)**
- HAMPRO MOD (Hammer Pro)
- IBKR GUN MOD (IBKR Live)
- IBKR PED MOD (IBKR Paper)
- Mod değiştirme

#### 6. **Pozisyonlar (mypositions.py)**
- Hammer Pro'dan pozisyon çekme
- Pozisyon listesi (Symbol, Qty, Avg Cost, Current, PnL, AVG_ADV, MAXALW, SMI, Final FB, Final SFS)
- Sıralama
- Real-time güncellemeler

#### 7. **Emirler (myorders.py - 3 Sekmeli)**
- **Pending Sekmesi**: Bekleyen/Kısmi dolmuş emirler
- **Completed Sekmesi**: Tamamen dolmuş emirler
- **JDataLog Sekmesi**: Fill anında ETF verileriyle detaylı log
- Emir iptal etme
- Real-time güncellemeler

#### 8. **Take Profit Panelleri (take_profit_panel.py)**
- Take Profit Longs paneli
- Take Profit Shorts paneli
- Spread threshold (0.06, 0.09)
- Croplit işlemleri
- Pozisyon filtreleme
- Emir gönderme

#### 9. **Spreadkusu Panel (spreadkusu_panel.py)**
- Spread >= 0.20 olan hisseleri göster
- BBtot ve SAStot kolonları
- Mini450 verileri
- Otomatik güncelleme
- Emir gönderme

#### 10. **Port Adjuster (port_adjuster.py)**
- Portföy ayarlama
- 3 Step süreci:
  - Step 1: Pozisyon yükleme
  - Step 2: CSV yükleme
  - Step 3: Final FB/SFS hesaplama
  - Step 4: Grup ağırlıkları
  - Step 5: Tüm CSV işlemleri
- Exposure hesaplama
- Grup bazlı işlemler

#### 11. **ETF Panel (etf_panel.py)**
- ETF verileri (PFF, TLT, IEF, IEI, SPY)
- L1 streaming
- Prev close verileri
- Değişim hesaplamaları

#### 12. **BDATA/BEFDAY Export**
- BDATA Export (bdata_fills.json → bdata.csv)
- BEFDAY Export (bdata_snapshot.json → befday.csv)
- BDATA Clear
- Exception List yönetimi

#### 13. **Stock Data Manager**
- Stock data durumu
- Veri yönetimi

#### 14. **jdata Analiz (myjdata.py)**
- jdata analiz penceresi
- Sembol bazlı analiz

#### 15. **Top Ten / Bottom Ten**
- Top Ten Bid Buy
- Bottom Ten Ask Sell
- Grup bazlı emir gönderme

#### 16. **BEFHAM/BEFIB**
- BEFHAM export (befham.csv)
- BEFIB export (befibgun.csv, befibped.csv)
- Günlük kontrol

#### 17. **PSFALGO Robot**
- Otomatik trading robotu
- Pozisyon yönetimi
- Emir gönderme
- Exposure limitleri
- Controller kontrolleri
- Loop report
- Activity log
- Nfilled dosyası yönetimi

#### 18. **Benchmark Hesaplamaları**
- Benchmark formülleri (C400, C425, C450, vb.)
- ETF değişimleri
- Stabil benchmark hesaplama
- Benchmark shift

#### 19. **Skor Hesaplamaları**
- Final_FB_skor
- Final_SFS_skor
- Final_THG hesaplama
- Market data ile skor güncellemeleri

#### 20. **Diğer Özellikler**
- Portfolio Comparison
- Pressure Analyzer
- BGGG Analyzer
- Final THG Lot Distributor
- CSV Prev Close Manager
- Exception Manager
- Order Book Window

---

## 🚀 MIGRATION STRATEJİSİ

### Faz 1: Temel Altyapı ✅ (TAMAMLANDI)
- ✅ Flask Backend
- ✅ React Frontend
- ✅ WebSocket bağlantısı
- ✅ CSV yükleme
- ✅ Temel tablo

### Faz 2: Ana Tablo ve Emir Sistemi (ŞU AN BURADAYIZ)
- ⏳ Tüm sütunları göster (97 sütun) - YAPILDI
- ⏳ Seçim checkbox'ları - YAPILDI
- ⏳ Emir butonları (8 buton)
- ⏳ Lot yönetimi
- ⏳ Mod sistemi
- ⏳ Skor hesaplamaları
- ⏳ Benchmark hesaplamaları
- ⏳ Live data güncellemeleri

### Faz 3: Paneller ve Pencereler
- Pozisyonlar sayfası (detaylı)
- Emirler sayfası (3 sekmeli)
- Take Profit Longs/Shorts
- Spreadkusu
- Port Adjuster
- ETF Panel
- jdata Analiz

### Faz 4: Export ve Yönetim
- BDATA/BEFDAY Export
- Exception List
- Stock Data Manager
- BEFHAM/BEFIB

### Faz 5: Gelişmiş Özellikler
- PSFALGO Robot
- Top Ten / Bottom Ten
- Portfolio Comparison
- Pressure Analyzer
- BGGG Analyzer

---

## 📝 DETAYLI GÖREV LİSTESİ

### ADIM 1: Ana Tablo İyileştirmesi ✅
- [x] Tüm sütunları göster
- [x] Seçim checkbox'ları
- [ ] Sıralama (her sütuna göre)
- [ ] Sayfalama
- [ ] Skor hesaplamaları
- [ ] Benchmark hesaplamaları
- [ ] Live data güncellemeleri

### ADIM 2: Emir Sistemi
- [ ] OrderManager backend servisi
- [ ] 8 emir butonu (Bid Buy, Front Buy, Ask Buy, Ask Sell, Front Sell, Bid Sell, SoftFront Buy, SoftFront Sell)
- [ ] Lot bölme mantığı
- [ ] Emir onay penceresi
- [ ] Trades.csv kaydetme
- [ ] SoftFront koşulları (LRPAN fiyatı)

### ADIM 3: Lot Yönetimi
- [ ] Lot input
- [ ] %25, %50, %75, %100 butonları
- [ ] Avg Adv butonu
- [ ] Seçili hisselere lot uygulama

### ADIM 4: Mod Sistemi
- [ ] ModeManager backend servisi
- [ ] HAMPRO/IBKR mod değiştirme
- [ ] Mod durumu gösterimi

### ADIM 5: Pozisyonlar Sayfası
- [ ] Detaylı pozisyon listesi
- [ ] Sıralama
- [ ] Real-time güncellemeler
- [ ] Pozisyon detayları

### ADIM 6: Emirler Sayfası (3 Sekmeli)
- [ ] Pending sekmesi
- [ ] Completed sekmesi
- [ ] JDataLog sekmesi
- [ ] Emir iptal etme
- [ ] Real-time güncellemeler

### ADIM 7: Take Profit Panelleri
- [ ] Take Profit Longs paneli
- [ ] Take Profit Shorts paneli
- [ ] Spread threshold
- [ ] Croplit işlemleri

### ADIM 8: Spreadkusu
- [ ] Spread >= 0.20 filtreleme
- [ ] BBtot/SAStot kolonları
- [ ] Otomatik güncelleme

### ADIM 9: Port Adjuster
- [ ] 5 Step süreci
- [ ] Exposure hesaplama
- [ ] Grup bazlı işlemler

### ADIM 10: Diğer Paneller
- [ ] ETF Panel
- [ ] jdata Analiz
- [ ] Top Ten / Bottom Ten

### ADIM 11: Export ve Yönetim
- [ ] BDATA/BEFDAY Export
- [ ] Exception List
- [ ] Stock Data Manager

### ADIM 12: PSFALGO Robot
- [ ] Robot UI
- [ ] Otomatik trading
- [ ] Controller kontrolleri
- [ ] Loop report
- [ ] Activity log

---

## 🎯 ÖNCELİK SIRASI

1. **ADIM 1-4**: Ana tablo, emir sistemi, lot yönetimi, mod sistemi (Trading için kritik)
2. **ADIM 5-6**: Pozisyonlar ve Emirler (Takip için kritik)
3. **ADIM 7-9**: Take Profit, Spreadkusu, Port Adjuster (Strateji için önemli)
4. **ADIM 10-12**: Diğer özellikler (Tamamlama)

---

## 📦 BACKEND SERVİSLERİ

### Yeni Servisler Gerekli:
1. `order_service.py` - Emir yönetimi (mevcut, genişletilecek)
2. `mode_service.py` - Mod yönetimi
3. `score_service.py` - Skor hesaplamaları
4. `benchmark_service.py` - Benchmark hesaplamaları
5. `take_profit_service.py` - Take Profit işlemleri
6. `spreadkusu_service.py` - Spreadkusu işlemleri
7. `port_adjuster_service.py` - Port Adjuster işlemleri
8. `etf_service.py` - ETF verileri
9. `export_service.py` - Export işlemleri
10. `psfalgo_service.py` - PSFALGO robot

---

## 🎨 FRONTEND COMPONENTLERİ

### Yeni Componentler:
1. `OrderButtons.jsx` - Emir butonları
2. `LotManager.jsx` - Lot yönetimi
3. `ModeSelector.jsx` - Mod seçici
4. `ScoreCalculator.jsx` - Skor hesaplayıcı
5. `TakeProfitPanel.jsx` - Take Profit paneli
6. `SpreadkusuPanel.jsx` - Spreadkusu paneli
7. `PortAdjusterPanel.jsx` - Port Adjuster paneli
8. `ETFPanel.jsx` - ETF paneli
9. `JDataAnaliz.jsx` - jdata analiz
10. `PSFALGORobot.jsx` - PSFALGO robot

---

## ⚡ PERFORMANS OPTİMİZASYONLARI

- WebSocket ile real-time güncellemeler
- Backend'de caching
- Frontend'de virtual scrolling (büyük tablolar için)
- Lazy loading (paneller)
- Debouncing (skor hesaplamaları)

---

## 🔄 VERİ AKIŞI

```
Frontend (React) 
    ↕ WebSocket + REST API
Backend (Flask)
    ↕ WebSocket
Hammer Pro / IBKR
    ↕ Market Data
```

---

## 📅 TAHMİNİ SÜRE

- Faz 2: 2-3 gün (Ana tablo, emir sistemi)
- Faz 3: 3-4 gün (Paneller)
- Faz 4: 1-2 gün (Export)
- Faz 5: 2-3 gün (Gelişmiş özellikler)

**TOPLAM: ~8-12 gün** (Adım adım, test ederek)

---

## ✅ BAŞARILI MIGRATION KRİTERLERİ

1. Tüm özellikler çalışıyor
2. Tkinter'daki tüm fonksiyonlar web'de mevcut
3. Performans sorunsuz (single-threading sorunu çözüldü)
4. Real-time güncellemeler çalışıyor
5. Veri tutarlılığı korunuyor









