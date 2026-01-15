# Quant Engine - Veri Gereksinimleri Analiz Raporu

## 📋 Özet

Bu rapor, ChatGPT'nin belirttiği 5 katmanlı veri gereksinimlerini mevcut `quant_engine` sistemimizle karşılaştırarak, **neler var, neler yok, ne gerekir** sorularını detaylı olarak yanıtlamaktadır.

---

## 1️⃣ ZORUNLU VERİLER (OLMAZSA OLMAZ)

### A) Tick / Print Seviyesi (Time & Sales)

#### ChatGPT Gereksinimleri:
- ✅ `timestamp` (ms hassasiyet)
- ✅ `price`
- ✅ `size`
- ❌ `side` (bid hit mi, ask lift mi)
- ✅ `is_truth_tick` (100-200 lot filtreli gerçek print tanımı)

#### Mevcut Durumumuz:

**✅ VAR:**
- **TruthTicksEngine** (`quant_engine/app/market_data/truth_ticks_engine.py`)
  - `add_tick()` metodu ile tick ekleniyor
  - Normalize edilmiş tick formatı:
    ```python
    {
        'ts': timestamp,      # float (unix timestamp)
        'price': float,       # fiyat
        'size': float,        # lot size
        'exch': str           # exchange (FNRA, NYSE, ARCA, etc.)
    }
    ```
  - `is_truth_tick()` metodu: size >= 20, FNRA rules (100/200 lot)
  - `filter_truth_ticks()` metodu ile filtreleme
  - `tick_store`: `{symbol: deque(maxlen=200)}` - son 200 tick saklanıyor

**❌ EKSİK:**
- **`side` (bid hit / ask lift)**: Tick'lerde yok
  - Neden gerekli: Front-run tespiti, two-sided flow analizi
  - Nasıl eklenir: Hammer L1Update'ten `side` field'ı eklenebilir
  - Öncelik: **YÜKSEK** (front-run tracking için kritik)

**🟡 GELİŞTİRME ÖNERİLERİ:**
- `truth_confidence` (0-1): size + ardışıklık + zaman yakınlığı
  - Şu an: Yok
  - Nasıl eklenir: `compute_metrics_for_timeframe()` içinde hesaplanabilir
- `burst_id`: Art arda gelen printleri grup olarak tanımlamak
  - Şu an: Yok
  - Nasıl eklenir: Time-window based grouping (örn: 5 saniye içinde 3+ print = burst)

---

### B) Anlık Order Book (L1 zorunlu, L2 opsiyonel)

#### ChatGPT Gereksinimleri:
- ✅ `best_bid`
- ✅ `best_ask`
- ✅ `bid_size`
- ✅ `ask_size`
- ✅ `spread`

#### Mevcut Durumumuz:

**✅ VAR:**
- **Market Data Cache** (`quant_engine/app/api/market_data_routes.py`)
  - `market_data_cache: Dict[str, Dict[str, Any]]` - global cache
  - `update_market_data_cache()` ile güncelleniyor
  - Hammer L1Update'ten geliyor
  - Format:
    ```python
    {
        'bid': float,
        'ask': float,
        'last': float,
        'size': int,
        'prev_close': float,
        'spread': float,  # ask - bid
        'timestamp': float
    }
    ```
  - `bid_size`, `ask_size`: Hammer'dan geliyorsa var, yoksa hesaplanabilir

**🟡 OPSİYONEL (L2):**
- **Depth seviyeleri**: Şu an yok
- **Bid/ask duvarı**: Şu an yok
- **Iceberg sezgisi**: Şu an yok
- **Not:** L2 data Hammer'dan alınabilir ama şu an kullanılmıyor

**Öncelik:** ✅ Yeterli (L1 var, L2 opsiyonel)

---

### C) Benchmark (PFF vs)

#### ChatGPT Gereksinimleri:
- ✅ `benchmark_last`
- ✅ `benchmark_prev_close`
- ✅ `benchmark_change`
- ❌ `benchmark_change_delta` (son 1-5 dk)

