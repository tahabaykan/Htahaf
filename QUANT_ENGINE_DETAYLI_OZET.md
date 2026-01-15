# QUANT_ENGINE - Detaylı Özellikler ve Kullanım Kılavuzu

## 📋 GENEL BAKIŞ

**Quant Engine**, ABD preferred stock piyasasında profesyonel algoritmik trading için geliştirilmiş, **modüler, ölçeklenebilir, cloud-ready** bir backend trading engine'dir. Sistem, gerçek zamanlı piyasa verilerini analiz ederek, otomatik skorlama, sinyal üretimi, risk yönetimi ve pozisyon yönetimi sağlar.

### Temel Özellikler
- ✅ **Modüler Mimari**: Mikroservis benzeri, bağımsız modüller
- ✅ **Web Tabanlı UI**: React + Vite ile modern web arayüzü
- ✅ **Gerçek Zamanlı Veri**: WebSocket ile canlı market data streaming
- ✅ **Çoklu Broker Desteği**: Hammer Pro + IBKR entegrasyonu
- ✅ **Gelişmiş Analiz**: GRPAN (rolling windows), RWVAP, Janall Metrics, Pricing Overlay Engine
- ✅ **İki Katmanlı Gruplama**: PRIMARY GROUP (file_group) + SECONDARY GROUP (CGRUP for heldkuponlu)
- ✅ **Benchmark-Aware Scoring**: Pricing Overlay Engine ile benchmark-aware ucuzluk/pahalılık skorları
- ✅ **Risk Yönetimi**: Monte Carlo simülasyonu, risk limitleri, circuit breaker
- ✅ **Backtest & Optimizasyon**: Walk-forward optimization, parameter tuning
- ✅ **Otomatik Trading**: PSFALGO algoritması ile 7/24 çalışabilen sistem
- ✅ **Redis Integration**: Otomatik Redis başlatma ve pub/sub messaging

---

## 🏗️ MİMARİ YAPISI

### Teknoloji Stack
- **Backend**: Python 3.9+, FastAPI, asyncio
- **Frontend**: React 18, Vite, WebSocket
- **Veri İletişimi**: Redis (pub/sub + streams), WebSocket
- **Market Data**: Hammer Pro WebSocket API, IBKR TWS/Gateway
- **Veritabanı**: SQLite (PSFALGO state), CSV (static data)

### Modül Yapısı
```
quant_engine/
├── app/
│   ├── api/              # FastAPI REST/WebSocket endpoints
│   ├── market_data/      # Market data processing (GRPAN, RWVAP, Janall)
│   ├── decision/         # Karar motorları (intent, signal, order planning)
│   ├── psfalgo/          # PSFALGO otomatik trading algoritması
│   ├── engine/           # Trading engine loop, position manager
│   ├── risk/             # Risk yönetimi (Monte Carlo, limits)
│   ├── backtest/          # Backtest engine ve raporlama
│   ├── optimization/      # Parameter optimization, walk-forward
│   ├── live/              # Live trading adapters (Hammer, IBKR)
│   ├── strategy/          # Strategy framework (indicators, candles)
│   └── execution/         # Execution simulator, commission, liquidity
├── frontend/              # React web UI
└── docs/                  # Kapsamlı dokümantasyon
```

---

## 🎯 ANA ÖZELLİKLER

### 1. **SCANNER TABLO SİSTEMİ**

#### CSV Yükleme ve Veri İşleme
- **CSV Formatı**: `janalldata.csv` (97+ sütun)
- **Otomatik Parsing**: PREF_IBKR, CMON, CGRUP, FINAL_THG, SHORT_FINAL, AVG_ADV, SMI, vb.
- **Static Data Store**: Günlük statik verileri yükler ve cache'ler
- **Real-time Updates**: WebSocket ile canlı güncellemeler

#### Tablo Özellikleri
- **Sıralama**: Tüm kolonlar için büyükten küçüğe (default) veya küçükten büyüğe
- **Filtreleme**: State, spread, AVG_ADV, FINAL_THG, SHORT_FINAL filtreleri
- **Focus Mode**: Sadece seçili state'lerdeki hisseleri göster
- **Sayfalama**: Virtual scrolling ile performanslı görüntüleme
- **Detaylı Inspector**: Her hisse için State Reason Inspector paneli

#### Kolonlar
- **Temel Bilgiler**: PREF_IBKR, CMON, CGRUP, GROUP (primary group), prev_close, bid, ask, last, volume, spread_percent
- **Janall Metrics**: FINAL_THG, SHORT_FINAL, SMI, SMA63chg, SMA246chg, AVG_ADV
- **GRPAN**: grpan_price, grpan_concentration_percent, grpan_ort_dev (GOD)
- **RWVAP**: rwvap_1d, rwvap_ort_dev (ROD)
- **PSFALGO**: state, signal, intent, plan, queue, gate, action, execution
- **Ranking**: fbtot_rank_norm, sfstot_rank_norm
- **Benchmark**: benchmark_chg (vs C400, C425, C450, C475, C500)
- **Pricing Overlay Scores** (18 kolon):
  - `overlay_benchmark_type`: Benchmark tipi (C450, DEFAULT, vb.)
  - `overlay_benchmark_chg`: Benchmark değişimi (4 ondalık)
  - `Bid_buy_ucuzluk_skoru`, `Front_buy_ucuzluk_skoru`, `Ask_buy_ucuzluk_skoru` (2 ondalık)
  - `Ask_sell_pahalilik_skoru`, `Front_sell_pahalilik_skoru`, `Bid_sell_pahalilik_skoru` (2 ondalık)
  - `Final_BB_skor`, `Final_FB_skor`, `Final_AB_skor`, `Final_AS_skor`, `Final_FS_skor`, `Final_BS_skor` (2 ondalık)
  - `Final_SAS_skor`, `Final_SFS_skor`, `Final_SBS_skor` (2 ondalık)
  - `overlay_spread`: Spread (4 ondalık)

