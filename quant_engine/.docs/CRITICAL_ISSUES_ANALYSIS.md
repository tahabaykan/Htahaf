# 🔴 KRİTİK SORUNLAR - QUANT ENGINE SİSTEM ANALİZİ

## ⚠️ SORUN 1: GLOBAL MUTABLE STATE - RACE CONDITIONS

### market_data_cache (GLOBAL DICT)
**Dosya:** `app/api/market_data_routes.py`

**Sorun:**
```python
# GLOBAL mutable dict - Thread-safe DEĞİL!
market_data_cache: Dict[str, Dict[str, Any]] = {}

# Aynı anda birden fazla thread/process erişiyor:
1. Hammer Feed Thread → update_market_data_cache()
2. XNL Engine (asyncio) → get_fast_snapshot()
3. RUNALL Engine (asyncio) → prepare_cycle_request()
4. RevBookCheck Terminal (asyncio) → position calculations
5. WebSocket Broadcaster (asyncio) → UI updates
```

**Risk:**
- ❌ **Race condition:** Aynı anda read/write → data corruption
- ❌ **Lost updates:** Bir thread'in yazdığı data başkası tarafından ezil bilir
- ❌ **Inconsistent reads:** Yarı yazılmış data okunabilir

**Kanıt:**
```python
# hammer_feed.py:131
update_market_data_cache(display_symbol, market_data)  ← Thread 1

# xnl_engine.py:1206 (async)
snapshot = fabric.get_fast_snapshot(symbol)  ← Thread 2 (event loop)

# İKİSİ DE AYNI GLOBAL market_data_cache'e erişiyor!
```

### Çözüm:
```python
import threading

# Lock ekle
_market_data_cache_lock = threading.Lock()

def update_market_data_cache(symbol, data):
    with _market_data_cache_lock:
        market_data_cache[symbol] = data

def get_market_data(symbol):
    with _market_data_cache_lock:
        return market_data_cache.get(symbol, {}).copy()  # Copy döndür!
```

---

## ⚠️ SORUN 2: DUAL PROCESS - ACCOUNT CONTEXT RACE

### TradingAccountContext Switch
**Dosya:** `app/xnl/dual_process_runner.py:156`

**Sorun:**
```python
# Line 156: Account A'ya switch
ctx.set_trading_mode(to_mode(account_a))  ← Global state değişti!

# Line 159: Cancel All
await engine.cancel_by_filter(account_a, "tum", False)

# Line 164: Start XNL
await engine.start()  ← Bu sırada başka bir process ne hesap kullanıyor?
```

