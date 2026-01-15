# PSFALGO Quant_Engine Implementation Guide

## 📋 GENEL BAKIŞ

Bu doküman, Quant_Engine için profesyonel, akışkan ve explainable bir RUNALL mimarisinin nasıl kurulacağını detaylandırır. Janall'daki mantık korunur, ancak UI hackleri, monolitik loop'lar ve global state karmaşasından kaçınılır.

---

## 1. PROFESYONEL RUNALL SKELETON

### 1.1. RUNALL = Sadece Orchestrator

**RUNALL'ın Sorumlulukları:**
- ✅ Cycle timing ve orchestration
- ✅ State management
- ✅ Decision engine coordination
- ✅ Metrics collection
- ✅ State publishing

**RUNALL'ın YAPMADIĞI:**
- ❌ Trading kararları vermez (decision engine'lere bırakır)
- ❌ Emir göndermez (execution engine'e bırakır)
- ❌ Position yönetimi yapmaz (position manager'a bırakır)
- ❌ Metrics hesaplamaz (market data pipeline'a bırakır)

### 1.2. Non-Blocking Decision Engines

**ÖNEMLİ**: Decision engine'ler `await` ile **BLOKLANMAZ**. Her decision engine:

1. **Stateless** çalışır (sadece input alır, output verir)
2. **Deterministic** çalışır (aynı input → aynı output)
3. **Async** çalışır (ama blocking değil)
4. **Fast** çalışır (< 1 saniye)

```python
# ✅ DO: Decision engine async ama hızlı
async def karbotu_decision_engine(request: DecisionRequest) -> DecisionResponse:
    # Hızlı hesaplama (< 1 saniye)
    decisions = []
    for position in request.positions:
        # Filtreleme ve karar üretme
        decision = make_decision(position, request.metrics)
        decisions.append(decision)
    return DecisionResponse(decisions=decisions)

# ❌ DON'T: Decision engine'i bloklama
# await karbotu_decision_engine(request)  # Bu zaten async, ama hızlı olmalı
```

### 1.3. Deterministic Cycle Timing

**Cycle Interval**: Config'ten gelir (örn: 30-60 saniye)

```python
# Config
{
    "cycle_interval_seconds": 60,  # Her 60 saniyede bir cycle
    "dry_run_mode": true
}

# Cycle timing
cycle_start = datetime.now()
# ... decision engines run ...
cycle_end = datetime.now()
cycle_duration = (cycle_end - cycle_start).total_seconds()

# Deterministic wait
remaining_time = cycle_interval - cycle_duration
if remaining_time > 0:
    await asyncio.sleep(remaining_time)  # Exact timing
else:
    # Overrun detected - log warning
    logger.warning(f"Cycle overrun: {cycle_duration:.2f}s > {cycle_interval}s")
```

### 1.4. Cycle Skeleton (Özet)

```python
async def _cycle_loop(self):
    """Main cycle loop"""
    while self.loop_running:
        cycle_start = datetime.now()
        self.loop_count += 1
        
        try:
            # 1. Update exposure
            await self._step_update_exposure()
            
            # 2. Determine mode
            mode = self._determine_exposure_mode()
            
            # 3. Run decision engine (non-blocking, but await for result)
            if mode == 'OFANSIF':
                await self._step_run_karbotu()  # Fast async call
            else:
                await self._step_run_reducemore()
            
            # 4. Run ADDNEWPOS if eligible
            if self._is_addnewpos_eligible():
                await self._step_run_addnewpos()
            
            # 5. Collect metrics
            await self._collect_cycle_metrics()
            
            # 6. Wait for next cycle (deterministic)
            await self._wait_for_next_cycle(cycle_start)
            
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            await asyncio.sleep(5)  # Retry after 5s
```

---

## 2. MINIMAL AMA YETERLİ STATE & METRICS

### 2.1. ExposureSnapshot

```python
@dataclass
class ExposureSnapshot:
    pot_total: float  # Total exposure
    pot_max: float  # Max limit
    long_lots: float  # Long positions
    short_lots: float  # Short positions
    net_exposure: float  # long - short
    timestamp: datetime
    
    @property
    def exposure_ratio(self) -> float:
        return self.pot_total / self.pot_max if self.pot_max > 0 else 0.0
    
    @property
    def is_over_limit(self) -> bool:
        return self.pot_total >= self.pot_max
```

**Kullanım:**
- Mode determination (OFANSIF/DEFANSIF)
- ADDNEWPOS eligibility
- Risk monitoring

### 2.2. CycleMetrics

```python
@dataclass
class CycleMetrics:
    loop_count: int
    cycle_start_time: datetime
    cycle_duration_seconds: float
    exposure_snapshot: Optional[ExposureSnapshot]
    karbotu_decisions: int
    reducemore_decisions: int
    addnewpos_decisions: int
    error: Optional[str]
    timestamp: datetime
```

**Kullanım:**
- Performance monitoring
- Overrun detection
- Error tracking

### 2.3. RUNALL State Machine

```python
# Global State
class RunallState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING = "WAITING"  # Waiting for decision engine
    BLOCKED = "BLOCKED"
    CANCELLING = "CANCELLING"
    ERROR = "ERROR"

# Cycle Sub-State
class CycleState(str, Enum):
    INIT = "INIT"
    EXPOSURE_CHECK = "EXPOSURE_CHECK"
    KARBOTU_RUNNING = "KARBOTU_RUNNING"
    REDUCEMORE_RUNNING = "REDUCEMORE_RUNNING"
    ADDNEWPOS_CHECK = "ADDNEWPOS_CHECK"
    ADDNEWPOS_RUNNING = "ADDNEWPOS_RUNNING"
    METRICS_COLLECT = "METRICS_COLLECT"
    WAITING_NEXT = "WAITING_NEXT"
```

---

## 3. TEMİZ SINIRLAR

### 3.1. RUNALL → Decision Engines

```
RUNALL (Orchestrator)
    ↓
    prepare DecisionRequest
    ↓
Decision Engine (Stateless)
    ↓
    returns DecisionResponse
    ↓
RUNALL (Orchestrator)
    ↓
    publish decisions
```

**Sınır:**
- RUNALL decision engine'e **sadece input verir**
- Decision engine **sadece output verir**
- **Hiçbir global state paylaşılmaz**

### 3.2. Decision Engine'ler Stateless

```python
# ✅ DO: Stateless decision engine
async def karbotu_decision_engine(request: DecisionRequest) -> DecisionResponse:
    """
    Stateless - sadece input alır, output verir.
    Aynı input → her zaman aynı output.
    """
    decisions = []
    for position in request.positions:
        # Decision logic (stateless)
        decision = make_decision(position, request.metrics)
        decisions.append(decision)
    return DecisionResponse(decisions=decisions)

# ❌ DON'T: Global state kullanma
# global_state = {}  # ❌ YOK!
# self.cache = {}  # ❌ YOK!
```

### 3.3. Explainability Her Decision Engine'den

```python
@dataclass
class Decision:
    symbol: str
    action: str
    reason: str  # Neden bu karar?
    filter_reasons: List[str]  # Neden filtrelendi?
    metrics_used: Dict[str, float]  # Hangi metrics kullanıldı?
    confidence: float  # Güven skoru
```

**Her decision kendi explainability'sini içerir.**

---

## 4. EKSİK YAPILAR (Janall'da var, Quant_Engine'de yok)

### 4.1. Exposure Snapshot ❌ EKSİK

**Janall'da:**
- `check_exposure_limits_async()` fonksiyonu var
- Pot Total, Pot Max hesaplanıyor
- Mode (OFANSIF/DEFANSIF) belirleniyor

**Quant_Engine'de:**
- ❌ Position manager yok
- ❌ Exposure calculation yok
- ✅ **YAPILMASI GEREKEN**: `ExposureSnapshot` data model + calculation logic

### 4.2. Cycle History ❌ EKSİK

**Janall'da:**
- `loop_report` var
- Cycle bazlı raporlama var
- Döngü sayacı var

**Quant_Engine'de:**
- ❌ Cycle history storage yok
- ❌ Cycle bazlı raporlama yok
- ✅ **YAPILMASI GEREKEN**: `CycleMetrics` storage + API endpoint

### 4.3. Deterministic Clock / Overrun Detection ❌ EKSİK

**Janall'da:**
- `after(120000)` ile 2 dakika bekleme var
- Ama overrun detection yok

**Quant_Engine'de:**
- ❌ Deterministic timing yok
- ❌ Overrun detection yok
- ✅ **YAPILMASI GEREKEN**: Cycle timing logic + overrun detection

### 4.4. Config-Driven PSFALGO Rules ❌ EKSİK

**Janall'da:**
- KARBOTU/REDUCEMORE kuralları kod içinde hardcoded
- Lot yüzdeleri, Fbtot threshold'ları hardcoded

**Quant_Engine'de:**
- ❌ Config-driven rules yok
- ✅ **YAPILMASI GEREKEN**: `psfalgo_rules.yaml` + rule loader

### 4.5. Position Snapshot ❌ EKSİK

**Janall'da:**
- Position'lar IBKR/Hammer'dan alınıyor
- Take Profit panel'lerde gösteriliyor

**Quant_Engine'de:**
- ❌ Position manager yok
- ❌ Position snapshot yok
- ✅ **YAPILMASI GEREKEN**: Position manager + snapshot API

### 4.6. Metrics Snapshot ❌ EKSİK

**Janall'da:**
- `mini450` dataframe'den metrics alınıyor
- Fbtot, Ask Sell Pahalılık, vb. hesaplanıyor

**Quant_Engine'de:**
- ✅ Market data cache var
- ❌ Metrics snapshot aggregation yok
- ✅ **YAPILMASI GEREKEN**: Metrics snapshot API (market data cache'den aggregate)

---

## 5. DO / DON'T LİSTESİ

### 5.1. DO ✅

#### **State Management**
- ✅ **DO**: State'i dataclass'larla modelle (immutable)
- ✅ **DO**: State'i Redis'e publish et (distributed)
- ✅ **DO**: State machine enum'ları kullan (type-safe)
- ✅ **DO**: Cycle metrics'i topla ve sakla

#### **Decision Engines**
- ✅ **DO**: Decision engine'leri stateless yap
- ✅ **DO**: Input/Output modellerini net tanımla
- ✅ **DO**: Her decision için explanation üret
- ✅ **DO**: Decision engine'leri async yap (ama hızlı)

#### **Timing**
- ✅ **DO**: Deterministic cycle timing kullan
- ✅ **DO**: Overrun detection yap
- ✅ **DO**: Cycle interval'i config'ten al
- ✅ **DO**: Cycle duration'ı logla

#### **Error Handling**
- ✅ **DO**: Try-catch ile error handling yap
- ✅ **DO**: Error'ları state'e kaydet
- ✅ **DO**: Error sonrası retry mekanizması ekle
- ✅ **DO**: Error'ları logla ve publish et

#### **Publishing**
- ✅ **DO**: State'i Redis pub/sub ile publish et
- ✅ **DO**: Decisions'ı WebSocket ile broadcast et
- ✅ **DO**: Metrics'i periyodik publish et
- ✅ **DO**: Diff publishing kullan (sadece değişenler)

### 5.2. DON'T ❌

#### **State Management**
- ❌ **DON'T**: Global mutable state kullanma
- ❌ **DON'T**: Thread-local state kullanma
- ❌ **DON'T**: State'i UI thread'inde tutma
- ❌ **DON'T**: State'i file system'de tutma (Redis kullan)

#### **Decision Engines**
- ❌ **DON'T**: Decision engine'lerde global state kullanma
- ❌ **DON'T**: Decision engine'leri blocking yapma
- ❌ **DON'T**: Decision engine'lerde side effect yapma (DB write, vb.)
- ❌ **DON'T**: Decision engine'lerde UI update yapma

#### **Timing**
- ❌ **DON'T**: `time.sleep()` kullanma (async/await kullan)
- ❌ **DON'T**: Cycle timing'i hardcode etme (config'ten al)
- ❌ **DON'T**: Overrun'ı ignore etme (logla ve uyar)
- ❌ **DON'T**: Cycle'ları overlap ettirme (deterministic timing)

#### **Error Handling**
- ❌ **DON'T**: Error'ları silent fail yapma
- ❌ **DON'T**: Error sonrası state'i inconsistent bırakma
- ❌ **DON'T**: Error'ları UI'da gösterme (log + publish)
- ❌ **DON'T**: Error recovery yapmadan devam etme

#### **Publishing**
- ❌ **DON'T**: Full state'i her seferinde publish etme (diff kullan)
- ❌ **DON'T**: Publishing'i blocking yapma (async)
- ❌ **DON'T**: Publishing'i UI thread'inde yapma
- ❌ **DON'T**: Publishing'i skip etme (her zaman publish et)

#### **Janall'daki Hatalar (Tekrar Etme)**
- ❌ **DON'T**: `after()` kullanma (async/await kullan)
- ❌ **DON'T**: `safe_ui_call()` kullanma (WebSocket kullan)
- ❌ **DON'T**: Threading kullanma (async/await kullan)
- ❌ **DON'T**: Global mutable state kullanma (dataclass kullan)
- ❌ **DON'T**: Monolitik loop'lar yazma (modüler yap)
- ❌ **DON'T**: UI hackleri yapma (clean architecture)

---

## 6. UYGULAMA ADIMLARI

### Adım 1: Data Models ✅
- [x] `decision_models.py` oluştur
- [x] `ExposureSnapshot` tanımla
- [x] `CycleMetrics` tanımla
- [x] `DecisionRequest/Response` tanımla
- [x] State enum'ları tanımla

### Adım 2: RUNALL Engine ✅
- [x] `runall_engine.py` skeleton oluştur
- [x] Cycle loop implementasyonu
- [x] State management
- [x] Timing logic
- [ ] Redis pub/sub entegrasyonu
- [ ] WebSocket broadcast entegrasyonu

### Adım 3: Position Manager (EKSİK)
- [ ] Position manager oluştur
- [ ] Position snapshot API
- [ ] Exposure calculation logic
- [ ] IBKR/Hammer entegrasyonu

### Adım 4: Metrics Snapshot (EKSİK)
- [ ] Metrics snapshot API
- [ ] Market data cache aggregation
- [ ] Symbol metrics mapping

### Adım 5: Decision Engines (EKSİK)
- [ ] `karbotu_engine.py` - 13 adımlı decision engine
- [ ] `reducemore_engine.py` - KARBOTU ile aynı mantık
- [ ] `addnewpos_engine.py` - Yeni pozisyon açma logic

### Adım 6: Config (EKSİK)
- [ ] `psfalgo_rules.yaml` oluştur
- [ ] Rule loader
- [ ] Config validation

### Adım 7: API Endpoints (EKSİK)
- [ ] `/psfalgo/runall/start` - RUNALL başlat
- [ ] `/psfalgo/runall/stop` - RUNALL durdur
- [ ] `/psfalgo/state` - State al
- [ ] `/psfalgo/decisions/{loop_count}` - Decisions al
- [ ] `/psfalgo/metrics` - Metrics al

### Adım 8: Frontend Integration (EKSİK)
- [ ] PSFALGO state display
- [ ] Decision table
- [ ] Explanation panel
- [ ] Cycle history

---

## 7. EKSİK YAPILAR DETAYLI LİSTESİ

### 7.1. Position Manager Integration ✅ VAR (ama entegrasyon eksik)

**Mevcut:**
- ✅ `app/engine/position_manager.py` var
- ✅ `app/psfalgo/position_snapshot_engine.py` var
- ✅ Position tracking mekanizması var

**Eksik:**
- ❌ `get_position_snapshot()` async API yok
- ❌ Position snapshot formatı `PositionSnapshot` dataclass'a uygun değil
- ❌ Exposure calculation `ExposureSnapshot` formatında değil

**Yapılması Gereken:**
```python
# position_manager.py'ye ekle
async def get_position_snapshot(self) -> List[PositionSnapshot]:
    """Get position snapshot in PositionSnapshot format"""
    positions = self.get_all_positions()
    return [
        PositionSnapshot(
            symbol=pos['symbol'],
            qty=pos['qty'],
            avg_price=pos['avg_price'],
            current_price=pos['current_price'],
            unrealized_pnl=pos['unrealized_pnl'],
            group=pos.get('group'),
            cgrup=pos.get('cgrup')
        )
        for pos in positions
    ]
```

### 7.2. Metrics Snapshot API ❌ EKSİK

**Mevcut:**
- ✅ Market data cache var (`market_data_cache`)
- ✅ Pricing overlay engine var
- ✅ GRPAN/RWVAP metrics var

**Eksik:**
- ❌ Metrics snapshot aggregation API yok
- ❌ `SymbolMetrics` dataclass formatında metrics yok
- ❌ Batch metrics fetch yok

**Yapılması Gereken:**
```python
# metrics_snapshot_api.py oluştur
async def get_metrics_snapshot(symbols: List[str]) -> Dict[str, SymbolMetrics]:
    """Get metrics snapshot for symbols"""
    snapshot = {}
    for symbol in symbols:
        # Aggregate from market_data_cache, pricing_overlay, grpan, rwvap
        metrics = SymbolMetrics(
            symbol=symbol,
            bid=market_data_cache[symbol].get('bid'),
            ask=market_data_cache[symbol].get('ask'),
            # ... diğer metrics
        )
        snapshot[symbol] = metrics
    return snapshot
```

### 7.3. Config-Driven PSFALGO Rules ❌ EKSİK

**Mevcut:**
- ✅ `app/config/psfalgo_rules.yaml` dosyası var (ama içi boş olabilir)

**Eksik:**
- ❌ KARBOTU/REDUCEMORE kuralları config'de yok
- ❌ Lot yüzdeleri config'de yok
- ❌ Fbtot threshold'ları config'de yok
- ❌ Rule loader yok

**Yapılması Gereken:**
```yaml
# psfalgo_rules.yaml
karbotu:
  steps:
    - step: 2
      name: "Fbtot < 1.10"
      condition:
        fbtot_lt: 1.10
        ask_sell_pahalilik_gt: -0.10
      lot_percentage: 50
      order_type: "ASK_SELL"
    - step: 3
      name: "Fbtot 1.11-1.45 (low)"
      condition:
        fbtot_range: [1.11, 1.45]
        ask_sell_pahalilik_range: [-0.05, 0.04]
      lot_percentage: 25
      order_type: "ASK_SELL"
    # ... diğer adımlar

reducemore:
  # KARBOTU ile aynı ama lot_percentage'ler daha düşük
  steps:
    - step: 2
      lot_percentage: 25  # KARBOTU'da 50, burada 25
    # ...

addnewpos:
  eligibility:
    pot_total_lt_pot_max: true
    exposure_mode: "OFANSIF"
  filters:
    bid_buy_ucuzluk_gt: 0.06
    fbtot_gt: 1.10
    spread_lt: 0.05
    avg_adv_gt: 1000
```

### 7.4. Cycle History Storage ❌ EKSİK

**Mevcut:**
- ✅ `CycleMetrics` dataclass var
- ✅ `cycle_metrics` list var (in-memory)

**Eksik:**
- ❌ Persistent storage yok (Redis veya SQLite)
- ❌ Cycle history API yok
- ❌ Cycle bazlı raporlama yok

**Yapılması Gereken:**
```python
# cycle_history_store.py oluştur
class CycleHistoryStore:
    def __init__(self):
        self.redis_client = get_redis_client()
    
    async def save_cycle_metrics(self, metrics: CycleMetrics):
        """Save cycle metrics to Redis"""
        key = f"psfalgo:cycle:{metrics.loop_count}"
        await self.redis_client.set(key, json.dumps(asdict(metrics)), ex=86400*7)  # 7 days
    
    async def get_cycle_metrics(self, loop_count: int) -> Optional[CycleMetrics]:
        """Get cycle metrics from Redis"""
        key = f"psfalgo:cycle:{loop_count}"
        data = await self.redis_client.get(key)
        if data:
            return CycleMetrics(**json.loads(data))
        return None
    
    async def get_recent_cycles(self, last_n: int = 10) -> List[CycleMetrics]:
        """Get last N cycles"""
        # Redis'den son N cycle'ı al
        # ...
```

### 7.5. Deterministic Clock / Overrun Detection ✅ KISMEN VAR

**Mevcut:**
- ✅ `_wait_for_next_cycle()` fonksiyonu var
- ✅ Overrun detection logic var

**Eksik:**
- ❌ Overrun metrics'i `CycleMetrics`'e kaydedilmiyor
- ❌ Overrun alerting yok

**Yapılması Gereken:**
```python
# runall_engine.py'de
async def _wait_for_next_cycle(self, cycle_start: datetime):
    cycle_end = datetime.now()
    cycle_duration = (cycle_end - cycle_start).total_seconds()
    remaining_time = self.cycle_interval - cycle_duration
    
    if remaining_time < 0:
        # Overrun detected
        logger.warning(f"Cycle {self.loop_count} overrun: {cycle_duration:.2f}s > {self.cycle_interval}s")
        # Metrics'e kaydet
        self.current_cycle_metrics.is_overrun = True  # ✅ EKLE
        return
    
    await asyncio.sleep(remaining_time)
```

---

## 8. DO / DON'T LİSTESİ (DETAYLI)

### 8.1. DO ✅

#### **State Management**
- ✅ **DO**: State'i dataclass'larla modelle (immutable, type-safe)
- ✅ **DO**: State'i Redis'e publish et (distributed, persistent)
- ✅ **DO**: State machine enum'ları kullan (type-safe, IDE autocomplete)
- ✅ **DO**: Cycle metrics'i topla ve sakla (performance monitoring)
- ✅ **DO**: State transitions'i logla (audit trail)
- ✅ **DO**: State'i periyodik publish et (her 1 saniyede bir)

#### **Decision Engines**
- ✅ **DO**: Decision engine'leri stateless yap (testable, deterministic)
- ✅ **DO**: Input/Output modellerini net tanımla (type-safe)
- ✅ **DO**: Her decision için explanation üret (explainability)
- ✅ **DO**: Decision engine'leri async yap (ama hızlı, < 1s)
- ✅ **DO**: Decision engine'lerde error handling yap (graceful degradation)
- ✅ **DO**: Decision engine'lerde validation yap (input validation)

#### **Timing**
- ✅ **DO**: Deterministic cycle timing kullan (exact intervals)
- ✅ **DO**: Overrun detection yap (performance monitoring)
- ✅ **DO**: Cycle interval'i config'ten al (flexible)
- ✅ **DO**: Cycle duration'ı logla (performance tracking)
- ✅ **DO**: Next cycle time'ı hesapla ve publish et (UI için)

#### **Error Handling**
- ✅ **DO**: Try-catch ile error handling yap (robust)
- ✅ **DO**: Error'ları state'e kaydet (error tracking)
- ✅ **DO**: Error sonrası retry mekanizması ekle (resilience)
- ✅ **DO**: Error'ları logla ve publish et (monitoring)
- ✅ **DO**: Error recovery yap (state'i consistent tut)

#### **Publishing**
- ✅ **DO**: State'i Redis pub/sub ile publish et (distributed)
- ✅ **DO**: Decisions'ı WebSocket ile broadcast et (real-time UI)
- ✅ **DO**: Metrics'i periyodik publish et (monitoring)
- ✅ **DO**: Diff publishing kullan (sadece değişenler, performance)
- ✅ **DO**: Publishing'i async yap (non-blocking)

#### **Architecture**
- ✅ **DO**: Clean separation of concerns (RUNALL orchestration, decision engines, execution)
- ✅ **DO**: Dependency injection kullan (testable)
- ✅ **DO**: Config-driven yap (flexible, no hardcode)
- ✅ **DO**: Logging yap (debugging, monitoring)
- ✅ **DO**: Type hints kullan (type safety, IDE support)

### 8.2. DON'T ❌

#### **State Management**
- ❌ **DON'T**: Global mutable state kullanma (race conditions, bugs)
- ❌ **DON'T**: Thread-local state kullanma (async/await kullan)
- ❌ **DON'T**: State'i UI thread'inde tutma (separation of concerns)
- ❌ **DON'T**: State'i file system'de tutma (Redis kullan, distributed)
- ❌ **DON'T**: State'i memory-only tutma (persistent storage kullan)
- ❌ **DON'T**: State transitions'i skip etme (her transition logla)

#### **Decision Engines**
- ❌ **DON'T**: Decision engine'lerde global state kullanma (stateless olmalı)
- ❌ **DON'T**: Decision engine'leri blocking yapma (async, hızlı)
- ❌ **DON'T**: Decision engine'lerde side effect yapma (DB write, file write)
- ❌ **DON'T**: Decision engine'lerde UI update yapma (separation of concerns)
- ❌ **DON'T**: Decision engine'lerde caching yapma (stateless olmalı)
- ❌ **DON'T**: Decision engine'lerde error'ı silent fail yapma (logla)

#### **Timing**
- ❌ **DON'T**: `time.sleep()` kullanma (async/await kullan, `asyncio.sleep()`)
- ❌ **DON'T**: Cycle timing'i hardcode etme (config'ten al)
- ❌ **DON'T**: Overrun'ı ignore etme (logla, uyar, metrics'e kaydet)
- ❌ **DON'T**: Cycle'ları overlap ettirme (deterministic timing)
- ❌ **DON'T**: Cycle timing'i UI thread'inde yapma (background task)

#### **Error Handling**
- ❌ **DON'T**: Error'ları silent fail yapma (logla, publish et)
- ❌ **DON'T**: Error sonrası state'i inconsistent bırakma (error recovery)
- ❌ **DON'T**: Error'ları UI'da gösterme (log + publish, UI WebSocket'ten alır)
- ❌ **DON'T**: Error recovery yapmadan devam etme (state'i consistent tut)
- ❌ **DON'T**: Error'ları retry etmeden fail etme (resilience)

#### **Publishing**
- ❌ **DON'T**: Full state'i her seferinde publish etme (diff kullan, performance)
- ❌ **DON'T**: Publishing'i blocking yapma (async)
- ❌ **DON'T**: Publishing'i UI thread'inde yapma (background task)
- ❌ **DON'T**: Publishing'i skip etme (her zaman publish et, monitoring için)
- ❌ **DON'T**: Publishing'i error'da skip etme (error state'i de publish et)

#### **Janall'daki Hatalar (Tekrar Etme)**
- ❌ **DON'T**: `after()` kullanma (async/await kullan)
- ❌ **DON'T**: `safe_ui_call()` kullanma (WebSocket kullan)
- ❌ **DON'T**: Threading kullanma (async/await kullan)
- ❌ **DON'T**: Global mutable state kullanma (dataclass kullan)
- ❌ **DON'T**: Monolitik loop'lar yazma (modüler yap)
- ❌ **DON'T**: UI hackleri yapma (clean architecture)
- ❌ **DON'T**: Callback karmaşası yapma (async/await kullan)
- ❌ **DON'T**: Blocking işlemler yapma (async/await kullan)
- ❌ **DON'T**: Hardcode değerler kullanma (config'ten al)

---

## 9. SONUÇ

Bu tasarım, Janall'daki PSFALGO mantığını **birebir koruyarak**, ancak **daha profesyonel, akışkan, güvenli ve explainable** bir şekilde Quant_Engine'e taşır.

### 9.1. Ana Prensipler

1. ✅ **RUNALL = Sadece Orchestrator** (karar vermez, sadece koordine eder)
2. ✅ **Decision Engines = Stateless** (input/output, deterministic)
3. ✅ **Non-Blocking** (async/await, hızlı decision engines)
4. ✅ **Deterministic** (aynı input → aynı output, testable)
5. ✅ **Config-Driven** (hardcode yok, flexible)
6. ✅ **Explainable** (her decision için reason, filter reasons)
7. ✅ **Clean Architecture** (temiz sınırlar, separation of concerns)

### 9.2. Eksik Yapılar (Öncelik Sırasına Göre)

#### **Yüksek Öncelik (Hemen Yapılmalı)**
1. ❌ **Position Snapshot API**: `position_manager.py`'ye `get_position_snapshot()` ekle
2. ❌ **Metrics Snapshot API**: `get_metrics_snapshot()` fonksiyonu oluştur
3. ❌ **Exposure Calculation**: `ExposureSnapshot` formatında exposure hesapla

#### **Orta Öncelik (Sonra Yapılabilir)**
4. ❌ **Config-Driven Rules**: `psfalgo_rules.yaml` doldur + rule loader
5. ❌ **Cycle History Storage**: Redis'te cycle metrics saklama
6. ❌ **Overrun Metrics**: Overrun'ı `CycleMetrics`'e kaydet

#### **Düşük Öncelik (Nice to Have)**
7. ❌ **Cycle History API**: Cycle bazlı raporlama endpoint'leri
8. ❌ **Overrun Alerting**: Overrun için alert mekanizması

### 9.3. Hazır Dosyalar

✅ **Oluşturulan Dosyalar:**
1. `quant_engine/app/psfalgo/runall_engine.py` - RUNALL skeleton
2. `quant_engine/app/psfalgo/decision_models.py` - Data models
3. `PSFALGO_QUANT_ENGINE_IMPLEMENTATION_GUIDE.md` - Implementation guide

### 9.4. Sonraki Adımlar

1. **Position Snapshot API**: `position_manager.py`'ye entegre et
2. **Metrics Snapshot API**: Market data cache'den aggregate et
3. **KARBOTU Engine**: 13 adımlı decision engine implement et
4. **REDUCEMORE Engine**: KARBOTU ile aynı mantık
5. **ADDNEWPOS Engine**: Yeni pozisyon açma logic
6. **Config Rules**: `psfalgo_rules.yaml` doldur
7. **API Endpoints**: FastAPI endpoints ekle
8. **Frontend Integration**: UI'da PSFALGO state display

---

**Özet**: Bu tasarım, Janall'daki PSFALGO'yu **birebir mantıkla** ama **modern, profesyonel, akışkan ve explainable** bir şekilde Quant_Engine'e taşır. UI hackleri, monolitik loop'lar ve global state karmaşasından kaçınır.