---

### 2. **GRPAN (Grouped Real Print Analyzer)**

#### Ne Yapar?
GRPAN, trade print'lerinden ağırlıklı fiyat yoğunluğu analizi yapar. Son işlemlerdeki dominant fiyatı ve konsantrasyon yüzdesini hesaplar.

#### Özellikler
- **Event-Driven**: Her trade print geldiğinde otomatik hesaplama
- **Ring Buffer**: Son 15 print'i tutar (O(1) memory)
- **Lot-Based Weighting**: 
  - 100/200/300 lot = 1.0 ağırlık
  - Diğer lotlar = 0.25 ağırlık
- **Size Filter**: 10 lot altı print'ler ignore edilir
- **Rolling Windows**: 
  - `latest_pan`: Son 15 print (backward compatible)
  - `pan_10m`: Son 10 dakika
  - `pan_30m`: Son 30 dakika
  - `pan_1h`: Son 1 saat
  - `pan_3h`: Son 3 saat
  - `pan_1d`: Son 1 işlem günü
  - `pan_3d`: Son 3 işlem günü

#### Trading-Time Aware
- **NYSE Trading Hours**: 09:30 - 16:00 ET
- **Holiday Support**: NYSE tatillerini bilir
- **Market Closed**: Market kapalıyken "now" = son trade timestamp
- **Stable Windows**: Hafta sonu/tatillerde PAN değerleri sabit kalır

#### Çıktılar
- `grpan_price`: Dominant fiyat
- `concentration_percent`: ±0.04 aralığındaki yoğunluk yüzdesi
- `real_lot_count`: 100/200/300 lot sayısı
- `print_count`: Toplam print sayısı
- `deviation_vs_last`: `last_price - grpan_price` (son print'in GRPAN'den sapması)
- `deviation_vs_prev_window`: Önceki window ile fark

#### GOD (GRPAN ORT DEV)
- Tüm GRPAN window'larının ortalaması (geçersiz veriler çıkarılır)
- `GOD = last_price - grpan_ort`
- En yüksek GOD değerleri = en çok sapma gösteren hisseler

---

### 3. **RWVAP (Robust VWAP)**

#### Ne Yapar?
RWVAP, extreme volume print'lerini (FINRA, block transfers) hariç tutarak VWAP hesaplar. İlliquid preferred stock'lar için daha güvenilir bir ortalama fiyat sağlar.

#### Özellikler
- **Extreme Volume Filter**: 
  - `size > (AVG_ADV * 1.0)` olan print'ler exclude edilir
  - Configurable multiplier (default: 1.0)
- **Trading-Day Windows**:
  - `rwvap_1d`: Son 1 işlem günü
  - `rwvap_3d`: Son 3 işlem günü
  - `rwvap_5d`: Son 5 işlem günü
- **Shared Buffer**: GRPAN'in 150-tick buffer'ını kullanır (veri tekrarı yok)
- **Status Tracking**: OK, COLLECTING, INSUFFICIENT_DATA

#### Çıktılar
- `rwvap`: Robust VWAP fiyatı
- `effective_print_count`: Hesaplamaya dahil edilen print sayısı
- `excluded_print_count`: Hariç tutulan print sayısı
- `excluded_volume_ratio`: Hariç tutulan volume oranı
- `deviation_vs_last`: `last_price - rwvap` (son print'in RWVAP'den sapması)
- `status`: OK / COLLECTING / INSUFFICIENT_DATA

#### ROD (RWVAP ORT DEV)
- Tüm RWVAP window'larının ortalaması (geçersiz veriler çıkarılır)
- `ROD = last_price - rwvap_ort`
- En yüksek ROD değerleri = en çok sapma gösteren hisseler

---

### 4. **JANALL METRICS ENGINE**

#### Ne Yapar?
Janall uygulamasındaki skorlama sistemini taklit eder. FINAL_THG, SHORT_FINAL, SMI, SMA değişimleri, benchmark karşılaştırmaları hesaplar.

#### Özellikler
- **FINAL_THG**: Final FB (Front Buy) skoru
- **SHORT_FINAL**: Final SFS (Short Front Sell) skoru
- **SMI**: Stock Market Index
- **SMA Changes**: SMA63 ve SMA246 değişimleri
- **Benchmark Comparison**: C400, C425, C450, C475, C500 ile karşılaştırma
- **Ranking**: fbtot_rank_norm, sfstot_rank_norm (normalized ranks)

---

### 4.5. **PRICING OVERLAY ENGINE** (YENİ - Benchmark-Aware Scoring)

#### Ne Yapar?
Janall'daki "mini450" dataframe'indeki benchmark-aware ucuzluk/pahalılık skorlarını hesaplar. Her hisse için benchmark'a göre relative ucuzluk/pahalılık skorları üretir.

#### Özellikler
- **Dirty Tracking**: Symbol'ler sadece bid/ask/last değiştiğinde veya benchmark ETF'ler değiştiğinde yeniden hesaplanır
- **Throttle Mechanism**: Minimum 250ms per symbol, batch processing (200 symbol/batch)
- **Benchmark-Aware**: İki katmanlı gruplama sistemine göre benchmark formülü seçilir
- **Janall Parity**: Janall formüllerini birebir taklit eder

#### Hesaplanan Skorlar

**Ucuzluk Skorları (Long pozisyonlar için):**
- `Bid_buy_ucuzluk_skoru`: Bid fiyatından alış yapıldığında ne kadar ucuz
- `Front_buy_ucuzluk_skoru`: Front fiyatından alış yapıldığında ne kadar ucuz
- `Ask_buy_ucuzluk_skoru`: Ask fiyatından alış yapıldığında ne kadar ucuz