**Risk:**
Eğer aynı anda:
1. **Dual Process** account_a'ya switch etti
2. **Manuel XNL Start** button tıklandı (UI'dan)
3. **RUNALL** çalışıyorsa

→ Hepsi aynı global `TradingAccountContext`'i kullanıyor!
→ Account karışabilir! (HAMPRO emir gönderilirken context IBKR_PED olabilir!)

### Kanıt:
```python
# trading_account_context.py
class TradingAccountContext:
    def __init__(self):
        self._mode = TradingAccountMode.HAMPRO  ← GLOBAL SINGLETON!
    
    def set_trading_mode(self, mode: TradingAccountMode):
        self._mode = mode  ← RACE CONDITION!
```

**Senaryo:**
```
T=0.0: Dual Process → ctx.set_trading_mode("HAMPRO")
T=0.1: Manuel XNL Start (UI) → ctx.set_trading_mode("IBKR_PED")
T=0.2: Dual Process → engine.start() ← Hangi hesap?? (IBKR_PED!)
T=0.3: HAMPRO için emir gönderilmeli ama IBKR_PED'e gitti! ❌
```

### Çözüm:
```python
# Dual Process kendi lock'unu korumalı
class DualProcessRunner:
    def __init__(self):
        self._account_lock = asyncio.Lock()  # Ekle!
    
    async def _run_loop(self):
        async with self._account_lock:  # Bu lock ile koru
            ctx.set_trading_mode(to_mode(account_a))
            await engine.cancel_by_filter(account_a, "tum", False)
            await engine.start()
```

**VEYA** daha iyi:
```python
# Hesap bilgisini engine'e parametre olarak gönder
await engine.start(account_id=account_a)  # Explicit!
```

---

## ⚠️ SORUN 3: XNL ENGINE - MULTIPLE START CALLS

### XNL Singleton Start
**Dosya:** `app/xnl/xnl_engine.py:161`

**Sorun:**
```python
async def start(self):
    if self.state.state == XNLState.RUNNING:
        logger.warning("[XNL_ENGINE] Already running")
        return False  ← Sadece warning, devam eder!
```

**Risk:**
1. Dual Process → `engine.start()` çağırır
2. Aynı anda UI'dan manuel Start tıklanır
3. İkisi de `XNLState.STARTING` state'inde geçer
4. İki kere initial cycle başlatılır! ← DUPLICATE ORDERS!

**Kanıt:**
```python
# dual_process_runner.py:164
await engine.start()  ← Call 1

# xnl_routes.py:103 (UI button)
engine = get_xnl_engine()
await engine.start()  ← Call 2 (aynı singleton!)

# İKİSİ DE AYNI ENGINE INSTANCE!
```

**Senaryo:**
```
T=0.0: Dual → engine.start() → State = STARTING
T=0.1: UI → engine.start() → State hala STARTING (check geçer!)
T=0.2: Dual → _run_initial_cycle() başlar
T=0.3: UI → _run_initial_cycle() başlar ← DUPLICATE!
T=0.4: 2x LT_TRIM, 2x KARBOTU, 2x ADDNEWPOS çalıştı! ❌
```

### Çözüm:
```python
async def start(self):
    if self.state.state in [XNLState.RUNNING, XNLState.STARTING]:
        return False  # STARTING de check et!
    
    # Atomic state transition
    async with self._start_lock:  # Lock ekle!
        if self.state.state != XNLState.STOPPED:
            return False
        self.state.state = XNLState.STARTING
        # ... rest
```

---

## ⚠️ SORUN 4: PROPOSAL STORE - CYCLE_ID CONFLICT

### Proposal Cycle ID
**Dosya:** `app/xnl/xnl_engine.py:749`

**Sorun:**
```python
# XNL uses cycle_id = -1
xnl_cycle_id = -1

# RUNALL uses positive cycle_id
cycle_id = self.loop_count  # 1, 2, 3, ...
```

**Risk:**
Eğer RUNALL ve XNL aynı anda çalışıyorsa:
1. XNL → cycle_id=-1 ile proposals yazar
2. RUNALL → cycle_id=5 ile proposals yazar
3. UI'da iki set proposal görünür (karışıklık!)
4. Conflict resolution çalışmaz (farklı cycle_id'ler!)

**Kanıt:**
```python
# xnl_engine.py:744
cleared = proposal_store.clear_pending_proposals_with_cycle_id(-1)

# runall_engine.py:423
proposals = await proposal_engine.process_decision_response(
    response=response,
    cycle_id=self.loop_count,  ← FARKLI!
    ...
)
```

**Senaryo:**
```
T=0: RUNALL cycle=5 → BK PRK SELL 200 (LT_TRIM)
T=1: XNL cycle=-1 → BK PRK SELL 250 (0-snap!) ← CONFLICT!
T=2: UI shows BOTH proposals (confusion!)
T=3: User approves first one → But second overwrites potential_qty!
```

### Çözüm:
```python
# XNL ve RUNALL mutual exclusion
class ProposalCoordinator:
    _lock = asyncio.Lock()
    
    @staticmethod
    async def generate_proposals(source, decisions):
        async with ProposalCoordinator._lock:
            # Sadece bir source proposals gönderebilir
            await proposal_engine.process_decision_response(...)
```

**VEYA:**
```python
# XNL sadece RUNALL dururken çalışmalı
if RUNALL.is_running():
    logger.error("Cannot start XNL while RUNALL is running!")
    return False
```

---

## ⚠️ SORUN 5: POTENTIAL_QTY CASCADE - DATA INSİSTENCY

### Cascade Logic Broken
**Dosya:** `app/psfalgo/runall_engine.py`

**Sorun:**
```python
# Line 587-596: potential_qty hesaplanıyor
if intent.symbol in positions_map:
    pos = positions_map[intent.symbol]
    current_qty = pos.qty
    base_potential = getattr(pos, 'potential_qty', pos.qty)
    
    # AMA: base_potential bir önceki engine'in sonucunu içermiyor!
    # positions_map STATIC (cycle başında alınmış)!
```

**Risk:**
```
LT_TRIM: BK PRK current=250, order=-200 → potential=50
  └─ O-SNAP uygula → order=-250, potential=0 ✅

KARBOTU: BK PRK current=250 (positions_map'ten)
  └─ base_potential = 250 (LT_TRIM'in 0-snap'ini GÖRMEDİ!)
  └─ order=-100 → potential=150 ❌ YANLIŞ!
  
Beklenen: potential=0 (LT_TRIM zaten kapatmış)
Gerçek: potential=150 (LT_TRIM ignore edildi)
```

**Kanıt:**
```python
# runall_engine.py:282-285 (positions_map oluşturulur)
positions_map = {pos.symbol: pos for pos in request.positions} if request.positions else {}

# Bu map STATIC! LT_TRIM sonucu güncellemez!
```

### Çözüm:
```python
# Her engine sonrası positions_map güncelle
lt_intents = await lt_trim_engine.run(...)

# Update positions_map with LT potential_qty
for intent in lt_intents:
    if intent.symbol in positions_map:
        pos = positions_map[intent.symbol]
        # Recalculate potential after 0-snap
        decision_impact = intent.qty if intent.action == 'BUY' else -intent.qty
        pos.potential_qty = pos.qty + decision_impact

# Şimdi KARBOTU güncel potential_qty kullanır!
karbotu_out = await karbotu_engine.run(request)
```

---

## ⚠️ SORUN 6: TRUTH TICK - STALE DATA

### Truth Tick TTL
**Dosya:** `app/api/market_data_routes.py`

**Sorun:**
```python
# market_data_cache NO TTL!
market_data_cache[symbol] = {
    "last": 25.11,
    "size": 100,
    "venue": "FNRA",
    # timestamp YOK! ← Ne zaman geldi belli değil!
}
```

**Risk:**
1. 14:30:00 → HBANL truth tick gelir (last=25.11, size=100, venue=FNRA)
2. 16:00:00 → Market kapandı, artık tick gelmiyor
3. 16:05:00 → XNL frontlama check yapıyor
4. truth_tick = 25.11 ← 1.5 saat önceki data! ❌ STALE!
5. Frontlama validation: 100 lot FNRA ✅ (ama 1.5 saat eski!)

**Kanıt:**
```python
# hammer_feed.py:131
update_market_data_cache(display_symbol, market_data)

# market_data içinde timestamp YOK!
market_data = {
    "bid": ...,
    "last": ...,
    "size": ...,
    "venue": ...
    # "timestamp": MISSING!
}
```

### Çözüm:
```python
# Timestamp ekle
market_data = {
    "bid": ...,
    "last": ...,
    "size": ...,
    "venue": ...,
    "timestamp": time.time()  # Unix timestamp
}

# Frontlama engine'de check et
def _is_valid_truth_tick(truth_last, truth_venue, truth_size, truth_timestamp):
    # TTL check (e.g., 60 seconds)
    if time.time() - truth_timestamp > 60:
        return False  # Stale data!
    
    # ... rest of validation
```

---

## 📊 SORUN ÖZETİ

| # | Sorun | Severity | Impact |
|---|-------|----------|--------|
| 1 | **market_data_cache Race Condition** | 🔴 CRITICAL | Data corruption, wrong prices |
| 2 | **Account Context Race** | 🔴 CRITICAL | Orders to wrong account! |
| 3 | **XNL Multiple Start** | 🟠 HIGH | Duplicate orders |
| 4 | **Proposal Cycle ID Conflict** | 🟠 HIGH | Confusion, wrong potential_qty |
| 5 | **Potential_qty Cascade Broken** | 🟡 MEDIUM | Incorrect order sizing |
| 6 | **Truth Tick Stale Data** | 🟡 MEDIUM | Frontlama on old data |

---

## ✅ ÖNCELİKLİ FIX SIRASI

### 1. HEMEN (CRITICAL):
- ✅ market_data_cache lock ekle
- ✅ Account context lock ekle (Dual Process)

### 2. YAKIN GELECEK (HIGH):
- ✅ XNL start lock ekle
- ✅ RUNALL ↔ XNL mutual exclusion

### 3. ORTA VADE (MEDIUM):
- ✅ Potential_qty cascade düzelt
- ✅ Truth tick timestamp ekle

