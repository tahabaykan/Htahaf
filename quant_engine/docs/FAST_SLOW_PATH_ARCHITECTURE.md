# PSFALGO Fast Path / Slow Path Architecture

## 🎯 Amaç

PSFALGO sistemini profesyonel trader ekranı (Lightspeed / Janall Mini450) mantığına yaklaştırmak:
- UI anında ve akıcı açılmalı
- L1 (bid/ask/last) verileri tak diye görünmeli
- Algo (RUNALL, KARBOTU, ADDNEWPOS) yavaşlamamalı
- Tick-by-tick (GOD / ROD / GRPAN) ana pipeline'ı asla bloklamamalı

---

## 🧠 Temel Prensip

```
L1 DATA ve TICK-BY-TICK DATA AYRI KATMANLAR
```

| Katman | Amaç | Hız | Algo Etkisi |
|--------|------|-----|-------------|
| 🟢 L1 Data (FAST PATH) | UI + Algo | Çok hızlı | ✔️ Kullanır |
| 🔵 Tick-by-Tick (SLOW PATH) | Derin analiz | Yavaş | ❌ Kullanmaz |

---

## 🟢 FAST PATH - Ana Sayfa (PSFALGO'yu Besleyen Katman)

Bu katman uygulama açılır açılmaz dolmalı.

### 1️⃣ Statik CSV Verileri (Startup'ta 1 kere)

```python
# DataFabric'te yüklenir - ASLA runtime'da disk I/O yok
- prev_close
- AVG_ADV
- FINAL_THG
- SHORT_FINAL
- symbol → group mapping
- MAXALW
- SMA63 chg, SMA246 chg
```

**Kurallar:**
- CSV'ler her API çağrısında tekrar okunmaz
- Uygulama açılışında memory cache'e alınır
- UI ve Algo aynı cached objeyi okur

### 2️⃣ L1 Market Data (Hammer Pro)

```python
# Push-based, event-driven
- bid
- ask
- last
- volume
- timestamp
```

**Özellikler:**
- Tick geldiği anda güncellenir
- Sadece değişen symbol update edilir
- Tüm symbol'ler için sürekli recompute YOK

### 3️⃣ FAST Hesaplanan Kolonlar (L1 + CSV)

GOD/ROD/GRPAN OLMADAN hesaplanır:

```python
# FastScoreCalculator'da hesaplanır
- daily_change = last - prev_close
- benchmark_chg = ETF last / prev_close
- bid_buy_ucuzluk = (bid - prev_close) / prev_close
- ask_sell_pahalilik = (ask - prev_close) / prev_close
- front_buy_ucuzluk = bid_buy_ucuzluk - benchmark_chg
- front_sell_pahalilik = ask_sell_pahalilik - benchmark_chg
- Final_BB_skor = FINAL_THG - 1000 * bid_buy_ucuzluk
- Final_FB_skor = FINAL_THG - 1000 * front_buy_ucuzluk
- Final_SAS_skor = SHORT_FINAL + 1000 * ask_sell_pahalilik
- Final_SFS_skor = SHORT_FINAL + 1000 * front_sell_pahalilik
- Fbtot, SFStot, GORT (group-based ranking)
```

**ÖNEMLİ:** Bu kolonlar PSFALGO RUNALL için yeterlidir. Algo bu noktada hiçbir tick-by-tick veriye bakmaz.

---

## 🔵 SLOW PATH - Deeper Analysis (Ayrı Sekme)

### Amaç
Tick-by-tick gerektiren ağır hesapları opt-in hale getirmek.

### UI
Ana sayfada:
- ❌ GOD
- ❌ ROD  
- ❌ GRPAN YOK

Bunun yerine:
- ➡️ "Deeper Analysis" adlı ayrı bir sekme/buton

### Özellikler
- **Lazy load** - Sadece sekme açıldığında
- **Async hesaplama** - Ana UI bloklenmez
- **Progress indicator** - Kullanıcı beklerken görür
- **Ana UI ve RUNALL asla bloklanmaz**

### Tick-by-Tick Hesaplar

```python
# DataFabric._tick_data, _god_data, _rod_data, _grpan_data
- GOD (Group Outlier Detection)
- ROD (Relative Outlier Detection)
- GRPAN (Group Analysis)
```

**Kurallar:**
- Tick-by-tick engine default OFF
- Sadece Deeper Analysis sekmesi açıkken çalışır
- Her hisse için local state tutulur
- Rolling window kullanılır
- Event-driven compute yapılır

---

## ⚙️ Algo Pipeline Kuralları (HAYATİ)

### RUNALL / PSFALGO

**✔️ KULLANIR:**
- MarketSnapshot (L1)
- prev_close
- FAST skorlar (Final_BB, Fbtot, etc.)

**❌ KULLANMAZ:**
- GOD
- ROD
- GRPAN

### DataReadinessChecker

```python
# Gating Conditions (FAST PATH only)
- bid/ask/last ✓
- prev_close ✓
- Fbtot ✓

# NOT Gating (SLOW PATH)
- GOD ❌
- ROD ❌
- GRPAN ❌
```

Algo sadece L1 + prev_close ile READY sayılır.

---

## 📁 Dosya Yapısı

```
quant_engine/app/
├── core/
│   ├── data_fabric.py          # Single Source of Truth
│   └── fast_score_calculator.py # FAST PATH hesaplamalar
├── psfalgo/
│   └── data_readiness_checker.py # FAST PATH gating
├── api/
│   └── market_data_routes.py    # /fast/* ve /deep-analysis/* endpoints
└── live/
    └── hammer_feed.py           # L1 → DataFabric bağlantısı
```

---

## 🚀 API Endpoints

### FAST PATH
```
GET /api/market-data/fast/all      # Tüm FAST snapshots
GET /api/market-data/fast/{symbol} # Tek symbol FAST snapshot
POST /api/market-data/fast/compute # Batch FAST score hesaplama
```

### SLOW PATH
```
GET /api/market-data/deep-analysis/all      # Tüm tick-by-tick data
GET /api/market-data/deep-analysis/{symbol} # Tek symbol deep analysis
POST /api/market-data/deep-analysis/enable  # Tick-by-tick enable/disable
```

---

## 🎯 Beklenen Kazançlar

| Metrik | Önce | Sonra |
|--------|------|-------|
| UI açılış | Yavaş | Anlık |
| Bid/Ask/Last | Bazen boş | Hep dolu |
| RUNALL | Bazen takılır | Stabil |
| CPU kullanımı | Yüksek | %30-40 düşük |
| Proposal kalitesi | Değişken | Tutarlı |

---

## 🧠 Özet Cümle

```
L1 data = televizyon yayını gibi sürekli akmalı
Tick-by-tick = isteyene derin analiz
Algo, tick-by-tick yüzünden asla beklememeli
```