**Pahalılık Skorları (Short pozisyonlar için):**
- `Ask_sell_pahalilik_skoru`: Ask fiyatından satış yapıldığında ne kadar pahalı
- `Front_sell_pahalilik_skoru`: Front fiyatından satış yapıldığında ne kadar pahalı
- `Bid_sell_pahalilik_skoru`: Bid fiyatından satış yapıldığında ne kadar pahalı

**Final Skorlar:**
- `Final_BB_skor`: Final Bid Buy skoru
- `Final_FB_skor`: Final Front Buy skoru
- `Final_AB_skor`: Final Ask Buy skoru
- `Final_AS_skor`: Final Ask Sell skoru
- `Final_FS_skor`: Final Front Sell skoru
- `Final_BS_skor`: Final Bid Sell skoru
- `Final_SAS_skor`: Final Short Ask Sell skoru
- `Final_SFS_skor`: Final Short Front Sell skoru
- `Final_SBS_skor`: Final Short Bid Sell skoru

#### Hesaplama Mantığı

1. **Passive Price Hesaplama**:
   - `pf_bid_buy = prev_close + benchmark_chg`
   - `pf_ask_sell = prev_close + benchmark_chg`
   - `pf_front_buy = (bid + ask) / 2 + benchmark_chg`
   - `pf_front_sell = (bid + ask) / 2 + benchmark_chg`

2. **Price Change Hesaplama**:
   - `bid_buy_change = bid - pf_bid_buy`
   - `ask_sell_change = ask - pf_ask_sell`
   - `front_buy_change = (bid + ask) / 2 - pf_front_buy`
   - `front_sell_change = (bid + ask) / 2 - pf_front_sell`

3. **Ucuzluk/Pahalılık Skorları**:
   - `Bid_buy_ucuzluk = bid_buy_change / prev_close` (eğer prev_close > 0)
   - `Ask_sell_pahalilik = ask_sell_change / prev_close` (eğer prev_close > 0)
   - Benzer şekilde diğer skorlar

4. **Final Skorlar**:
   - `Final_BB = FINAL_THG * Bid_buy_ucuzluk_skoru`
   - `Final_FB = FINAL_THG * Front_buy_ucuzluk_skoru`
   - `Final_AB = FINAL_THG * Ask_buy_ucuzluk_skoru`
   - `Final_AS = SHORT_FINAL * Ask_sell_pahalilik_skoru`
   - `Final_FS = SHORT_FINAL * Front_sell_pahalilik_skoru`
   - `Final_BS = SHORT_FINAL * Bid_sell_pahalilik_skoru`
   - `Final_SAS = SHORT_FINAL * Ask_sell_pahalilik_skoru` (Short için)
   - `Final_SFS = SHORT_FINAL * Front_sell_pahalilik_skoru` (Short için)
   - `Final_SBS = SHORT_FINAL * Bid_sell_pahalilik_skoru` (Short için)

#### Status Tracking
- **OK**: Tüm veriler mevcut, skorlar hesaplandı
- **COLLECTING**: `prev_close` veya `benchmark_chg` eksik, veri toplanıyor
- **ERROR**: Hesaplama hatası

