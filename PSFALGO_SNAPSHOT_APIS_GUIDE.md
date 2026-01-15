# PSFALGO Snapshot APIs - Production Guide

## 📋 GENEL BAKIŞ

Bu doküman, PSFALGO için production-grade snapshot API'lerinin nasıl kullanılacağını detaylandırır. Tüm API'ler async, consistent ve decision engine'ler için optimize edilmiştir.

---

## 1. POSITION SNAPSHOT API

### 1.1. Kullanım

```python
from app.psfalgo.position_snapshot_api import get_position_snapshot_api

# Get position snapshot
position_api = get_position_snapshot_api()
if position_api:
    positions = await position_api.get_position_snapshot()
    # Returns: List[PositionSnapshot]
```

### 1.2. PositionSnapshot Dataclass

```python
@dataclass
class PositionSnapshot:
    symbol: str
    qty: float  # Positive = Long, Negative = Short
    avg_price: float
    current_price: float
    unrealized_pnl: float
    group: Optional[str]  # PRIMARY GROUP
    cgrup: Optional[str]  # SECONDARY GROUP (CGRUP)
    position_open_ts: Optional[datetime]  # When position was opened
    holding_minutes: float  # How long position has been held (minutes)
    timestamp: datetime
    
    # Properties
    @property
    def is_long(self) -> bool
    @property
    def is_short(self) -> bool
    @property
    def pnl_percent(self) -> float
    @property
    def holding_hours(self) -> float
    @property
    def holding_days(self) -> float
```

### 1.3. Özellikler

- ✅ **Async**: Non-blocking position snapshot
- ✅ **Enriched**: Market data + static data + holding time
- ✅ **Group Info**: PRIMARY GROUP + CGRUP (for heldkuponlu)
- ✅ **Holding Time**: `position_open_ts` + `holding_minutes`
- ✅ **Exposure-Ready**: Directly usable for exposure calculation

### 1.4. Initialization

```python
from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api
from app.engine.position_manager import PositionManager
from app.market_data.static_data_store import StaticDataStore

# Initialize
initialize_position_snapshot_api(
    position_manager=position_manager,
    static_store=static_store,
    market_data_cache=market_data_cache
)
```

---

## 2. METRICS SNAPSHOT API

### 2.1. Kullanım

```python
from app.psfalgo.metrics_snapshot_api import get_metrics_snapshot_api

# Get metrics snapshot for symbols
metrics_api = get_metrics_snapshot_api()
if metrics_api:
    symbols = ['WFC PRY', 'BAC PRM', ...]
    metrics = await metrics_api.get_metrics_snapshot(symbols, snapshot_ts=datetime.now())
    # Returns: Dict[str, SymbolMetrics]
```

### 2.2. SymbolMetrics Dataclass

```python
@dataclass
class SymbolMetrics:
    symbol: str
    timestamp: datetime
    
    # Pricing
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    prev_close: Optional[float]
    spread: Optional[float]
    spread_percent: Optional[float]
    
    # GRPAN
    grpan_price: Optional[float]
    grpan_concentration_percent: Optional[float]
    grpan_ort_dev: Optional[float]  # GOD
    
    # RWVAP
    rwvap_1d: Optional[float]
    rwvap_ort_dev: Optional[float]  # ROD
    
    # Janall Metrics
    fbtot: Optional[float]
    sfstot: Optional[float]
    gort: Optional[float]
    sma63_chg: Optional[float]
    sma246_chg: Optional[float]
    
    # Pricing Overlay
    bid_buy_ucuzluk: Optional[float]
    ask_sell_pahalilik: Optional[float]
    front_buy_ucuzluk: Optional[float]
    front_sell_pahalilik: Optional[float]
    
    # Static
    avg_adv: Optional[float]
    final_thg: Optional[float]
    short_final: Optional[float]
```

### 2.3. Özellikler

- ✅ **Single Entry Point**: Decision engine'lerin TEK giriş noktası
- ✅ **Aggregated**: Market data + GRPAN + RWVAP + pricing_overlay + Janall metrics
- ✅ **Consistent**: Same `snapshot_ts` ensures consistency
- ✅ **Complete**: All metrics needed for decision making

### 2.4. Initialization