#### Mevcut Durumumuz:

**✅ VAR:**
- **ETF Market Data** (`quant_engine/app/api/market_data_routes.py`)
  - `etf_market_data: Dict[str, Dict[str, Any]]` - global cache
  - `update_etf_market_data()` ile güncelleniyor
  - PFF data:
    ```python
    {
        'last': float,
        'prev_close': float,
        'daily_change_percent': float,
        'daily_change_cents': float,
        'bid': float,
        'ask': float
    }
    ```
  - **BenchmarkEngine** (`quant_engine/app/market_data/benchmark_engine.py`)
    - `compute_benchmark_change()` metodu ile composite benchmark hesaplanıyor
    - Formula-based (PFF, TLT, IEF, IEI weights)
    - `benchmark_chg` = composite last - composite prev_close

**❌ EKSİK:**
- **`benchmark_change_delta` (son 1-5 dk)**: Şu an yok
  - Neden gerekli: `pff_delta_5m` için (shock_impulse hesaplama)
  - Nasıl eklenir: Time-series tracking (Redis veya in-memory deque)
  - Öncelik: **ORTA** (shock_impulse için gerekli ama şu an `pff_change_now` kullanılıyor)

**🟡 GELİŞTİRME ÖNERİLERİ:**
- Her hisse için kendi benchmark'ı (bank preferred → KBE, mREIT → REM vs)
  - Şu an: Composite benchmark var (formula-based)
  - Nasıl eklenir: `benchmark_rules.yaml`'da symbol-specific formulas

---

### D) Prev Close & Gün İçi Referanslar

#### ChatGPT Gereksinimleri:
- ✅ `prev_close`
- ❌ `today_open`
- ❌ `day_high`
- ❌ `day_low`

#### Mevcut Durumumuz:

**✅ VAR:**
- **Prev Close**: `market_data_cache` içinde var
  - CSV'den yükleniyor (startup'ta)
  - Hammer snapshot'tan da alınabilir

**❌ EKSİK:**
- **`today_open`**: Şu an yok
- **`day_high`**: Şu an yok
- **`day_low`**: Şu an yok
  - Neden gerekli: "Ucuzdan alıyorum" algısı, panic/mean reversion
  - Nasıl eklenir: Hammer'dan veya gün içi tracking (Redis)
  - Öncelik: **DÜŞÜK** (opsiyonel ama güçlendirici)

---

### E) AVG_ADV (Liquidity Normalization)

#### ChatGPT Gereksinimleri:
- ✅ `avg_adv_shares`
- 🟡 `avg_dollar_volume` (opsiyonel)

#### Mevcut Durumumuz:

**✅ VAR:**
- **Static Data Store** (`quant_engine/app/market_data/static_data_store.py`)
  - `AVG_ADV` field'ı CSV'den yükleniyor
  - `get_static_data(symbol)` ile erişiliyor
  - Format: `{'AVG_ADV': float, ...}`

**🟡 OPSİYONEL:**
- **`avg_dollar_volume`**: Şu an yok, ama hesaplanabilir (AVG_ADV * avg_price)

**Öncelik:** ✅ Yeterli

---

## 2️⃣ KARAR VERDİREN AMA LOG İLE TAKİP EDİLMESİ GEREKENLER

### F) Quote State (Algoritmanın Hafızası)

#### ChatGPT Gereksinimleri:
- ❌ `symbol`
- ❌ `side` (buy/sell)
- ❌ `quote_price`
- ❌ `quote_time`
- ❌ `size`
- ❌ `reason_code` (MM, hedge, panic, etc)

#### Mevcut Durumumuz:

**❌ EKSİK:**
- **Quote State Tracking**: Şu an yok
  - Neden gerekli: Front-run tespiti, "Ben bunu niye yazmıştım?" sorusu
  - Nasıl eklenir: Redis veya in-memory store
  - Öncelik: **KRİTİK** (front-run tracking için zorunlu)

