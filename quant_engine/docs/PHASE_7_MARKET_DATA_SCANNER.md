# Phase 7: Market Data & Scanner Layer

## 📋 Genel Bakış

Phase 7, Janall'daki "scanner + kolon hesaplama + günlük snapshot" yapısını Quant Engine içine profesyonel ve non-blocking şekilde ekler.

**ÖNEMLİ**: Decision / Execution / Proposal katmanlarına **ASLA dokunulmaz**. Sadece data ve scanner eklenir.

---

## 🎯 Hedefler

1. **MarketSnapshot Model**: Decision engine'ler için TEK GERÇEK VERİ KAYNAĞI
2. **Daily Snapshot Mantığı**: Janall uyumlu (befday_* alanları)
3. **Metric Compute Engine**: Janall'da kullanılan tüm metrikler
4. **Scanner API**: Read-only, filtrelenebilir, sort edilebilir
5. **Decision Layer Entegrasyonu**: MarketSnapshot'tan beslenir (dokunmadan)

---

## 📁 Dosya Yapısı

```
quant_engine/app/psfalgo/
├── market_snapshot_models.py    # MarketSnapshot model
├── market_snapshot_store.py     # Daily snapshot management
├── metric_compute_engine.py      # Metric computation
└── metrics_snapshot_api.py        # Updated: MarketSnapshot integration

quant_engine/app/api/
└── psfalgo_routes.py             # Scanner API endpoint (updated)

quant_engine/snapshots/
└── snapshot_YYYY-MM-DD_ACCOUNT.json    # Daily snapshots (optional)
```

---

## 🔧 Bileşenler

### 1. MarketSnapshot Model (`market_snapshot_models.py`)

**MarketSnapshot** - Single source of truth for decision engines.

**Fields:**
- **Live market data**: `bid`, `ask`, `last`, `spread`, `spread_percent`, `prev_close`
- **Daily snapshot**: `befday_qty`, `befday_cost`
- **Today changes**: `today_qty_chg`, `today_cost`
- **Computed metrics**: `sma63_chg`, `sma246_chg`, `fbtot`, `sfstot`, `gort`, `avg_adv`
- **Account type**: `account_type` (IBKR_GUN / IBKR_PED)
- **Timestamp**: `snapshot_ts`

**Methods:**
- `to_dict()`: JSON serialization
- `to_scanner_row()`: Scanner row format (for UI/API)

### 2. MetricComputeEngine (`metric_compute_engine.py`)

**Responsibilities:**
- Compute SMA63_CHG, SMA246_CHG (from static data)
- Compute FBTOT, SFSTOT, GORT (from pricing overlay)
- Compute spread, spread_percent
- Compute befday_* and today_* fields

**Methods:**
- `compute_metrics()`: Compute all metrics and create MarketSnapshot

### 3. MarketSnapshotStore (`market_snapshot_store.py`)

**Responsibilities:**
- Daily snapshot creation (befday_* fields)
- Current snapshot management
- Account type separation (IBKR_GUN / IBKR_PED)
- Snapshot persistence (optional JSON export)

**Daily Snapshot Logic:**
- **Market open öncesi**: befday_* alanları hesapla (from Hammer Pro / IBKR)
- **Gün içinde**: befday_* SABİT, live data güncellenir
- **Ertesi gün**: Yeni snapshot oluşturulur

**Methods:**
- `create_daily_snapshot()`: Create daily snapshot for account type
- `update_current_snapshot()`: Update current snapshot
- `get_current_snapshot()`: Get current snapshot for symbol
- `get_all_current_snapshots()`: Get all current snapshots

### 4. Scanner API (`psfalgo_routes.py`)

**Endpoint:**
- `GET /api/psfalgo/scanner` - Get scanner data with filters and sorting

**Filters:**
- `account_type`: IBKR_GUN, IBKR_PED
- `fbtot_lt`, `fbtot_gt`: FBTOT filters
- `gort_gt`, `gort_lt`: GORT filters
- `sma63_chg_lt`, `sma63_chg_gt`: SMA63_CHG filters
- `sma246_chg_lt`, `sma246_chg_gt`: SMA246_CHG filters

**Sorting:**
- `sort_by`: Field name (fbtot, gort, sma63_chg, etc.)
- `sort_desc`: Descending (default: True)

**Limit:**
- `limit`: Maximum results (default: 500, max: 1000)

### 5. Decision Layer Entegrasyonu (`metrics_snapshot_api.py`)

**Updated:**
- `_aggregate_metrics_for_symbol()`: Now uses MarketSnapshot as single source of truth
- Falls back to legacy aggregation if MarketSnapshot not available
- Decision logic DEĞİŞMEZ
- Threshold / rule / config DEĞİŞMEZ

---

## 📊 MarketSnapshot Fields