```python
from app.psfalgo.metrics_snapshot_api import initialize_metrics_snapshot_api

# Initialize
initialize_metrics_snapshot_api(
    market_data_cache=market_data_cache,
    static_store=static_store,
    grpan_engine=grpan_engine,
    rwvap_engine=rwvap_engine,
    pricing_overlay_engine=pricing_overlay_engine,
    janall_metrics_engine=janall_metrics_engine
)
```

---

## 3. EXPOSURE CALCULATOR

### 3.1. Kullanım

```python
from app.psfalgo.exposure_calculator import get_exposure_calculator

# Calculate exposure
exposure_calculator = get_exposure_calculator()
if exposure_calculator:
    exposure = exposure_calculator.calculate_exposure(positions)
    # Returns: ExposureSnapshot
    
    # Determine mode
    mode = exposure_calculator.determine_exposure_mode(exposure)
    # Returns: 'OFANSIF' or 'DEFANSIF'
```

### 3.2. ExposureSnapshot Dataclass

```python
@dataclass
class ExposureSnapshot:
    pot_total: float  # Total exposure (sum of |qty| * price)
    pot_max: float  # Maximum exposure limit
    long_lots: float  # Total long lots
    short_lots: float  # Total short lots
    net_exposure: float  # long_lots - short_lots
    timestamp: datetime
    
    # Properties
    @property
    def exposure_ratio(self) -> float  # pot_total / pot_max
    @property
    def is_over_limit(self) -> bool
    @property
    def long_short_ratio(self) -> float
```

### 3.3. Özellikler

- ✅ **Simple**: Minimal but sufficient
- ✅ **Config-Driven**: `pot_max` from config
- ✅ **Mode Determination**: OFANSIF/DEFANSIF logic

### 3.4. Initialization

```python
from app.psfalgo.exposure_calculator import initialize_exposure_calculator

# Initialize with config
initialize_exposure_calculator(config={
    'pot_max_lot': 63636  # Default
})
```

---

## 4. RUNALL ENTEGRASYONU

### 4.1. Snapshot Consistency

**ÖNEMLİ**: Aynı cycle'da aynı snapshot timestamp kullanılır.

```python
# RUNALL cycle'da
snapshot_ts = datetime.now()  # Tek bir timestamp

# Step 1: Update exposure
positions = await position_api.get_position_snapshot()  # snapshot_ts kullanılmaz (position manager'dan gelir)
exposure = exposure_calculator.calculate_exposure(positions)

# Step 2: Prepare decision request
positions = await position_api.get_position_snapshot()  # Aynı cycle, aynı positions
metrics = await metrics_api.get_metrics_snapshot(symbols, snapshot_ts=snapshot_ts)  # Consistent timestamp
```

### 4.2. RUNALL Cycle Adımları

```
Cycle Start
    ↓
Step 1: Update Exposure
    - Get position snapshot
    - Calculate exposure
    - Store exposure snapshot
    ↓
Step 2: Determine Mode
    - OFANSIF or DEFANSIF
    ↓
Step 3: Run Decision Engine
    - Get position snapshot (same cycle)
    - Get metrics snapshot (same snapshot_ts)
    - Prepare DecisionRequest
    - Run decision engine
    ↓
Step 4: Collect Metrics
    - Store cycle metrics
```

### 4.3. DecisionRequest Format

```python
@dataclass
class DecisionRequest:
    positions: List[PositionSnapshot]  # PositionSnapshot objects
    metrics: Dict[str, SymbolMetrics]  # SymbolMetrics objects
    exposure: Optional[ExposureSnapshot]
    cycle_count: int
    available_symbols: Optional[List[str]]  # For ADDNEWPOS only
    snapshot_ts: Optional[datetime]  # Snapshot timestamp (for consistency)
```

---

## 5. DECISION COOLDOWN (BONUS)

### 5.1. Kullanım

```python
from app.psfalgo.decision_cooldown import get_decision_cooldown_manager

# Check cooldown
cooldown_manager = get_decision_cooldown_manager()
if cooldown_manager:
    if cooldown_manager.can_make_decision(symbol):
        # Make decision
        decision = make_decision(...)
        # Record decision
        cooldown_manager.record_decision(symbol)
    else:
        # Cooldown active
        time_since_last = cooldown_manager.get_time_since_last_decision(symbol)
        logger.debug(f"{symbol}: Cooldown active ({time_since_last:.1f} minutes)")
```

### 5.2. Özellikler