**🟡 İLGİLİ SİSTEMLER:**
- **OrderController** (`quant_engine/app/psfalgo/order_controller.py`)
  - `TrackedOrder` class var ama MM quote state için değil
  - Order lifecycle tracking var (PENDING, SENT, FILLED, etc.)
  - Ama MM quote state (reason_code, quote_time) yok

**ÖNERİ:**
```python
# Redis Schema
quote_state:{symbol}:{side} = {
    "quote_price": float,
    "quote_time": timestamp,
    "size": int,
    "reason_code": "MM|HEDGE|PANIC",
    "effective_frac": float,
    "shock_level": int,
    "front_run_steps": int
}
```

---

### G) Front-run / Miss Tracking

#### ChatGPT Gereksinimleri:
- ❌ `front_run_count`
- ❌ `last_front_run_ts`
- ❌ `decay_half_life` (örn 60 sn)

#### Mevcut Durumumuz:

**❌ EKSİK:**
- **Front-run Tracking**: Şu an yok
  - Neden gerekli: `effective_frac` hesaplama (0.15 → 0.30)
  - Nasıl eklenir: Quote state + tick comparison
  - Öncelik: **KRİTİK** (adaptive aggressiveness için zorunlu)

**🟡 MEVCUT KOD:**
- `AuraMMEngine._compute_effective_quote_fraction()` içinde `front_run_steps` parametresi var ama **TODO** olarak işaretlenmiş
- `front_run_steps=0` hardcoded

**ÖNERİ:**
```python
# Front-run Detection Logic
def detect_front_run(symbol, side, quote_price, last_ticks):
    """
    Detect if our quote was front-run.
    
    Logic:
    - If side == 'BUY' and print occurs at quote_price - 0.01 → front-run
    - If side == 'SELL' and print occurs at quote_price + 0.01 → front-run
    """
    for tick in last_ticks[-10:]:  # Last 10 ticks
        if side == 'BUY' and abs(tick['price'] - (quote_price - 0.01)) < 0.001:
            return True
        if side == 'SELL' and abs(tick['price'] - (quote_price + 0.01)) < 0.001:
            return True
    return False

# Redis Schema
front_run:{symbol}:{side} = {
    "count": int,
    "last_ts": timestamp,
    "decay_half_life": 60  # seconds
}

# Decay Logic
def get_front_run_steps(symbol, side, current_ts):
    data = redis.get(f"front_run:{symbol}:{side}")
    if not data:
        return 0
    elapsed = current_ts - data['last_ts']
    decay_factor = exp(-elapsed / data['decay_half_life'])
    return data['count'] * decay_factor
```

---

### H) Shock Regime State

#### ChatGPT Gereksinimleri:
- ✅ `shock_level` (hesaplanıyor)
- ✅ `shock_dir` (hesaplanıyor)
- ❌ `shock_start_ts`
- ❌ `shock_peak`

#### Mevcut Durumumuz:

**✅ VAR:**
- **Shock Level Calculation**: `AuraMMEngine._compute_effective_quote_fraction()`
  - `shock_level = floor(abs(pff_change_now) / pff_step)`
  - `shock_impulse = floor(abs(pff_delta_5m) / pff_step)`
  - `effective_shock = max(shock_level, shock_impulse)`
  - `shock_dir = sign(pff_change_now)` (implicit)

**❌ EKSİK:**
- **`shock_start_ts`**: Şu an yok
  - Neden gerekli: "Bu düşüş yeni mi, eski mi?" sorusu
  - Nasıl eklenir: Shock threshold'u aştığında timestamp kaydet
- **`shock_peak`**: Şu an yok
  - Neden gerekli: Panik mi normal mi ayrımı
  - Nasıl eklenir: Time-series tracking (max value)