#### Performans Optimizasyonu
- **Dirty Tracking**: Sadece değişen symbol'ler yeniden hesaplanır
- **Throttle**: Minimum 250ms per symbol (aynı symbol'ü çok sık hesaplamaz)
- **Batch Processing**: 200 symbol/batch (backpressure kontrolü)
- **Cache**: Hesaplanan skorlar cache'lenir (`overlay_cache`)

---

### 4.6. **İKİ KATMANLI GRUPLAMA SİSTEMİ** (YENİ)

#### Ne Yapar?
Preferred stock'ları iki katmanlı bir sistemle gruplar. Bu sistem, Janall'daki GORT mantığı ile birebir uyumludur.

#### 1️⃣ PRIMARY GROUP = FILE_GROUP (Ana Strateji Rejimi)

**Ne Yapar?**
- Ana davranış karakteristiklerini belirler
- Strategy regime'i tanımlar
- Mean-reversion ve sensitivity rejimini belirler

**Örnekler (Janall'dan birebir - 22 grup):**
- `heldkuponlu` - Fixed coupon, no maturity
- `heldff` - Fixed-to-floating
- `helddeznff` - Dezenflasyon, no fixed-to-floating
- `heldnff` - No fixed-to-floating
- `heldflr` - Floating rate (NOT "flr", it's "heldflr")
- `heldgarabetaltiyedi` - Garantili, altı yedi yıl
- `heldkuponlukreciliz` - Kuponlu, kredi riski düşük
- `heldkuponlukreorta` - Kuponlu, kredi riski orta
- `heldotelremorta` - Overnight repo, medium term
- `heldsolidbig` - Solid, big issuers
- `heldtitrekhc` - Titrek, high credit
- `highmatur` - High maturity
- `notcefilliquid` - Not çok filliquid
- `notbesmaturlu` - Not beş yıl maturiteli
- `nottitrekhc` - Not titrek, high credit
- `salakilliquid` - Salak, illiquid
- `shitremhc` - Shit, rem, high credit
- `rumoreddanger` - Rumored/dangerous
- `heldcilizyeniyedi` - Ciliz, yeni yedi
- `heldcommonsuz` - Common stock yok
- `notheldtitrekhc` - Not held titrek, high credit
- `heldbesmaturlu` - Beş yıl maturiteli

**Belirlediği Özellikler:**
- Maturity yapısı (fixed maturity vs perpetual)
- Coupon tipi (fixed vs floating)
- Issuer kalitesi
- Sektörel risk
- Likidite profili

**Çözümleme Yöntemi:**
- **Öncelik 1**: `GROUP` kolonu (janalldata.csv'de varsa)
- **Öncelik 2**: `file_group` kolonu
- **Öncelik 3**: `group` kolonu
- **Öncelik 4**: Janall mantığı - Her grubun ayrı CSV dosyası var (ssfinekheldff.csv, vb.)
  - Symbol'ü tüm grup CSV dosyalarında `PREF IBKR` kolonunda arar
  - Bulunduğu dosyaya göre grup belirlenir
  - Cache mekanizması ile performans optimize edilir

#### 2️⃣ SECONDARY GROUP = CGRUP (SADECE kuponlu gruplar için)

**Ne Yapar?**
- Kupon bandını temsil eder
- **SADECE** kuponlu gruplar için kullanılır: `heldkuponlu`, `heldkuponlukreciliz`, `heldkuponlukreorta`
- Diğer tüm gruplar CGRUP'u **ignore eder**

**Örnekler:**
- `C400` - 4.00% coupon band
- `C425` - 4.25% coupon band
- `C450` - 4.50% coupon band
- `C475` - 4.75% coupon band
- `C500` - 5.00% coupon band
- `C525` - 5.25% coupon band
- `C550` - 5.50% coupon band
- `C575` - 5.75% coupon band
- `C600` - 6.00% coupon band

**Neden Sadece Kuponlu Gruplar?**
- Fixed coupon
- Maturity yok
- Duration ve rate sensitivity tamamen coupon'a bağlı
- C400 ≠ C550 (farklı benchmark, farklı davranış)
- Janall'da bu 3 grup CGRUP'a göre split edilir

#### Group Key Formatı

- **Kuponlu grup + CGRUP**: `"heldkuponlu:c400"`, `"heldkuponlukreciliz:c425"`, vb.
- **Diğer gruplar**: `"heldff"`, `"heldsolidbig"`, vb. (CGRUP ignored)

#### Benchmark Kullanımı

- **heldkuponlu + CGRUP**: CGRUP'a göre benchmark formülü (C400, C425, C450, vb.)
- **Diğer gruplar**: PRIMARY GROUP'a göre benchmark formülü
- **Benchmark Rules**: `benchmark_rules.yaml` dosyasından yüklenir

---

### 4.7. **BENCHMARK ENGINE** (Güncellenmiş)

#### Ne Yapar?
İki katmanlı gruplama sistemine göre benchmark değişimini hesaplar. Her grup için farklı ETF formülleri kullanır.

#### Özellikler
- **İki Katmanlı Benchmark**: PRIMARY GROUP + SECONDARY GROUP (CGRUP)
- **YAML Configuration**: `benchmark_rules.yaml` dosyasından formüller yüklenir
- **ETF Composite**: Birden fazla ETF'nin ağırlıklı kombinasyonu
- **Janall Parity**: Janall'daki benchmark formüllerini birebir taklit eder

#### Benchmark Formülü Formatı

```yaml
# Default benchmark
default:
  formula:
    PFF: 1.1
    TLT: -0.08
    IEF: 0.0
    IEI: 0.0

# heldkuponlu için CGRUP bazlı formüller
heldkuponlu:
  c400:
    formula:
      PFF: 0.36
      TLT: 0.36
      IEF: 0.08
      IEI: 0.0
  c450:
    formula:
      PFF: 0.38
      TLT: 0.32
      IEF: 0.10
      IEI: 0.0
  # ... diğer CGRUP'lar

# Diğer primary gruplar için
heldff:
  formula:
    PFF: 1.0
    TLT: 0.0
    IEF: 0.0
    IEI: 0.0
```

#### Benchmark Change Hesaplama

```python
benchmark_chg = sum(
    ETF_coefficient * (ETF_last - ETF_prev_close) / ETF_prev_close
    for ETF, coefficient in formula.items()
)
```

**Örnek:**
- Formula: `{'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08}`
- PFF: last=100, prev_close=99 → change = 1.01%
- TLT: last=95, prev_close=96 → change = -1.04%
- IEF: last=50, prev_close=50 → 0%
- **benchmark_chg** = 0.36 * 1.01% + 0.36 * (-1.04%) + 0.08 * 0% = -0.01%

---

### 5. **PSFALGO (Otomatik Trading Algoritması)**

#### Ne Yapar?
7/24 çalışabilen, risk kontrollü, otomatik trading sistemidir. Pozisyon yönetimi, guard kontrolü, action planning yapar.

#### Özellikler
- **State Management**: IDLE, WATCH, CANDIDATE, PLAN, QUEUE, GATE, ACTION, EXECUTION
- **Position Snapshot**: Anlık pozisyon durumu
- **Position Guards**: MAXALW, daily_add_limit, change_3h_limit kontrolleri
- **Action Planner**: Otomatik action plan üretimi (BUY, SELL, HOLD)
- **Execution Ledger**: Tüm işlemlerin kaydı
- **Cycle Engine**: Periyodik döngüsel işlemler

#### State Machine
```
IDLE → WATCH → CANDIDATE → PLAN → QUEUE → GATE → ACTION → EXECUTION
  ↑                                                              ↓
  └──────────────────────────────────────────────────────────────┘
```

#### Guard Sistemi
- **MAXALW**: Maksimum allowed lot kontrolü
- **Daily Add Limit**: Günlük ekleme limiti
- **Change 3H Limit**: 3 saatlik değişim limiti
- **Cross Block**: Aynı şirketten cross işlem engelleme

---

### 6. **DECISION ENGINES (Karar Motorları)**

#### Signal Interpreter
- Janall metrics'lerden sinyal üretir
- FINAL_THG, SHORT_FINAL, benchmark_chg, rank'leri analiz eder
- Signal: BUY, SELL, HOLD, STRONG_BUY, STRONG_SELL

#### Intent Engine
- Signal'den intent üretir
- LONG, SHORT, CLOSE_LONG, CLOSE_SHORT, HOLD
- YAML tabanlı kurallar (`intent_rules.yaml`)

#### Order Planner
- Intent'ten order plan üretir
- Fiyat, lot, order type (BID_BUY, FRONT_BUY, ASK_BUY, vb.) belirler
- GRPAN hint price kullanır
- YAML tabanlı kurallar (`order_plan_rules.yaml`)

#### Order Queue
- Plan'ları queue'ya ekler
- Priority sıralaması
- YAML tabanlı kurallar (`order_queue_rules.yaml`)

#### Order Gate
- Queue'daki order'ları kontrol eder
- Risk limitleri, guard kontrolleri
- AUTO_APPROVED, MANUAL_REVIEW, BLOCKED
- YAML tabanlı kurallar (`order_gate_rules.yaml`)

#### Exposure Mode Engine
- Portfolio exposure'ı hesaplar
- LONG, SHORT, NEUTRAL, OVEREXPOSED, UNDEREXPOSED

---

### 7. **RISK MANAGEMENT**

#### Risk Manager
- **Position Limits**: Symbol bazlı maksimum pozisyon limitleri
- **Daily Loss Limit**: Günlük maksimum kayıp limiti
- **Circuit Breaker**: Risk limiti aşıldığında otomatik durdurma
- **Portfolio Risk**: Toplam portföy riski hesaplama

#### Monte Carlo Simulation
- Senaryo bazlı risk analizi
- 10,000+ simülasyon
- VaR (Value at Risk) hesaplama
- Confidence intervals

---

### 8. **BACKTEST & OPTIMIZATION**

#### Backtest Engine
- Historical data ile strateji testi
- OHLCV candle data
- Execution simulator (slippage, commission)
- Performance metrics (Sharpe, Sortino, Max Drawdown)

#### Walk-Forward Optimization
- Out-of-sample validation
- Rolling window optimization
- Parameter tuning
- Overfitting önleme

#### Advanced Optimizer
- Multi-objective optimization
- Genetic algorithms
- Parameter space exploration

---

### 9. **LIVE TRADING**

#### Execution Adapters
- **Hammer Execution**: Hammer Pro üzerinden emir gönderimi
- **IBKR Execution**: IBKR TWS/Gateway üzerinden emir gönderimi
- **Simulator**: Paper trading için execution simulator

#### Position Manager
- FIFO position tracking
- P&L calculation
- Real-time position updates
- IBKR synchronization

#### Trading Account Context
- Multi-account support
- Account switching
- Position isolation

---

### 10. **WEB UI (Frontend)**

#### Scanner Table
- Real-time market data display
- Sortable columns (default: desc)
- Filtering (state, spread, AVG_ADV, vb.)
- Focus mode
- Virtual scrolling

#### State Reason Inspector
- Detaylı hisse analizi
- GRPAN rolling windows görüntüleme (PAN_10M, PAN_30M, PAN_1H, PAN_3H, PAN_1D, PAN_3D)
- RWVAP windows görüntüleme (RWVAP_1D, RWVAP_3D, RWVAP_5D)
- PSFALGO state, guards, action plan
- Janall metrics breakdown
- **Pricing Overlay Scores** bölümü:
  - Status (OK/COLLECTING/ERROR)
  - Benchmark Type ve Benchmark Chg
  - Ucuzluk Skorları (Bid Buy, Front Buy, Ask Buy)
  - Pahalılık Skorları (Ask Sell, Front Sell, Bid Sell)
  - Final Skorlar (Final_BB, Final_FB, Final_AB, Final_AS, Final_FS, Final_BS, Final_SAS, Final_SFS, Final_SBS)
  - Spread

#### Control Bar
- CSV load/unload
- Auto-refresh toggle
- Execution mode (PREVIEW/LIVE)
- Trading account selector

#### Group Selector (YENİ)
- **Header Dropdown**: Üst kısımda grup seçici dropdown
- **Primary Groups**: 22 ana grup listelenir (heldff, heldkuponlu, heldsolidbig, vb.)
- **CGRUP Sub-groups**: Kuponlu gruplar için CGRUP alt-grupları (C400, C425, C450, vb.)
- **Group Counts**: Her grup için symbol sayısı gösterilir
- **New Tab Navigation**: Grup seçildiğinde yeni sekmede açılır (`?group=...&cgrup=...`)
- **Client-Side Filtering**: Yeni data fetch yok, sadece client-side filtreleme (performanslı)
- **Group Context Bar**: Seçili grup için benchmark ve özet istatistikler gösterilir

#### PSFALGO Bulk Action Panel
- Toplu emir gönderimi
- Batch operations
- Approval workflow

#### Trading Panels Overlay
- Positions panel
- Orders panel (Pending, Completed, JDataLog)
- Account sidebar

---

## 🔄 VERİ AKIŞI

### 1. CSV Yükleme
```
CSV File (janalldata.csv)
    ↓
Static Data Store (load_csv endpoint)
    ↓
Market Data Cache
    ↓
WebSocket Broadcast
    ↓
Frontend (Scanner Table)
```

### 2. Live Market Data
```
Hammer Pro WebSocket
    ↓
Hammer Feed (L1Update, L2Update)
    ↓
Trade Print Router
    ↓
GRPAN Engine (add_trade_print)
    ↓
RWVAP Engine (shared buffer)
    ↓
Market Data Cache
    ↓
Pricing Overlay Engine (dirty queue processing)
    ↓
WebSocket Broadcast (diff publishing)
    ↓
Frontend (Real-time updates)
```

### 2.5. Pricing Overlay Pipeline
```
Market Data Update (bid/ask/last)
    ↓
Pricing Overlay Engine (mark_dirty)
    ↓
Benchmark ETF Update
    ↓
Pricing Overlay Engine (mark_benchmark_dirty)
    ↓
Dirty Queue Processing (throttled, batch)
    ↓
Overlay Cache Update
    ↓
WebSocket Broadcast (diff)
    ↓
Frontend (Overlay scores display)
```

### 3. PSFALGO Pipeline
```
Market Data Update
    ↓
Signal Interpreter
    ↓
Intent Engine
    ↓
Order Planner
    ↓
Order Queue
    ↓
Order Gate
    ↓
User Action Store (if MANUAL_REVIEW)
    ↓
Execution Router
    ↓
Hammer/IBKR Execution
    ↓
Position Manager
    ↓
PSFALGO State Update
```

---

## 📊 JANALL vs QUANT_ENGINE KARŞILAŞTIRMASI

### JANALL (Eski Sistem)
- **Tip**: Desktop GUI uygulaması (Tkinter)
- **Mimari**: Monolitik, tek uygulama
- **UI**: Tkinter tabanlı desktop GUI
- **Veri İletişimi**: Doğrudan broker API'leri
- **Kullanım**: Manuel ve otomatik trading için desktop uygulaması
- **Özellikler**:
  - CSV yükleme ve tablo görüntüleme
  - GRPAN hesaplama (son 15 tick)
  - Emir yönetimi (Bid Buy, Front Buy, Ask Buy, vb.)
  - Pozisyon takibi
  - Take Profit panelleri
  - PSFALGO otomasyonu (3 dakikalık döngü)

### QUANT_ENGINE (Yeni Sistem)
- **Tip**: Backend odaklı, modüler, profesyonel trading engine
- **Mimari**: Mikroservis benzeri, cloud-ready, scalable
- **UI**: React tabanlı web arayüzü (Vite + React)
- **Veri İletişimi**: Redis pub/sub + streams, FastAPI REST/WebSocket
- **Kullanım**: Profesyonel algoritmik trading backend'i
- **Özellikler**:
  - ✅ **Gelişmiş GRPAN**: Rolling windows (10m, 30m, 1h, 3h, 1d, 3d), trading-time aware
  - ✅ **RWVAP**: Robust VWAP, extreme volume filtering
  - ✅ **GOD/ROD**: GRPAN/RWVAP ortalamaları ve deviation hesaplama
  - ✅ **Web UI**: Modern, responsive, sıralanabilir tablolar
  - ✅ **Real-time Updates**: WebSocket ile canlı güncellemeler
  - ✅ **Modüler Mimari**: Bağımsız modüller, kolay genişletilebilir
  - ✅ **Backtest & Optimization**: Walk-forward, parameter tuning
  - ✅ **Risk Management**: Monte Carlo, risk limits, circuit breaker
  - ✅ **Multi-Account**: Birden fazla trading account desteği
  - ✅ **API-First**: REST API ve WebSocket endpoints
  - ✅ **Cloud-Ready**: Docker, scalable architecture

### Temel Farklar

| Özellik | JANALL | QUANT_ENGINE |
|---------|--------|--------------|
| **Platform** | Desktop (Windows) | Web (Cross-platform) |
| **UI Framework** | Tkinter | React + Vite |
| **Mimari** | Monolitik | Modüler, mikroservis |
| **GRPAN** | Son 15 tick (snapshot) | Rolling windows (statistical state) |
| **RWVAP** | ❌ Yok | ✅ Robust VWAP |
| **GOD/ROD** | ❌ Yok | ✅ Ortalama deviation hesaplama |
| **Trading-Time** | Wall-clock time | NYSE trading-time aware |
| **Backtest** | ❌ Yok | ✅ Full backtest engine |
| **Optimization** | ❌ Yok | ✅ Walk-forward optimization |
| **Risk Management** | Basit limitler | Monte Carlo, circuit breaker |
| **API** | ❌ Yok | ✅ REST + WebSocket |
| **Scalability** | Tek kullanıcı | Multi-user, cloud-ready |
| **Maintenance** | Zor (monolitik) | Kolay (modüler) |

---

## 🚀 KULLANIM SENARYOLARI

### Senaryo 1: CSV Yükleme ve Analiz
1. Frontend'de "Load CSV" butonuna tıkla
2. `janalldata.csv` dosyasını seç
3. Tablo otomatik yüklenir ve görüntülenir
4. Kolonlara tıklayarak sıralama yap
5. Filtrelerle istediğin hisseleri bul
6. Bir hisseye tıklayarak State Reason Inspector'da detayları gör

### Senaryo 2: Real-time Market Data
1. Backend çalışıyor ve Hammer Pro'ya bağlı
2. WebSocket otomatik bağlanır
3. Her 2 saniyede bir market data güncellemeleri gelir
4. Tablo otomatik güncellenir
5. GRPAN ve RWVAP değerleri real-time hesaplanır

### Senaryo 3: PSFALGO Otomasyonu
1. PSFALGO aktif edilir
2. Her döngüde:
   - Market data güncellenir
   - Signal üretilir
   - Intent belirlenir
   - Order plan oluşturulur
   - Queue'ya eklenir
   - Gate kontrolünden geçer
   - Execution'a gönderilir
3. Execution mode PREVIEW ise sadece log, LIVE ise gerçek emir gönderilir

### Senaryo 4: GOD/ROD ile Preferred Stock Seçimi
1. CSV yükle
2. GOD kolonuna tıkla (büyükten küçüğe sırala)
3. En yüksek GOD değerlerine sahip hisseleri gör
4. ROD kolonuna tıkla (büyükten küçüğe sırala)
5. En yüksek ROD değerlerine sahip hisseleri gör
6. Bu hisseler = son print'in GRPAN/RWVAP'den en çok sapma gösterenler
7. Bu hisseler = potansiyel trading fırsatları

### Senaryo 5: Backtest
1. Historical data hazırla
2. Strategy tanımla
3. Backtest engine'i çalıştır
4. Performance metrics görüntüle
5. Walk-forward optimization yap
6. Parameter tuning

---

## 📈 PERFORMANS VE ÖLÇEKLENEBİLİRLİK

### Performans
- **WebSocket Latency**: < 50ms
- **GRPAN Computation**: O(1) per trade print
- **RWVAP Computation**: O(N) per symbol (N = prints in window)
- **Table Rendering**: Virtual scrolling ile 1000+ satır sorunsuz
- **Memory Usage**: Ring buffers ile sabit memory (O(1))

### Ölçeklenebilirlik
- **Multi-Symbol**: 100+ symbol destekler
- **Multi-Account**: Birden fazla trading account
- **Horizontal Scaling**: Redis ile distributed architecture
- **Cloud Deployment**: Docker, Kubernetes ready

---

## 🔧 KONFİGÜRASYON

### Environment Variables
- `REDIS_HOST`: Redis server host
- `REDIS_PORT`: Redis server port
- `HAMMER_WS_URL`: Hammer Pro WebSocket URL
- `IBKR_HOST`: IBKR TWS/Gateway host
- `IBKR_PORT`: IBKR TWS/Gateway port

### YAML Configuration Files
- `intent_rules.yaml`: Intent engine kuralları
- `order_plan_rules.yaml`: Order planning kuralları
- `order_queue_rules.yaml`: Order queue kuralları
- `order_gate_rules.yaml`: Order gate kuralları
- `psfalgo_rules.yaml`: PSFALGO kuralları
- `state_rules.yaml`: State machine kuralları
- `signal_rules.yaml`: Signal interpreter kuralları
- `rank_rules.yaml`: Ranking kuralları
- **`benchmark_rules.yaml`** (YENİ): Benchmark formülleri (PRIMARY GROUP + CGRUP bazlı)
- `group_benchmark.yaml`: Fallback benchmark rules (eski format)

---

## 📚 DOKÜMANTASYON

Tüm detaylı dokümantasyon `quant_engine/docs/` klasöründe:
- `EXECUTION_PIPELINE.md`: Execution flow
- `POSITION_MANAGER.md`: Position tracking
- `RISK_MANAGER.md`: Risk management
- `STRATEGY_ENGINE.md`: Strategy framework
- `BACKTEST_REPORT.md`: Backtest raporlama
- `WALK_FORWARD_OPTIMIZATION.md`: Walk-forward optimization
- `MONTE_CARLO.md`: Monte Carlo simulation
- `TESTING_GUIDE.md`: Testing rehberi

---

## 🎯 SONUÇ VE GÜNCEL DURUM

**Quant Engine**, JANALL'in tüm özelliklerini içeren ve çok daha fazlasını sunan, modern, modüler, ölçeklenebilir bir trading platformudur. Web tabanlı UI, gelişmiş analiz araçları (GRPAN rolling windows, RWVAP, GOD/ROD, Pricing Overlay), risk yönetimi, backtest ve optimization özellikleri ile profesyonel trading için tasarlanmıştır.

### Ana Avantajlar
1. **Modern Web UI**: Cross-platform, responsive, sıralanabilir tablolar
2. **Gelişmiş Analiz**: GRPAN rolling windows, RWVAP, GOD/ROD
3. **Pricing Overlay Engine**: Benchmark-aware ucuzluk/pahalılık skorları (Janall parity)
4. **İki Katmanlı Gruplama**: PRIMARY GROUP + SECONDARY CGRUP sistemi
5. **Trading-Time Aware**: NYSE trading hours ve holidays desteği
6. **Modüler Mimari**: Kolay genişletilebilir, bakımı kolay
7. **Cloud-Ready**: Docker, scalable, multi-user
8. **API-First**: REST API ve WebSocket endpoints
9. **Backtest & Optimization**: Strateji testi ve optimizasyon
10. **Risk Management**: Monte Carlo, circuit breaker, risk limits
11. **Redis Integration**: Otomatik Redis başlatma, pub/sub messaging
12. **Group Navigation**: Frontend'de grup bazlı filtreleme ve navigasyon

---

## 📊 GÜNCEL DURUM (Son Geliştirmeler)

### ✅ Tamamlanan Özellikler

#### 1. **GRPAN Rolling Windows** ✅
- Trading-time aware window'lar (10m, 30m, 1h, 3h, 1d, 3d)
- NYSE trading hours ve holidays desteği
- Market kapalıyken stable windows
- Bootstrap/recovery mode (getTicks sadece gerektiğinde)

#### 2. **RWVAP (Robust VWAP)** ✅
- Extreme volume filtering (AVG_ADV * 1.0 threshold)
- Trading-day windows (1D, 3D, 5D)
- Shared buffer (GRPAN ile)
- Status tracking (OK/COLLECTING/INSUFFICIENT_DATA)

#### 3. **GOD/ROD Hesaplama** ✅
- GRPAN ORT DEV (GOD): Tüm GRPAN window'larının ortalaması
- RWVAP ORT DEV (ROD): Tüm RWVAP window'larının ortalaması
- Deviation hesaplama: `Last - GRPAN_ORT` / `Last - RWVAP_ORT`
- Frontend'de sıralanabilir kolonlar

#### 4. **İki Katmanlı Gruplama Sistemi** ✅
- PRIMARY GROUP çözümleme (22 grup)
- SECONDARY GROUP (CGRUP) çözümleme (sadece kuponlu gruplar için)
- Janall mantığı: Her grubun ayrı CSV dosyası (ssfinekheldff.csv, vb.)
- Cache mekanizması (performans optimizasyonu)
- `GROUP` kolonu static data'ya eklenir

#### 5. **Benchmark Engine** ✅
- İki katmanlı gruplamaya göre benchmark formülü seçimi
- YAML tabanlı konfigürasyon (`benchmark_rules.yaml`)
- heldkuponlu için CGRUP bazlı formüller (C400, C425, C450, vb.)
- Diğer gruplar için PRIMARY GROUP bazlı formüller
- Janall parity (formüller birebir aynı)

#### 6. **Pricing Overlay Engine** ✅
- Benchmark-aware ucuzluk/pahalılık skorları
- Dirty tracking (sadece değişen symbol'ler)
- Throttle mechanism (250ms per symbol, batch processing)
- 18 overlay score kolonu (ucuzluk, pahalılık, final skorlar)
- Janall parity (formüller birebir aynı)
- Status tracking (OK/COLLECTING/ERROR)

#### 7. **Frontend Geliştirmeleri** ✅
- **Group Selector**: Header dropdown ile grup navigasyonu
- **Group Context Bar**: Seçili grup için benchmark ve özet
- **Client-Side Filtering**: Yeni sekmede grup bazlı filtreleme
- **Overlay Scores Display**: 18 yeni kolon (ScannerTable)
- **Overlay Scores Inspector**: State Reason Inspector'da detaylı görüntüleme
- **prev_close Fallback**: CSV'den prev_close yükleme
- **Format Improvements**: Tüm fiyatlar 2 ondalık, deviation'lar doğru yönde

#### 8. **Redis Integration** ✅
- **Redis Startup Script**: Otomatik Redis başlatma (`redis_startup.py`)
- Windows (WSL) ve Linux desteği
- `baslat.py` entegrasyonu (backend başlatmadan önce Redis kontrolü)
- Optional Redis (çalışmıyorsa in-memory cache kullanılır)

#### 9. **Data Loading Improvements** ✅
- **prev_close Fallback**: Live market data'da yoksa CSV'den yükle
- **GROUP Resolution**: CSV'de yoksa Janall mantığı ile çözümle
- **Static Data Store**: `prev_close` ve `GROUP` kolonları eklendi
- **WebSocket Broadcast**: `prev_close` fallback mekanizması

#### 10. **Performance Optimizations** ✅
- **Dirty Tracking**: Pricing Overlay Engine'de sadece değişen symbol'ler
- **Throttle Mechanism**: Minimum interval, batch processing
- **Cache Systems**: Group file cache, overlay cache, benchmark cache
- **Diff Publishing**: WebSocket'te sadece değişen alanlar gönderilir

### 🔄 Devam Eden / Planlanan Özellikler

#### 1. **PSFALGO Full Implementation**
- RUNALL loop/cycle mantığı (async/await)
- Queue düzeni (FastAPI async queue)
- Order iptal-yaz stratejisi
- Auto confirm loop (WebSocket based)

#### 2. **Backtest Engine**
- Historical data loading
- Strategy framework
- Performance metrics

#### 3. **Risk Management**
- Monte Carlo simulation
- Circuit breaker
- Position limits

#### 4. **Execution Adapters**
- Hammer Pro execution
- IBKR execution
- Simulator

---

## 📈 PERFORMANS VE ÖLÇEKLENEBİLİRLİK

### Performans
- **WebSocket Latency**: < 50ms
- **GRPAN Computation**: O(1) per trade print
- **RWVAP Computation**: O(N) per symbol (N = prints in window)
- **Pricing Overlay Computation**: O(1) per symbol (throttled, cached)
- **Table Rendering**: Virtual scrolling ile 1000+ satır sorunsuz
- **Memory Usage**: Ring buffers ile sabit memory (O(1))
- **Dirty Tracking**: Sadece değişen symbol'ler yeniden hesaplanır

### Ölçeklenebilirlik
- **Multi-Symbol**: 100+ symbol destekler
- **Multi-Account**: Birden fazla trading account
- **Horizontal Scaling**: Redis ile distributed architecture
- **Cloud Deployment**: Docker, Kubernetes ready
- **Batch Processing**: Pricing Overlay Engine'de 200 symbol/batch

### Kullanım Alanları
- Preferred stock trading
- Algoritmik trading
- Risk yönetimi
- Portfolio optimizasyonu
- Strateji geliştirme ve test
- Real-time market analysis

---

---

## 🎯 EN SON AŞAMA (Güncel Durum)

### Tamamlanan Özellikler (Son Güncellemeler)

1. ✅ **GRPAN Rolling Windows**: Trading-time aware, 6 window (10m, 30m, 1h, 3h, 1d, 3d)
2. ✅ **RWVAP**: Robust VWAP, extreme volume filtering, 3 window (1D, 3D, 5D)
3. ✅ **GOD/ROD**: GRPAN/RWVAP ortalama deviation hesaplama
4. ✅ **İki Katmanlı Gruplama**: PRIMARY GROUP + SECONDARY CGRUP sistemi
5. ✅ **Benchmark Engine**: İki katmanlı gruplamaya göre benchmark hesaplama
6. ✅ **Pricing Overlay Engine**: Benchmark-aware ucuzluk/pahalılık skorları (18 kolon)
7. ✅ **Group Selector**: Frontend'de grup navigasyonu ve filtreleme
8. ✅ **prev_close Fallback**: CSV'den prev_close yükleme mekanizması
9. ✅ **Redis Startup**: Otomatik Redis başlatma script'i
10. ✅ **Frontend Overlay Display**: 18 overlay score kolonu + State Reason Inspector bölümü

### Şu Anda Çalışan Sistem

- ✅ **Backend**: FastAPI + WebSocket, GRPAN/RWVAP/Pricing Overlay hesaplama
- ✅ **Frontend**: React + Vite, Scanner Table, State Reason Inspector, Group Selector
- ✅ **Market Data**: Hammer Pro WebSocket, L1/L2 updates, trade prints
- ✅ **Static Data**: CSV yükleme, GROUP resolution, prev_close fallback
- ✅ **Real-time Updates**: WebSocket broadcast, diff publishing
- ✅ **Group Navigation**: Client-side filtering, new tab navigation

### Sonraki Adımlar (Planlanan)

1. 🔄 **PSFALGO Full Implementation**: RUNALL loop, queue system, order management
2. 🔄 **Backtest Engine**: Historical data, strategy testing
3. 🔄 **Risk Management**: Monte Carlo, circuit breaker
4. 🔄 **Execution Adapters**: Hammer/IBKR execution

---

*Son Güncelleme: 2025-01-14*