- ✅ **Per-Symbol**: Her symbol için ayrı cooldown
- ✅ **Configurable**: Cooldown minutes config'ten
- ✅ **Time Tracking**: Time since last decision

### 5.3. Initialization

```python
from app.psfalgo.decision_cooldown import initialize_decision_cooldown_manager

# Initialize (default: 5 minutes)
initialize_decision_cooldown_manager(cooldown_minutes=5.0)
```

---

## 6. CONFIDENCE CALCULATOR (BONUS)

### 6.1. Kullanım

```python
from app.psfalgo.confidence_calculator import get_confidence_calculator

# Calculate confidence
confidence_calculator = get_confidence_calculator()
if confidence_calculator:
    confidence = confidence_calculator.calculate_confidence(
        symbol=symbol,
        position=position,
        metrics=metrics,
        action="SELL",
        reason="Fbtot < 1.10"
    )
    # Returns: float (0.0-1.0)
```

### 6.2. Confidence Factors

1. **Data Completeness** (0.0-0.3): Are all required metrics available?
2. **Signal Strength** (0.0-0.4): How strong is the signal?
3. **Market Conditions** (0.0-0.2): Spread, liquidity, etc.
4. **Historical Accuracy** (0.0-0.1): Placeholder for future

### 6.3. Initialization

```python
from app.psfalgo.confidence_calculator import initialize_confidence_calculator

# Initialize
initialize_confidence_calculator()
```

---

## 7. TAM ENTEGRASYON ÖRNEĞİ

### 7.1. RUNALL Engine'de Kullanım

```python
# runall_engine.py içinde

async def _step_update_exposure(self):
    """Step 1: Update exposure snapshot"""
    self.cycle_state = CycleState.EXPOSURE_CHECK
    
    # Get position snapshot
    position_api = get_position_snapshot_api()
    positions = await position_api.get_position_snapshot()
    
    # Calculate exposure
    exposure_calculator = get_exposure_calculator()
    self.current_exposure = exposure_calculator.calculate_exposure(positions)
    
    await self._publish_state()

async def _prepare_karbotu_request(self) -> DecisionRequest:
    """Prepare KARBOTU decision request"""
    # Get APIs
    position_api = get_position_snapshot_api()
    metrics_api = get_metrics_snapshot_api()
    
    # Use same snapshot timestamp for consistency
    snapshot_ts = datetime.now()
    
    # Get position snapshot (long positions only)
    all_positions = await position_api.get_position_snapshot()
    long_positions = [p for p in all_positions if p.qty > 0]
    
    # Get symbols for metrics snapshot
    symbols = [p.symbol for p in long_positions]
    
    # Get metrics snapshot (same timestamp)
    metrics = await metrics_api.get_metrics_snapshot(symbols, snapshot_ts=snapshot_ts)
    
    return DecisionRequest(
        positions=long_positions,
        metrics=metrics,
        exposure=self.current_exposure,
        cycle_count=self.loop_count,
        snapshot_ts=snapshot_ts
    )
```

### 7.2. Decision Engine'de Kullanım

```python
# karbotu_engine.py içinde

async def karbotu_decision_engine(request: DecisionRequest) -> DecisionResponse:
    """KARBOTU decision engine"""
    decisions = []
    filtered_out = []
    
    # Get cooldown manager
    cooldown_manager = get_decision_cooldown_manager()
    
    # Get confidence calculator
    confidence_calculator = get_confidence_calculator()
    
    for position in request.positions:
        symbol = position.symbol
        metrics = request.metrics.get(symbol)
        
        if not metrics:
            # No metrics available
            filtered_out.append(Decision(
                symbol=symbol,
                action="FILTERED",
                filtered_out=True,
                filter_reasons=["Metrics not available"]
            ))
            continue
        
        # Check cooldown
        if cooldown_manager and not cooldown_manager.can_make_decision(symbol):
            filtered_out.append(Decision(
                symbol=symbol,
                action="FILTERED",
                filtered_out=True,
                filter_reasons=[f"Cooldown active ({cooldown_manager.get_time_since_last_decision(symbol):.1f} min)"]
            ))
            continue
        
        # Make decision (example: Step 2 - Fbtot < 1.10)
        if metrics.fbtot and metrics.fbtot < 1.10 and metrics.ask_sell_pahalilik and metrics.ask_sell_pahalilik > -0.10:
            # Calculate confidence
            confidence = 0.0
            if confidence_calculator:
                confidence = confidence_calculator.calculate_confidence(
                    symbol=symbol,
                    position=position,
                    metrics=metrics,
                    action="SELL",
                    reason="Fbtot < 1.10 and Ask Sell Pahalılık > -0.10"
                )
            
            # Create decision
            decision = Decision(
                symbol=symbol,
                action="SELL",
                order_type="ASK_SELL",
                lot_percentage=50.0,
                calculated_lot=int(abs(position.qty) * 0.5),
                price_hint=metrics.grpan_price or metrics.last,
                step_number=2,
                reason="Fbtot < 1.10 and Ask Sell Pahalılık > -0.10",
                confidence=confidence,
                metrics_used={
                    'fbtot': metrics.fbtot,
                    'ask_sell_pahalilik': metrics.ask_sell_pahalilik
                },
                timestamp=datetime.now()
            )
            
            decisions.append(decision)
            
            # Record decision (for cooldown)
            if cooldown_manager:
                cooldown_manager.record_decision(symbol)
        else:
            # Filtered out
            filtered_out.append(Decision(
                symbol=symbol,
                action="FILTERED",
                filtered_out=True,
                filter_reasons=["Fbtot >= 1.10 or Ask Sell Pahalılık <= -0.10"]
            ))
    
    return DecisionResponse(
        decisions=decisions,
        filtered_out=filtered_out
    )
```