### Live Market Data
- `bid`: Current bid price
- `ask`: Current ask price
- `last`: Last trade price
- `spread`: Ask - Bid
- `spread_percent`: (Spread / Mid) * 100
- `prev_close`: Previous day close

### Daily Snapshot (befday_*)
- `befday_qty`: Quantity at previous day close
- `befday_cost`: Cost at previous day close

### Today Changes
- `today_qty_chg`: today_qty - befday_qty
- `today_cost`: Current cost (today_qty * current_price)

### Computed Metrics
- `sma63_chg`: SMA63 change (from static data)
- `sma246_chg`: SMA246 change (from static data)
- `fbtot`: Front Buy Total (from pricing overlay)
- `sfstot`: Short Front Sell Total (from pricing overlay)
- `gort`: Group-relative value (from static data or pricing overlay)
- `avg_adv`: Average Daily Volume (from static data)

### Account Type
- `account_type`: "IBKR_GUN" or "IBKR_PED"

---

## 🔄 Daily Snapshot Flow

### Market Open Öncesi (16:30 TR = 09:30 ET previous day)
1. Get positions from Hammer Pro / IBKR
2. Calculate `befday_qty` and `befday_cost`
3. Create daily snapshot for account type
4. Store in `daily_snapshots[date][account_type]`

### Gün İçinde
1. `befday_*` fields SABİT (from daily snapshot)
2. Live market data (bid/ask/last) güncellenir
3. Computed metrics (FBTOT, GORT, etc.) güncellenir
4. Current snapshots updated

### Ertesi Gün
1. New daily snapshot created
2. Previous day snapshot archived
3. New `befday_*` fields calculated

---

## 🚀 Kullanım

### 1. Create Daily Snapshot

```python
from app.psfalgo.market_snapshot_store import get_market_snapshot_store

store = get_market_snapshot_store()
positions = {
    'MS PRK': {'qty': 400.0, 'cost': 10800.0},
    'WFC PRY': {'qty': 200.0, 'cost': 4800.0}
}

snapshots = await store.create_daily_snapshot(
    account_type='IBKR_GUN',
    positions=positions
)
```

### 2. Update Current Snapshot

```python
from app.psfalgo.metric_compute_engine import get_metric_compute_engine
from app.psfalgo.market_snapshot_store import get_market_snapshot_store

compute_engine = get_metric_compute_engine()
store = get_market_snapshot_store()

market_data = {'bid': 27.28, 'ask': 27.32, 'last': 27.30, 'prev_close': 27.00}
position_data = {'qty': 400.0, 'cost': 10920.0, 'befday_qty': 400.0, 'befday_cost': 10800.0}

snapshot = compute_engine.compute_metrics(
    symbol='MS PRK',
    market_data=market_data,
    position_data=position_data
)

await store.update_current_snapshot('MS PRK', snapshot, account_type='IBKR_GUN')
```

### 3. Get Scanner Data

```bash
GET /api/psfalgo/scanner?fbtot_lt=1.10&gort_gt=-1&sort_by=fbtot&limit=50
```

### 4. Decision Layer (Automatic)

Decision engines automatically use MarketSnapshot via `metrics_snapshot_api`:
- No changes to decision logic
- No changes to thresholds
- No changes to rules
- Just data source updated

---

## ⚠️ Önemli Notlar

1. **Decision Logic'e Dokunma YOK**:
   - Decision engine'ler değişmez
   - Threshold / rule / config değişmez
   - Sadece data source güncellenir

2. **Execution Layer'a Dokunma YOK**:
   - Execution logic değişmez
   - Broker adapter çağrısı yok

3. **Dry-Run Kapatma YOK**:
   - dry_run zorunlu
   - Execution ASLA yapılmaz

4. **CSV Zorunluluğu YOK**:
   - Daily snapshots JSON formatında (optional)
   - CSV export istenirse eklenebilir

5. **Account Type Separation**:
   - IBKR_GUN ve IBKR_PED ayrı snapshots
   - Scanner API'de filtrelenebilir

---

## 📈 Sonraki Adımlar

1. ✅ MarketSnapshot model oluşturuldu
2. ✅ MetricComputeEngine oluşturuldu
3. ✅ MarketSnapshotStore oluşturuldu
4. ✅ Scanner API endpoint eklendi
5. ✅ Decision layer entegrasyonu (metrics_snapshot_api updated)
6. ⏳ Daily snapshot creation logic (Hammer Pro / IBKR integration)
7. ⏳ Snapshot update loop (market data updates)

---

## 🎯 Phase 7 Durumu

**TAMAMLANDI** ✅

- MarketSnapshot model: ✅
- MetricComputeEngine: ✅
- MarketSnapshotStore: ✅
- Scanner API: ✅
- Decision layer entegrasyonu: ✅
- Documentation: ✅

**Sistem artık MarketSnapshot'ı single source of truth olarak kullanıyor!** 🔍