**ÖNERİ:**
```python
# Redis Schema
shock_regime:{symbol} = {
    "shock_level": int,
    "shock_dir": "UP|DOWN",
    "shock_start_ts": timestamp,
    "shock_peak": float,
    "shock_peak_ts": timestamp
}

# Update Logic
def update_shock_regime(symbol, pff_change_now, current_ts):
    current_shock = floor(abs(pff_change_now) / 0.04)
    data = redis.get(f"shock_regime:{symbol}")
    
    if not data or current_shock != data['shock_level']:
        # New shock regime
        redis.set(f"shock_regime:{symbol}", {
            "shock_level": current_shock,
            "shock_dir": "UP" if pff_change_now > 0 else "DOWN",
            "shock_start_ts": current_ts,
            "shock_peak": abs(pff_change_now),
            "shock_peak_ts": current_ts
        })
    else:
        # Update peak if needed
        if abs(pff_change_now) > data['shock_peak']:
            data['shock_peak'] = abs(pff_change_now)
            data['shock_peak_ts'] = current_ts
            redis.set(f"shock_regime:{symbol}", data)
```

---

## 3️⃣ ANALİTİK AMA OPSİYONEL (SİSTEMİ SEVİYE ATLATABİLİR)

### I) Two-Sidedness Metrics

#### ChatGPT Gereksinimleri:
- ✅ `vol_up_share`
- ✅ `vol_down_share`
- ✅ `tick_up_share`
- ✅ `tick_down_share`
- ✅ `balance_score = 1 - |up - down|`

#### Mevcut Durumumuz:

**✅ VAR:**
- **Two-Sided Score**: `AuraMMEngine._compute_timeframe_anchors()`
  - `p1 = a1_volume / total_anchor_volume`
  - `p2 = a2_volume / total_anchor_volume`
  - `two_sided_score = 1.0 - abs(p1 - p2)`
  - Extreme penalty: `if max(p1, p2) > 0.95: two_sided_score *= 0.5`

**🟡 GELİŞTİRME:**
- **Tick-level up/down share**: Şu an yok (sadece volume share var)
  - Nasıl eklenir: Truth ticks'te price direction tracking

**Öncelik:** ✅ Yeterli (volume-based two-sidedness var)

---

### J) Volav Anchors (Merged, Tradeable)

#### ChatGPT Gereksinimleri:
- ✅ `center_price`
- ✅ `volume`
- ✅ `volume_share`
- ✅ `tick_count`
- ✅ `last_print_ts`

#### Mevcut Durumumuz:

**✅ VAR:**
- **Volav Levels**: `TruthTicksEngine.compute_volav_levels()`
  - Format:
    ```python
    {
        'rank': int,
        'price': float,  # center_price (VWAP)
        'volume': float,
        'tick_count': int,
        'pct_of_truth_volume': float,  # volume_share
        'last_print_ts': float,
        'range_min': float,
        'range_max': float,
        'merged': bool
    }
    ```
  - MM-Anchor spacing constraint: 0.06$ gap garantisi
  - Merge threshold: `min_gap * 0.90`

**Öncelik:** ✅ Yeterli

---

### K) Relative Value Scores

#### ChatGPT Gereksinimleri:
- ✅ `buy_cheapness = bench_change - symbol_change`
- ✅ `sell_richness = symbol_change - bench_change`

#### Mevcut Durumumuz:

**✅ VAR:**
- **Relative Value Metrics**: `AuraMMEngine._generate_recommendations()`
  - `buy_cheap = bench_change - symbol_change`
  - `sell_rich = symbol_change - bench_change`
  - `recommendations['relative_value']` dict'inde döndürülüyor
  - Skew sizing: `if buy_cheap > 0.05: buy_size_mult = 1.2`

**🟡 GELİŞTİRME:**
- **Expose edilmeli**: Frontend'de gösterilmeli
  - Şu an: Backend'de hesaplanıyor ama UI'da gösterilmiyor