---

## 8. INITIALIZATION SIRASI

### 8.1. Tüm API'leri Initialize Et

```python
# main.py veya initialization script'te

from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api
from app.psfalgo.metrics_snapshot_api import initialize_metrics_snapshot_api
from app.psfalgo.exposure_calculator import initialize_exposure_calculator
from app.psfalgo.decision_cooldown import initialize_decision_cooldown_manager
from app.psfalgo.confidence_calculator import initialize_confidence_calculator

# Initialize all APIs
initialize_position_snapshot_api(
    position_manager=position_manager,
    static_store=static_store,
    market_data_cache=market_data_cache
)

initialize_metrics_snapshot_api(
    market_data_cache=market_data_cache,
    static_store=static_store,
    grpan_engine=grpan_engine,
    rwvap_engine=rwvap_engine,
    pricing_overlay_engine=pricing_overlay_engine,
    janall_metrics_engine=janall_metrics_engine
)

initialize_exposure_calculator(config={
    'pot_max_lot': 63636
})

initialize_decision_cooldown_manager(cooldown_minutes=5.0)

initialize_confidence_calculator()
```

---

## 9. SONUÇ

### 9.1. Oluşturulan Dosyalar

1. ✅ `position_snapshot_api.py` - Position snapshot API
2. ✅ `metrics_snapshot_api.py` - Metrics snapshot API
3. ✅ `exposure_calculator.py` - Exposure calculation
4. ✅ `decision_cooldown.py` - Decision cooldown manager
5. ✅ `confidence_calculator.py` - Confidence calculator

### 9.2. Güncellenen Dosyalar

1. ✅ `decision_models.py` - PositionSnapshot'a `position_open_ts`, `holding_minutes` eklendi
2. ✅ `decision_models.py` - DecisionRequest'e `snapshot_ts` eklendi
3. ✅ `decision_models.py` - Decision'e `last_decision_ts` eklendi
4. ✅ `runall_engine.py` - Snapshot API'leri entegre edildi

### 9.3. Özellikler

- ✅ **Production-Grade**: Async, consistent, error handling
- ✅ **Snapshot Consistency**: Same cycle, same data
- ✅ **Decision Cooldown**: Per-symbol cooldown management
- ✅ **Confidence Scores**: 0-1 confidence calculation
- ✅ **Holding Time**: Position open timestamp + holding minutes
- ✅ **Group Info**: PRIMARY GROUP + CGRUP

### 9.4. Sonraki Adımlar

1. **KARBOTU Engine**: 13 adımlı decision engine implement et
2. **REDUCEMORE Engine**: KARBOTU ile aynı mantık
3. **ADDNEWPOS Engine**: Yeni pozisyon açma logic
4. **Config Rules**: `psfalgo_rules.yaml` doldur
5. **API Endpoints**: FastAPI endpoints ekle

---

**Özet**: Tüm snapshot API'leri production-ready, async, consistent ve decision engine'ler için optimize edilmiştir. RUNALL entegrasyonu tamamlandı ve snapshot consistency sağlanmıştır.