**Öncelik:** ✅ Yeterli (hesaplanıyor, sadece UI'da expose edilmeli)

---

## 4️⃣ LOG / TELEMETRİ (OLMAZSA DEBUG EDİLEMEZ)

### L) Decision Logs (ÇOK ÖNEMLİ)

#### ChatGPT Gereksinimleri:
- ❌ Structured decision logs
- ❌ Reason codes
- ❌ Context snapshot

#### Mevcut Durumumuz:

**❌ EKSİK:**
- **Structured Decision Logs**: Şu an yok
  - Neden gerekli: "Niye bunu yaptık?" sorusu, backtest benzeri analiz
  - Nasıl eklenir: Redis veya file-based logging
  - Öncelik: **KRİTİK** (sistem öğrenemez, debug edilemez)

**🟡 MEVCUT:**
- **Logger**: `app.core.logger` var ama structured logs yok
- **Reasoning Logger**: Eski sistemlerde var (`Htahaf/utils/reasoning_logger.py`) ama quant_engine'de yok

**ÖNERİ:**
```python
# Decision Log Schema
decision_log:{symbol}:{timestamp} = {
    "symbol": str,
    "timestamp": float,
    "mode": "MARKET_OPEN|MARKET_CLOSED",
    "tradeable_mm": bool,
    "spread": float,
    "effective_frac": float,
    "shock_level": int,
    "front_run_steps": int,
    "buy_quote": float,
    "sell_quote": float,
    "reason": [
        "two_sided_prints",
        "benchmark_down",
        "prev_close_above",
        "min_profit_ok"
    ],
    "context": {
        "anchor_gap": float,
        "two_sided_score": float,
        "confidence": float,
        "relative_value": {
            "buy_cheap": float,
            "sell_rich": float
        }
    }
}

# Logging Function
def log_mm_decision(symbol, recommendations, context):
    log_entry = {
        "symbol": symbol,
        "timestamp": time.time(),
        "mode": context.get('mode'),
        "tradeable_mm": recommendations.get('tradeable_mm'),
        "spread": context.get('spread'),
        "effective_frac": context.get('effective_frac'),
        "shock_level": context.get('shock_level'),
        "front_run_steps": context.get('front_run_steps'),
        "buy_quote": recommendations.get('buy_price'),
        "sell_quote": recommendations.get('sell_price'),
        "reason": _extract_reasons(recommendations, context),
        "context": context
    }
    
    # Redis: Keep last 1000 decisions per symbol
    redis.lpush(f"mm_decisions:{symbol}", json.dumps(log_entry))
    redis.ltrim(f"mm_decisions:{symbol}", 0, 999)
    
    # File: Daily log file
    log_file = f"logs/mm_decisions_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
```

---

## 5️⃣ ŞU AN GEREKMEYENLER (BİLEREK EKLEMİYORUZ)

ChatGPT'nin belirttiği gibi:
- ❌ Full L2 depth replay
- ❌ Options flow
- ❌ News sentiment (MM için fazla yavaş)
- ❌ Machine learning (şimdilik)

**Not:** Bu özellikler overfitting / latency riski yaratır.

---

## 📊 ÖZET TABLO

| Katman | Gerekli mi | Durum | Öncelik | Nasıl Eklenir |
|--------|-----------|-------|---------|---------------|
| **1A. Tick/TruthTick** | ✅ Zorunlu | ✅ Var | - | - |
| **1A. Tick Side** | ✅ Zorunlu | ❌ Yok | 🔴 YÜKSEK | Hammer L1Update'ten `side` field |
| **1B. L1 Order Book** | ✅ Zorunlu | ✅ Var | - | - |
| **1C. Benchmark** | ✅ Zorunlu | ✅ Var | - | - |
| **1C. Benchmark Delta 5m** | ⚠️ Gerekli | ❌ Yok | 🟡 ORTA | Time-series tracking (Redis) |
| **1D. Prev Close** | ✅ Zorunlu | ✅ Var | - | - |
| **1D. Day High/Low/Open** | 🟡 Opsiyonel | ❌ Yok | 🟢 DÜŞÜK | Hammer'dan veya tracking |
| **1E. AVG_ADV** | ✅ Zorunlu | ✅ Var | - | - |
| **2F. Quote State** | ⚠️ Gerekli | ❌ Yok | 🔴 KRİTİK | Redis schema + tracking |
| **2G. Front-run Tracking** | ⚠️ Gerekli | ❌ Yok | 🔴 KRİTİK | Quote state + tick comparison |
| **2H. Shock Regime** | ⚠️ Gerekli | 🟡 Kısmen | 🟡 ORTA | Redis schema + time-series |
| **3I. Two-Sidedness** | 🟡 Opsiyonel | ✅ Var | - | - |
| **3J. Volav Anchors** | 🟡 Opsiyonel | ✅ Var | - | - |
| **3K. Relative Value** | 🟡 Opsiyonel | ✅ Var | 🟡 UI'da expose edilmeli | Frontend güncellemesi |
| **4L. Decision Logs** | ❗ Kritik | ❌ Yok | 🔴 KRİTİK | Redis + file-based logging |

---

## 🎯 ÖNCELİKLİ EKSİKLER (Hemen Eklenmeli)

### 1. **Quote State Tracking** (🔴 KRİTİK)
- **Neden:** Front-run tracking için zorunlu
- **Nasıl:** Redis schema + `AuraMMEngine` içinde tracking
- **Süre:** 2-3 saat

### 2. **Front-run Detection** (🔴 KRİTİK)
- **Neden:** Adaptive aggressiveness için zorunlu
- **Nasıl:** Quote state + tick comparison logic
- **Süre:** 2-3 saat

### 3. **Decision Logs** (🔴 KRİTİK)
- **Neden:** Sistem öğrenemez, debug edilemez
- **Nasıl:** Redis + file-based structured logging
- **Süre:** 3-4 saat

### 4. **Tick Side (bid hit/ask lift)** (🔴 YÜKSEK)
- **Neden:** Two-sided flow analizi için gerekli
- **Nasıl:** Hammer L1Update'ten `side` field ekleme
- **Süre:** 1-2 saat

### 5. **Benchmark Delta 5m** (🟡 ORTA)
- **Neden:** `shock_impulse` hesaplama için
- **Nasıl:** Time-series tracking (Redis deque)
- **Süre:** 1-2 saat

---

## 📝 İMPLEMENTASYON ÖNERİLERİ

### Adım 1: Quote State Tracking
```python
# quant_engine/app/market_data/mm_quote_state.py (NEW FILE)
class MMQuoteState:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def set_quote(self, symbol, side, quote_price, size, reason_code, context):
        key = f"mm_quote:{symbol}:{side}"
        data = {
            "quote_price": quote_price,
            "quote_time": time.time(),
            "size": size,
            "reason_code": reason_code,
            "effective_frac": context.get('effective_frac'),
            "shock_level": context.get('shock_level'),
            "front_run_steps": context.get('front_run_steps', 0)
        }
        self.redis.setex(key, 3600, json.dumps(data))  # 1 hour TTL
    
    def get_quote(self, symbol, side):
        key = f"mm_quote:{symbol}:{side}"
        data = self.redis.get(key)
        return json.loads(data) if data else None
```

### Adım 2: Front-run Detection
```python
# quant_engine/app/market_data/mm_quote_state.py (EXTEND)
def detect_front_run(self, symbol, side, quote_price, truth_ticks):
    """
    Detect if our quote was front-run.
    """
    if not quote_price:
        return False
    
    # Get last 10 ticks
    recent_ticks = truth_ticks[-10:] if truth_ticks else []
    
    for tick in recent_ticks:
        tick_price = tick.get('price', 0)
        if side == 'BUY':
            # Our buy quote at $22.50, print at $22.49 → front-run
            if abs(tick_price - (quote_price - 0.01)) < 0.001:
                return True
        elif side == 'SELL':
            # Our sell quote at $22.60, print at $22.61 → front-run
            if abs(tick_price - (quote_price + 0.01)) < 0.001:
                return True
    
    return False

def update_front_run_steps(self, symbol, side, detected):
    key = f"front_run:{symbol}:{side}"
    current_ts = time.time()
    
    if detected:
        # Increment
        data = self.redis.get(key)
        if data:
            data = json.loads(data)
            data['count'] += 1
            data['last_ts'] = current_ts
        else:
            data = {'count': 1, 'last_ts': current_ts, 'decay_half_life': 60}
        self.redis.setex(key, 3600, json.dumps(data))
    else:
        # Decay
        data = self.redis.get(key)
        if data:
            data = json.loads(data)
            elapsed = current_ts - data['last_ts']
            decay_factor = math.exp(-elapsed / data['decay_half_life'])
            data['count'] = max(0, int(data['count'] * decay_factor))
            self.redis.setex(key, 3600, json.dumps(data))
    
    # Get current steps
    data = self.redis.get(key)
    if data:
        data = json.loads(data)
        elapsed = current_ts - data['last_ts']
        decay_factor = math.exp(-elapsed / data['decay_half_life'])
        return max(0, int(data['count'] * decay_factor))
    return 0
```

### Adım 3: Decision Logs
```python
# quant_engine/app/market_data/mm_decision_logger.py (NEW FILE)
class MMDecisionLogger:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def log_decision(self, symbol, recommendations, context):
        log_entry = {
            "symbol": symbol,
            "timestamp": time.time(),
            "mode": context.get('mode', 'MARKET_CLOSED'),
            "tradeable_mm": recommendations.get('tradeable_mm', False),
            "spread": context.get('spread'),
            "effective_frac": context.get('effective_frac'),
            "shock_level": context.get('shock_level', 0),
            "front_run_steps": context.get('front_run_steps', 0),
            "buy_quote": recommendations.get('buy_price'),
            "sell_quote": recommendations.get('sell_price'),
            "reason": self._extract_reasons(recommendations, context),
            "context": context
        }
        
        # Redis: Keep last 1000 decisions per symbol
        key = f"mm_decisions:{symbol}"
        self.redis.lpush(key, json.dumps(log_entry))
        self.redis.ltrim(key, 0, 999)
        self.redis.expire(key, 86400 * 7)  # 7 days
        
        # File: Daily log file
        log_dir = Path("logs/mm_decisions")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"mm_decisions_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def _extract_reasons(self, recommendations, context):
        reasons = []
        if recommendations.get('tradeable_mm'):
            reasons.append("tradeable_mm_ok")
        if context.get('two_sided_score', 0) > 0.7:
            reasons.append("two_sided_prints")
        if context.get('shock_level', 0) > 0:
            reasons.append(f"benchmark_shock_level_{context['shock_level']}")
        if recommendations.get('relative_value', {}).get('buy_cheap', 0) > 0.05:
            reasons.append("symbol_cheap_vs_benchmark")
        if recommendations.get('relative_value', {}).get('sell_rich', 0) > 0.05:
            reasons.append("symbol_rich_vs_benchmark")
        return reasons
```

---

## 🎯 SONUÇ

Mevcut sistemimiz **%70 hazır**. Eksik olan kritik parçalar:

1. **Quote State Tracking** → Front-run detection için zorunlu
2. **Front-run Detection** → Adaptive aggressiveness için zorunlu
3. **Decision Logs** → Sistem öğrenmesi ve debug için zorunlu
4. **Tick Side** → Two-sided flow analizi için gerekli
5. **Benchmark Delta 5m** → Shock impulse için gerekli

Bu 5 özellik eklendiğinde, sistem ChatGPT'nin belirttiği tüm gereksinimleri karşılayacak ve **gerçek MM davranışını** kodlayabilecek.

**Toplam Süre Tahmini:** 10-15 saat (1-2 gün)

**Öncelik Sırası:**
1. Quote State + Front-run Detection (4-6 saat)
2. Decision Logs (3-4 saat)
3. Tick Side (1-2 saat)
4. Benchmark Delta 5m (1-2 saat)

