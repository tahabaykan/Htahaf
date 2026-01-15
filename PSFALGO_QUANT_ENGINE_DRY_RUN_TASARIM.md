# PSFALGO Quant_Engine DRY-RUN Tasarım Dokümanı

## 📋 GENEL BAKIŞ

Bu doküman, Janall'daki PSFALGO sistemini Quant_Engine'e **DRY-RUN (decision-only)** modunda taşıma stratejisini detaylandırır. Sistem şu an **hiç emir göndermeyecek**, sadece karar üretecek ve açıklanabilir (explainable) çıktılar verecek.

---

## 1. JANALL'DAKİ PSFALGO RUNALL LOOP/CYCLE MANTIĞI

### 1.1. RUNALL Döngü Yapısı (Janall'dan)

RUNALL, **sürekli döngü halinde** çalışan master otomasyon sistemidir. Her döngü **9 adımdan** oluşur:

```
Döngü Başlangıcı (runall_loop_count++)
    ↓
Adım 1: Lot Bölücü Kontrolü (checkbox kontrolü)
    ↓
Adım 2: Controller ON (limit kontrolleri için)
    ↓
Adım 3: Exposure Kontrolü (Async - thread'de)
    ├─ Pot Toplam < Pot Max → OFANSIF → KARBOTU
    ├─ Pot Toplam >= Pot Max → DEFANSIF → REDUCEMORE
    └─ GEÇİŞ → REDUCEMORE
    ↓
Adım 4: KARBOTU veya REDUCEMORE Başlat (non-blocking)
    ↓
KARBOTU/REDUCEMORE Bitince (callback):
    ↓
Adım 5: ADDNEWPOS Kontrolü
    ├─ Pot Toplam < Pot Max → ADDNEWPOS aktif
    └─ Pot Toplam >= Pot Max → ADDNEWPOS pasif
    ↓
Adım 6: Qpcal İşlemi (Spreadkusu panel) - EMİR GÖNDERME
    ↓
Adım 7: 2 Dakika Bekle (after(120000))
    ↓
Adım 8: Tüm Emirleri İptal Et (runall_cancel_orders_and_restart)
    ↓
Adım 9: Yeni Döngü Başlat (Adım 1'e dön)
```

### 1.2. Cycle Periyodu

- **Adım 1-5**: ~30-60 saniye (KARBOTU/REDUCEMORE/ADDNEWPOS süresi)
- **Adım 6**: Qpcal işlemi (emir gönderme)
- **Adım 7**: **2 dakika bekleme** (120 saniye)
- **Adım 8**: Emir iptali (~5-10 saniye)
- **Adım 9**: Restart (anında)

**Toplam Cycle Süresi**: ~3-4 dakika (emir gönderme + 2 dakika bekleme + iptal)

### 1.3. Hangi Sırayla Hangi Modüller Çalışır?

#### **Adım 3: Exposure Kontrolü**
```python
# Exposure hesaplama
pot_total = sum(position['qty'] * position['price'] for position in positions)
pot_max_lot = 63636  # Varsayılan limit
exposure_mode = 'OFANSIF' if pot_total < pot_max_lot else 'DEFANSIF'
```

#### **Adım 4: KARBOTU veya REDUCEMORE**
- **OFANSIF**: `start_karbotu_automation()` → 13 adımlı süreç
- **DEFANSIF/GEÇİŞ**: `start_reducemore_automation()` → 13 adımlı süreç

#### **Adım 5: ADDNEWPOS**
- **Koşul**: `pot_total < pot_max_lot` ve `exposure_mode == 'OFANSIF'`
- **Aksiyon**: `start_addnewpos_automation()` → Yeni pozisyon açma

### 1.4. Cycle İçinde State Geçişleri

```python
# Global State
runall_loop_running: bool = True/False
runall_loop_count: int = 0, 1, 2, ...
runall_allowed_mode: bool = True/False  # Auto-confirm

# Cycle İçi Sub-State
runall_waiting_for_karbotu: bool = False
runall_waiting_for_reducemore: bool = False
runall_addnewpos_triggered: bool = False
runall_addnewpos_callback_set: bool = False

# KARBOTU/REDUCEMORE State
karbotu_running: bool = True/False
karbotu_current_step: int = 1-13
reducemore_running: bool = True/False
reducemore_current_step: int = 1-13
```

### 1.5. Callback Mekanizması

```python
# KARBOTU bitince
def karbotu_proceed_to_next_step():
    if karbotu_current_step == 13:
        # KARBOTU tamamlandı
        runall_waiting_for_karbotu = False
        # ADDNEWPOS kontrolü için callback
        runall_check_karbotu_and_addnewpos()

# REDUCEMORE bitince
def reducemore_proceed_to_next_step():
    if reducemore_current_step == 13:
        # REDUCEMORE tamamlandı
        runall_waiting_for_reducemore = False
        # ADDNEWPOS kontrolü için callback
        runall_check_reducemore_and_addnewpos()
```

---

## 2. KARBOTU / REDUCEMORE / ADDNEWPOS - DECISION ENGINE SOYUTLAMASI

### 2.1. Genel Yaklaşım

**Order göndermeyen**, sadece **decision engine** olarak çalışacak şekilde soyutlamak:

```
INPUT: Position Snapshot + Metrics Snapshot
    ↓
DECISION ENGINE: Filtreleme + Karar Üretme
    ↓
OUTPUT: Decision List + Filtered Out Reasons
```

### 2.2. KARBOTU Decision Engine

#### **Input (Position Snapshot + Metrics Snapshot)**

```python
class KarbotuInput:
    positions: List[PositionSnapshot]  # Long pozisyonlar
    metrics: Dict[str, SymbolMetrics]  # Her symbol için metrics
    
class PositionSnapshot:
    symbol: str
    qty: float  # Pozitif = Long
    avg_price: float
    current_price: float
    unrealized_pnl: float
    
class SymbolMetrics:
    fbtot: float  # Front Buy Total
    ask_sell_pahalilik: float  # Ask Sell Pahalılık skoru
    gort: float  # Group Relative Trend
    spread: float
    grpan_price: float
    rwvap_1d: float
    # ... diğer metrics
```

#### **Output (Decision List + Reasons)**

```python
class KarbotuDecision:
    symbol: str
    action: str  # "SELL", "REDUCE", "HOLD"
    order_type: str  # "ASK_SELL", "FRONT_SELL", "BID_SELL"
    lot_percentage: float  # %50, %25, %10, vb.
    calculated_lot: int  # Hesaplanan lot miktarı
    price: float  # Emir fiyatı (hint)
    step_number: int  # Hangi adımda karar verildi (1-13)
    reason: str  # Karar nedeni
    filtered_out: bool = False  # Filtrelendi mi?
    filter_reasons: List[str] = []  # Neden filtrelendi?

class KarbotuOutput:
    decisions: List[KarbotuDecision]  # Karar verilen pozisyonlar
    filtered_out: List[KarbotuDecision]  # Filtrelenen pozisyonlar
    step_summary: Dict[int, StepSummary]  # Her adım için özet
    total_decisions: int
    total_filtered: int
```

#### **KARBOTU 13 Adım Mantığı (Decision-Only)**

```python
def karbotu_decision_engine(input: KarbotuInput) -> KarbotuOutput:
    """
    KARBOTU decision engine - sadece karar üretir, emir göndermez.
    """
    decisions = []
    filtered_out = []
    
    # Adım 1: GORT Kontrolü (Take Profit Longs için)
    # Filtre: Gort > -1 ve Ask Sell pahalılık > -0.05
    eligible_positions = filter_by_gort(input.positions, input.metrics)
    
    # Adım 2: Fbtot < 1.10
    # Filtre: Fbtot < 1.10 ve Ask Sell pahalılık > -0.10
    # Lot: %50, Order Type: ASK_SELL
    step2_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: m.fbtot < 1.10 and m.ask_sell_pahalilik > -0.10,
        lot_percentage=50,
        order_type="ASK_SELL",
        step_number=2
    )
    decisions.extend(step2_decisions['decisions'])
    filtered_out.extend(step2_decisions['filtered_out'])
    
    # Adım 3: Fbtot 1.11-1.45 (low)
    # Filtre: 1.11 <= Fbtot <= 1.45 ve -0.05 <= Ask Sell pahalılık <= 0.04
    # Lot: %25, Order Type: ASK_SELL
    step3_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 1.11 <= m.fbtot <= 1.45 and -0.05 <= m.ask_sell_pahalilik <= 0.04,
        lot_percentage=25,
        order_type="ASK_SELL",
        step_number=3
    )
    decisions.extend(step3_decisions['decisions'])
    filtered_out.extend(step3_decisions['filtered_out'])
    
    # Adım 4: Fbtot 1.11-1.45 (high)
    # Filtre: 1.11 <= Fbtot <= 1.45 ve Ask Sell pahalılık > 0.04
    # Lot: %50, Order Type: ASK_SELL
    step4_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 1.11 <= m.fbtot <= 1.45 and m.ask_sell_pahalilik > 0.04,
        lot_percentage=50,
        order_type="ASK_SELL",
        step_number=4
    )
    decisions.extend(step4_decisions['decisions'])
    filtered_out.extend(step4_decisions['filtered_out'])
    
    # Adım 5: Fbtot 1.46-1.80 (low)
    # Filtre: 1.46 <= Fbtot <= 1.80 ve -0.05 <= Ask Sell pahalılık <= 0.04
    # Lot: %10, Order Type: FRONT_SELL
    step5_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 1.46 <= m.fbtot <= 1.80 and -0.05 <= m.ask_sell_pahalilik <= 0.04,
        lot_percentage=10,
        order_type="FRONT_SELL",
        step_number=5
    )
    decisions.extend(step5_decisions['decisions'])
    filtered_out.extend(step5_decisions['filtered_out'])
    
    # Adım 6: Fbtot 1.46-1.80 (high)
    # Filtre: 1.46 <= Fbtot <= 1.80 ve Ask Sell pahalılık > 0.04
    # Lot: %25, Order Type: ASK_SELL
    step6_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 1.46 <= m.fbtot <= 1.80 and m.ask_sell_pahalilik > 0.04,
        lot_percentage=25,
        order_type="ASK_SELL",
        step_number=6
    )
    decisions.extend(step6_decisions['decisions'])
    filtered_out.extend(step6_decisions['filtered_out'])
    
    # Adım 7: Fbtot 1.81-2.15 (low)
    # Filtre: 1.81 <= Fbtot <= 2.15 ve -0.05 <= Ask Sell pahalılık <= 0.04
    # Lot: %10, Order Type: FRONT_SELL
    step7_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 1.81 <= m.fbtot <= 2.15 and -0.05 <= m.ask_sell_pahalilik <= 0.04,
        lot_percentage=10,
        order_type="FRONT_SELL",
        step_number=7
    )
    decisions.extend(step7_decisions['decisions'])
    filtered_out.extend(step7_decisions['filtered_out'])
    
    # Adım 8: Fbtot 1.81-2.15 (high)
    # Filtre: 1.81 <= Fbtot <= 2.15 ve Ask Sell pahalılık > 0.04
    # Lot: %25, Order Type: ASK_SELL
    step8_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 1.81 <= m.fbtot <= 2.15 and m.ask_sell_pahalilik > 0.04,
        lot_percentage=25,
        order_type="ASK_SELL",
        step_number=8
    )
    decisions.extend(step8_decisions['decisions'])
    filtered_out.extend(step8_decisions['filtered_out'])
    
    # Adım 9: Fbtot 2.16-2.50 (low)
    # Filtre: 2.16 <= Fbtot <= 2.50 ve -0.05 <= Ask Sell pahalılık <= 0.04
    # Lot: %10, Order Type: FRONT_SELL
    step9_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 2.16 <= m.fbtot <= 2.50 and -0.05 <= m.ask_sell_pahalilik <= 0.04,
        lot_percentage=10,
        order_type="FRONT_SELL",
        step_number=9
    )
    decisions.extend(step9_decisions['decisions'])
    filtered_out.extend(step9_decisions['filtered_out'])
    
    # Adım 10: Fbtot 2.16-2.50 (high)
    # Filtre: 2.16 <= Fbtot <= 2.50 ve Ask Sell pahalılık > 0.04
    # Lot: %25, Order Type: ASK_SELL
    step10_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: 2.16 <= m.fbtot <= 2.50 and m.ask_sell_pahalilik > 0.04,
        lot_percentage=25,
        order_type="ASK_SELL",
        step_number=10
    )
    decisions.extend(step10_decisions['decisions'])
    filtered_out.extend(step10_decisions['filtered_out'])
    
    # Adım 11: Fbtot > 2.50 (low)
    # Filtre: Fbtot > 2.50 ve -0.05 <= Ask Sell pahalılık <= 0.04
    # Lot: %10, Order Type: FRONT_SELL
    step11_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: m.fbtot > 2.50 and -0.05 <= m.ask_sell_pahalilik <= 0.04,
        lot_percentage=10,
        order_type="FRONT_SELL",
        step_number=11
    )
    decisions.extend(step11_decisions['decisions'])
    filtered_out.extend(step11_decisions['filtered_out'])
    
    # Adım 12: Fbtot > 2.50 (high)
    # Filtre: Fbtot > 2.50 ve Ask Sell pahalılık > 0.04
    # Lot: %25, Order Type: ASK_SELL
    step12_decisions = filter_and_decide(
        eligible_positions,
        condition=lambda p, m: m.fbtot > 2.50 and m.ask_sell_pahalilik > 0.04,
        lot_percentage=25,
        order_type="ASK_SELL",
        step_number=12
    )
    decisions.extend(step12_decisions['decisions'])
    filtered_out.extend(step12_decisions['filtered_out'])
    
    # Adım 13: Short Pozisyonlar (eğer varsa)
    # Filtre: Short pozisyonlar için Bid Buy Ucuzluk < 0.06
    # Lot: %50, Order Type: BID_BUY (cover)
    step13_decisions = filter_and_decide_shorts(
        input.positions,  # Short pozisyonlar (qty < 0)
        input.metrics,
        condition=lambda p, m: m.bid_buy_ucuzluk < 0.06,
        lot_percentage=50,
        order_type="BID_BUY",  # Cover
        step_number=13
    )
    decisions.extend(step13_decisions['decisions'])
    filtered_out.extend(step13_decisions['filtered_out'])
    
    return KarbotuOutput(
        decisions=decisions,
        filtered_out=filtered_out,
        step_summary=build_step_summary(decisions),
        total_decisions=len(decisions),
        total_filtered=len(filtered_out)
    )
```

#### **Filter Helper Function**

```python
def filter_and_decide(
    positions: List[PositionSnapshot],
    metrics: Dict[str, SymbolMetrics],
    condition: Callable[[PositionSnapshot, SymbolMetrics], bool],
    lot_percentage: float,
    order_type: str,
    step_number: int
) -> Dict[str, List[KarbotuDecision]]:
    """
    Pozisyonları filtrele ve karar üret.
    """
    decisions = []
    filtered_out = []
    
    for position in positions:
        symbol = position.symbol
        metric = metrics.get(symbol)
        
        if not metric:
            filtered_out.append(KarbotuDecision(
                symbol=symbol,
                action="FILTERED",
                filtered_out=True,
                filter_reasons=["Metrics not available"]
            ))
            continue
        
        # Koşul kontrolü
        if condition(position, metric):
            # Lot hesaplama
            calculated_lot = calculate_lot(position.qty, lot_percentage)
            
            # Price hint (GRPAN veya RWVAP)
            price_hint = metric.grpan_price or metric.rwvap_1d or position.current_price
            
            decisions.append(KarbotuDecision(
                symbol=symbol,
                action="SELL",
                order_type=order_type,
                lot_percentage=lot_percentage,
                calculated_lot=calculated_lot,
                price=price_hint,
                step_number=step_number,
                reason=f"Fbtot={metric.fbtot:.2f}, Ask Sell Pahalılık={metric.ask_sell_pahalilik:.4f}"
            ))
        else:
            # Filtrelendi
            reasons = []
            if not (condition(position, metric)):
                reasons.append(f"Condition not met: Fbtot={metric.fbtot:.2f}, Ask Sell={metric.ask_sell_pahalilik:.4f}")
            
            filtered_out.append(KarbotuDecision(
                symbol=symbol,
                action="FILTERED",
                filtered_out=True,
                filter_reasons=reasons,
                step_number=step_number
            ))
    
    return {
        'decisions': decisions,
        'filtered_out': filtered_out
    }
```

### 2.3. REDUCEMORE Decision Engine

REDUCEMORE, KARBOTU ile **birebir aynı mantık** ama **daha konservatif**:

- **Aynı 13 adım**
- **Aynı filtreleme mantığı**
- **Fark**: Lot yüzdeleri daha düşük olabilir (configurable)

```python
class ReducemoreDecision:
    # KARBOTU ile aynı yapı
    # Fark: lot_percentage'ler daha konservatif (örn: %25 yerine %10)
```

### 2.4. ADDNEWPOS Decision Engine

#### **Input**

```python
class AddnewposInput:
    current_positions: List[PositionSnapshot]  # Mevcut pozisyonlar
    available_symbols: List[SymbolSnapshot]  # Tüm symbol'ler (CSV'den)
    metrics: Dict[str, SymbolMetrics]  # Her symbol için metrics
    exposure_info: ExposureInfo  # Pot Total, Pot Max, vb.
    port_adjuster: PortAdjusterConfig  # Grup bazlı lot limitleri
```

#### **Output**

```python
class AddnewposDecision:
    symbol: str
    action: str  # "BUY", "ADD", "HOLD"
    order_type: str  # "BID_BUY", "FRONT_BUY", "ASK_BUY"
    lot: int  # Hesaplanan lot miktarı
    price: float  # Emir fiyatı (hint)
    reason: str  # Karar nedeni
    filtered_out: bool = False
    filter_reasons: List[str] = []

class AddnewposOutput:
    decisions: List[AddnewposDecision]
    filtered_out: List[AddnewposDecision]
    exposure_check: ExposureCheckResult
    group_summary: Dict[str, GroupSummary]  # Grup bazlı özet
```

#### **ADDNEWPOS Mantığı (Özet)**

```python
def addnewpos_decision_engine(input: AddnewposInput) -> AddnewposOutput:
    """
    ADDNEWPOS decision engine - yeni pozisyon açma kararları.
    """
    decisions = []
    filtered_out = []
    
    # 1. Exposure kontrolü
    if input.exposure_info.pot_total >= input.exposure_info.pot_max_lot:
        # Exposure limiti aşıldı, yeni pozisyon açma
        return AddnewposOutput(
            decisions=[],
            filtered_out=[],
            exposure_check=ExposureCheckResult(blocked=True, reason="Pot Total >= Pot Max")
        )
    
    # 2. Grup bazlı filtreleme
    for group, symbols in group_symbols.items():
        # Grup lot limiti kontrolü
        group_lot_limit = input.port_adjuster.get_group_limit(group)
        current_group_lot = sum(p.qty for p in current_positions if p.group == group)
        
        if current_group_lot >= group_lot_limit:
            continue  # Grup limiti aşıldı
        
        # 3. Symbol bazlı filtreleme
        for symbol in symbols:
            metric = input.metrics.get(symbol)
            if not metric:
                continue
            
            # Filtreleme koşulları
            # - Bid Buy Ucuzluk > 0.06 (ucuz)
            # - Fbtot > 1.10 (long için)
            # - Spread < 0.05 (likidite)
            # - AVG_ADV > 1000 (likidite)
            
            if (metric.bid_buy_ucuzluk > 0.06 and 
                metric.fbtot > 1.10 and 
                metric.spread < 0.05 and
                metric.avg_adv > 1000):
                
                # Lot hesaplama (grup limitine göre)
                available_lot = group_lot_limit - current_group_lot
                calculated_lot = min(available_lot, 200)  # Max 200 lot per symbol
                
                decisions.append(AddnewposDecision(
                    symbol=symbol,
                    action="BUY",
                    order_type="BID_BUY",
                    lot=calculated_lot,
                    price=metric.grpan_price or metric.bid,
                    reason=f"Bid Buy Ucuzluk={metric.bid_buy_ucuzluk:.4f}, Fbtot={metric.fbtot:.2f}"
                ))
    
    return AddnewposOutput(
        decisions=decisions,
        filtered_out=filtered_out,
        exposure_check=ExposureCheckResult(blocked=False),
        group_summary=build_group_summary(decisions)
    )
```

---

## 3. QUANT_ENGINE İÇİN PSFALGO STATE MACHINE

### 3.1. Global State (RUNALL Level)

```python
class RunallGlobalState(str, Enum):
    IDLE = "IDLE"  # Başlatılmamış
    RUNNING = "RUNNING"  # Döngü çalışıyor
    WAITING = "WAITING"  # Alt modül bekleniyor (KARBOTU/REDUCEMORE/ADDNEWPOS)
    BLOCKED = "BLOCKED"  # Bloke edildi (exposure limit, vb.)
    CANCELLING = "CANCELLING"  # İptal ediliyor
    ERROR = "ERROR"  # Hata durumu
```

### 3.2. Cycle İçi Sub-State

```python
class RunallCycleState(str, Enum):
    INIT = "INIT"  # Döngü başlatılıyor
    LOT_DIVIDER_CHECK = "LOT_DIVIDER_CHECK"  # Adım 1
    CONTROLLER_ON = "CONTROLLER_ON"  # Adım 2
    EXPOSURE_CHECK = "EXPOSURE_CHECK"  # Adım 3
    KARBOTU_RUNNING = "KARBOTU_RUNNING"  # Adım 4a (OFANSIF)
    REDUCEMORE_RUNNING = "REDUCEMORE_RUNNING"  # Adım 4b (DEFANSIF)
    ADDNEWPOS_CHECK = "ADDNEWPOS_CHECK"  # Adım 5
    ADDNEWPOS_RUNNING = "ADDNEWPOS_RUNNING"  # Adım 5 (aktifse)
    QPCAL_PREP = "QPCAL_PREP"  # Adım 6 (DRY-RUN'da skip)
    WAITING_CANCEL = "WAITING_CANCEL"  # Adım 7 (2 dakika bekleme - DRY-RUN'da skip)
    CANCELLING_ORDERS = "CANCELLING_ORDERS"  # Adım 8 (DRY-RUN'da skip)
    RESTARTING = "RESTARTING"  # Adım 9
```

### 3.3. KARBOTU/REDUCEMORE Sub-State

```python
class KarbotuState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STEP_1 = "STEP_1"  # GORT Check
    STEP_2 = "STEP_2"  # Fbtot < 1.10
    STEP_3 = "STEP_3"  # Fbtot 1.11-1.45 (low)
    STEP_4 = "STEP_4"  # Fbtot 1.11-1.45 (high)
    STEP_5 = "STEP_5"  # Fbtot 1.46-1.80 (low)
    STEP_6 = "STEP_6"  # Fbtot 1.46-1.80 (high)
    STEP_7 = "STEP_7"  # Fbtot 1.81-2.15 (low)
    STEP_8 = "STEP_8"  # Fbtot 1.81-2.15 (high)
    STEP_9 = "STEP_9"  # Fbtot 2.16-2.50 (low)
    STEP_10 = "STEP_10"  # Fbtot 2.16-2.50 (high)
    STEP_11 = "STEP_11"  # Fbtot > 2.50 (low)
    STEP_12 = "STEP_12"  # Fbtot > 2.50 (high)
    STEP_13 = "STEP_13"  # Short positions
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
```

### 3.4. State Machine Diyagramı

```
RUNALL Global State Machine:
┌─────────┐
│  IDLE   │
└────┬────┘
     │ start_runall()
     ↓
┌──────────┐
│ RUNNING  │
└────┬─────┘
     │
     ├─→ Cycle State Machine
     │
     │   INIT → LOT_DIVIDER_CHECK → CONTROLLER_ON → EXPOSURE_CHECK
     │     ↓
     │   KARBOTU_RUNNING (OFANSIF) veya REDUCEMORE_RUNNING (DEFANSIF)
     │     ↓
     │   ADDNEWPOS_CHECK → ADDNEWPOS_RUNNING (if eligible)
     │     ↓
     │   RESTARTING → (yeni döngü)
     │
     ├─→ stop_runall()
     ↓
┌──────────┐
│  IDLE    │
└──────────┘
```

---

## 4. RUNALL İÇİN ASYNC / EVENT-DRIVEN AMA DETERMINISTIC YAPI

### 4.1. Async/Await Tabanlı Tasarım

```python
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

class RunallCycleEngine:
    """
    RUNALL cycle engine - async/await tabanlı, deterministic.
    """
    
    def __init__(self):
        self.global_state = RunallGlobalState.IDLE
        self.cycle_state = RunallCycleState.INIT
        self.loop_count = 0
        self.loop_running = False
        self.dry_run_mode = True  # DRY-RUN modu (default)
        
        # State storage (Redis veya in-memory)
        self.state_store: Dict[str, Any] = {}
        
        # Timer için
        self.cycle_start_time: Optional[datetime] = None
        self.wait_until: Optional[datetime] = None
    
    async def start_runall(self):
        """RUNALL'ı başlat"""
        if self.global_state != RunallGlobalState.IDLE:
            raise RuntimeError("RUNALL already running")
        
        self.global_state = RunallGlobalState.RUNNING
        self.loop_running = True
        
        # Background task olarak cycle'ı başlat
        asyncio.create_task(self.runall_cycle_loop())
        
        # State'i Redis'e publish et
        await self.publish_state()
    
    async def stop_runall(self):
        """RUNALL'ı durdur"""
        self.loop_running = False
        self.global_state = RunallGlobalState.IDLE
        await self.publish_state()
    
    async def runall_cycle_loop(self):
        """
        Ana cycle loop - sürekli döngü.
        """
        while self.loop_running:
            try:
                self.loop_count += 1
                self.cycle_start_time = datetime.now()
                
                logger.info(f"[RUNALL] 🔄 Cycle {self.loop_count} başlatılıyor...")
                
                # Adım 1: Lot Bölücü Kontrolü
                await self.step_1_lot_divider_check()
                
                # Adım 2: Controller ON
                await self.step_2_controller_on()
                
                # Adım 3: Exposure Kontrolü
                exposure_info = await self.step_3_exposure_check()
                
                # Adım 4: KARBOTU veya REDUCEMORE
                if exposure_info['mode'] == 'OFANSIF':
                    await self.step_4_karbotu()
                else:
                    await self.step_4_reducemore()
                
                # Adım 5: ADDNEWPOS Kontrolü
                if exposure_info['pot_total'] < exposure_info['pot_max_lot']:
                    await self.step_5_addnewpos()
                
                # Adım 6: Qpcal (DRY-RUN'da skip)
                if not self.dry_run_mode:
                    await self.step_6_qpcal()
                
                # Adım 7: 2 Dakika Bekleme (DRY-RUN'da skip)
                if not self.dry_run_mode:
                    await self.step_7_wait_2_minutes()
                
                # Adım 8: Emir İptali (DRY-RUN'da skip)
                if not self.dry_run_mode:
                    await self.step_8_cancel_orders()
                
                # Adım 9: Restart (yeni döngü)
                await self.step_9_restart()
                
                # State'i publish et
                await self.publish_state()
                
            except Exception as e:
                logger.error(f"[RUNALL] Cycle {self.loop_count} hatası: {e}", exc_info=True)
                self.global_state = RunallGlobalState.ERROR
                await self.publish_state()
                # Hata olsa bile devam et (next cycle)
                await asyncio.sleep(5)  # 5 saniye bekle, sonra yeni döngü
    
    async def step_1_lot_divider_check(self):
        """Adım 1: Lot Bölücü Kontrolü"""
        self.cycle_state = RunallCycleState.LOT_DIVIDER_CHECK
        # Lot bölücü checkbox kontrolü (config'den)
        # DRY-RUN'da sadece log
        logger.info("[RUNALL] Adım 1: Lot Bölücü kontrolü (DRY-RUN)")
        await self.publish_state()
    
    async def step_2_controller_on(self):
        """Adım 2: Controller ON"""
        self.cycle_state = RunallCycleState.CONTROLLER_ON
        # Controller'ı ON yap (config'den)
        logger.info("[RUNALL] Adım 2: Controller ON (DRY-RUN)")
        await self.publish_state()
    
    async def step_3_exposure_check(self) -> Dict[str, Any]:
        """Adım 3: Exposure Kontrolü"""
        self.cycle_state = RunallCycleState.EXPOSURE_CHECK
        
        # Position snapshot al
        positions = await self.get_position_snapshot()
        
        # Exposure hesapla
        pot_total = sum(p['qty'] * p['price'] for p in positions)
        pot_max_lot = 63636  # Config'den
        
        exposure_mode = 'OFANSIF' if pot_total < pot_max_lot else 'DEFANSIF'
        
        exposure_info = {
            'pot_total': pot_total,
            'pot_max_lot': pot_max_lot,
            'mode': exposure_mode,
            'total_lots': sum(abs(p['qty']) for p in positions)
        }
        
        logger.info(f"[RUNALL] Adım 3: Exposure kontrolü - Mode={exposure_mode}, Pot Total={pot_total:,}")
        await self.publish_state()
        
        return exposure_info
    
    async def step_4_karbotu(self):
        """Adım 4: KARBOTU"""
        self.cycle_state = RunallCycleState.KARBOTU_RUNNING
        self.global_state = RunallGlobalState.WAITING
        
        # Position snapshot + metrics snapshot al
        positions = await self.get_position_snapshot()
        metrics = await self.get_metrics_snapshot()
        
        # KARBOTU decision engine'i çalıştır
        karbotu_input = KarbotuInput(
            positions=[p for p in positions if p['qty'] > 0],  # Long only
            metrics=metrics
        )
        
        karbotu_output = karbotu_decision_engine(karbotu_input)
        
        # Decision'ları logla ve publish et
        logger.info(f"[RUNALL] KARBOTU tamamlandı: {len(karbotu_output.decisions)} karar, {len(karbotu_output.filtered_out)} filtrelendi")
        
        # Decision'ları Redis'e publish et (UI için)
        await self.publish_decisions('KARBOTU', karbotu_output)
        
        self.global_state = RunallGlobalState.RUNNING
        await self.publish_state()
    
    async def step_4_reducemore(self):
        """Adım 4: REDUCEMORE"""
        self.cycle_state = RunallCycleState.REDUCEMORE_RUNNING
        self.global_state = RunallGlobalState.WAITING
        
        # REDUCEMORE decision engine'i çalıştır (KARBOTU ile aynı mantık)
        # ...
        
        self.global_state = RunallGlobalState.RUNNING
        await self.publish_state()
    
    async def step_5_addnewpos(self):
        """Adım 5: ADDNEWPOS"""
        self.cycle_state = RunallCycleState.ADDNEWPOS_CHECK
        
        # Exposure kontrolü (zaten yapıldı, ama tekrar kontrol)
        exposure_info = await self.step_3_exposure_check()
        
        if exposure_info['pot_total'] >= exposure_info['pot_max_lot']:
            logger.info("[RUNALL] Adım 5: ADDNEWPOS pasif (Pot Total >= Pot Max)")
            return
        
        self.cycle_state = RunallCycleState.ADDNEWPOS_RUNNING
        self.global_state = RunallGlobalState.WAITING
        
        # ADDNEWPOS decision engine'i çalıştır
        # ...
        
        self.global_state = RunallGlobalState.RUNNING
        await self.publish_state()
    
    async def step_6_qpcal(self):
        """Adım 6: Qpcal (DRY-RUN'da skip)"""
        if self.dry_run_mode:
            return
        
        self.cycle_state = RunallCycleState.QPCAL_PREP
        # Qpcal işlemi (emir gönderme)
        # ...
    
    async def step_7_wait_2_minutes(self):
        """Adım 7: 2 Dakika Bekleme (DRY-RUN'da skip)"""
        if self.dry_run_mode:
            return
        
        self.cycle_state = RunallCycleState.WAITING_CANCEL
        self.wait_until = datetime.now() + timedelta(minutes=2)
        
        # 2 dakika bekle
        await asyncio.sleep(120)
    
    async def step_8_cancel_orders(self):
        """Adım 8: Emir İptali (DRY-RUN'da skip)"""
        if self.dry_run_mode:
            return
        
        self.cycle_state = RunallCycleState.CANCELLING_ORDERS
        # Tüm emirleri iptal et
        # ...
    
    async def step_9_restart(self):
        """Adım 9: Restart (yeni döngü)"""
        self.cycle_state = RunallCycleState.RESTARTING
        logger.info(f"[RUNALL] Cycle {self.loop_count} tamamlandı, yeni döngü başlatılıyor...")
        # Yeni döngü otomatik başlar (while loop)
    
    async def publish_state(self):
        """State'i Redis'e publish et"""
        state_data = {
            'global_state': self.global_state.value,
            'cycle_state': self.cycle_state.value,
            'loop_count': self.loop_count,
            'loop_running': self.loop_running,
            'dry_run_mode': self.dry_run_mode,
            'cycle_start_time': self.cycle_start_time.isoformat() if self.cycle_start_time else None,
            'wait_until': self.wait_until.isoformat() if self.wait_until else None,
            'timestamp': datetime.now().isoformat()
        }
        
        # Redis pub/sub
        await redis_client.publish('psfalgo:state', json.dumps(state_data))
        
        # WebSocket broadcast (UI için)
        await websocket_manager.broadcast({
            'type': 'psfalgo_state',
            'data': state_data
        })
    
    async def publish_decisions(self, module: str, output: Any):
        """Decision'ları Redis'e publish et"""
        decision_data = {
            'module': module,
            'loop_count': self.loop_count,
            'decisions': [d.__dict__ for d in output.decisions],
            'filtered_out': [d.__dict__ for d in output.filtered_out],
            'summary': {
                'total_decisions': output.total_decisions,
                'total_filtered': output.total_filtered
            },
            'timestamp': datetime.now().isoformat()
        }
        
        # Redis pub/sub
        await redis_client.publish(f'psfalgo:decisions:{module.lower()}', json.dumps(decision_data))
        
        # WebSocket broadcast
        await websocket_manager.broadcast({
            'type': 'psfalgo_decisions',
            'data': decision_data
        })
```

### 4.2. Timer + State Yönetimi

```python
class RunallTimer:
    """
    RUNALL için timer yönetimi.
    """
    
    def __init__(self):
        self.cycle_start: Optional[datetime] = None
        self.wait_until: Optional[datetime] = None
        self.last_state_publish: Optional[datetime] = None
    
    def start_cycle(self):
        """Cycle başlat"""
        self.cycle_start = datetime.now()
        self.wait_until = None
    
    def set_wait_until(self, minutes: int):
        """Bekleme süresi ayarla"""
        self.wait_until = datetime.now() + timedelta(minutes=minutes)
    
    def get_remaining_wait_time(self) -> Optional[float]:
        """Kalan bekleme süresi (saniye)"""
        if not self.wait_until:
            return None
        remaining = (self.wait_until - datetime.now()).total_seconds()
        return max(0, remaining)
    
    def is_waiting(self) -> bool:
        """Bekleme durumunda mı?"""
        if not self.wait_until:
            return False
        return datetime.now() < self.wait_until
```

### 4.3. Redis State Publish

```python
# Redis pub/sub channels
PSFALGO_STATE_CHANNEL = "psfalgo:state"
PSFALGO_DECISIONS_CHANNEL = "psfalgo:decisions:{module}"  # karbotu, reducemore, addnewpos
PSFALGO_CYCLE_CHANNEL = "psfalgo:cycle"

# State format
{
    "global_state": "RUNNING",
    "cycle_state": "KARBOTU_RUNNING",
    "loop_count": 5,
    "loop_running": true,
    "dry_run_mode": true,
    "cycle_start_time": "2025-01-14T10:30:00",
    "wait_until": null,
    "timestamp": "2025-01-14T10:30:15"
}
```

### 4.4. UI Freeze Önleme (Best Practices)

1. **Async/Await**: Tüm işlemler async
2. **Background Tasks**: `asyncio.create_task()` ile background task'lar
3. **Non-Blocking**: Hiçbir işlem main thread'i bloklamaz
4. **State Publishing**: Periyodik state publish (her 1 saniyede bir)
5. **WebSocket Broadcast**: Real-time UI güncellemeleri
6. **Batch Processing**: Decision engine'ler batch halinde çalışır

---

## 5. DRY-RUN MODU VE EXPLAINABILITY

### 5.1. DRY-RUN Modu Tasarımı

```python
class DryRunMode:
    """
    DRY-RUN modu - sadece karar üretir, emir göndermez.
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
    
    def should_send_orders(self) -> bool:
        """Emir gönderilmeli mi?"""
        return not self.enabled
    
    def should_wait_for_cancel(self) -> bool:
        """2 dakika bekleme yapılmalı mı?"""
        return not self.enabled
    
    def should_cancel_orders(self) -> bool:
        """Emir iptali yapılmalı mı?"""
        return not self.enabled
```

### 5.2. Explainability Data Model

```python
class DecisionExplanation:
    """
    Karar açıklaması - neden bu karar alındı?
    """
    symbol: str
    decision: str  # "SELL", "BUY", "HOLD", "FILTERED"
    reason: str  # Ana neden
    conditions_met: Dict[str, bool]  # Hangi koşullar sağlandı?
    conditions_failed: Dict[str, bool]  # Hangi koşullar sağlanmadı?
    metrics_used: Dict[str, float]  # Kullanılan metrics
    step_number: int  # Hangi adımda karar verildi?
    confidence: float  # Güven skoru (0-1)
    alternative_decisions: List[str]  # Alternatif kararlar

class FilterExplanation:
    """
    Filtreleme açıklaması - neden filtrelendi?
    """
    symbol: str
    filtered_out: bool
    filter_reasons: List[str]  # Filtreleme nedenleri
    failed_conditions: Dict[str, Any]  # Başarısız koşullar
    metrics_values: Dict[str, float]  # Metrics değerleri

class StepExplanation:
    """
    Adım açıklaması - bu adımda ne oldu?
    """
    step_number: int
    step_name: str
    total_positions: int
    filtered_positions: int
    decisions_made: int
    filter_summary: Dict[str, int]  # Filtre nedenlerine göre sayı
    time_taken_ms: float
```

### 5.3. Explainability Örnekleri

#### **KARBOTU Decision Explanation**

```python
{
    "symbol": "WFC PRY",
    "decision": "SELL",
    "reason": "Fbtot < 1.10 ve Ask Sell pahalılık > -0.10",
    "conditions_met": {
        "fbtot_lt_110": true,
        "ask_sell_pahalilik_gt_minus_010": true,
        "qty_ge_100": true,
        "gort_gt_minus_1": true
    },
    "conditions_failed": {},
    "metrics_used": {
        "fbtot": 1.05,
        "ask_sell_pahalilik": 0.02,
        "gort": 0.5,
        "spread": 0.03,
        "grpan_price": 24.50
    },
    "step_number": 2,
    "confidence": 0.85,
    "alternative_decisions": ["HOLD", "REDUCE_25"]
}
```

#### **Filter Explanation**

```python
{
    "symbol": "BAC PRM",
    "filtered_out": true,
    "filter_reasons": [
        "Fbtot >= 1.10 (Fbtot=1.15)",
        "Ask Sell pahalılık <= -0.10 (Ask Sell=-0.12)"
    ],
    "failed_conditions": {
        "fbtot_lt_110": false,  # 1.15 >= 1.10
        "ask_sell_pahalilik_gt_minus_010": false  # -0.12 <= -0.10
    },
    "metrics_values": {
        "fbtot": 1.15,
        "ask_sell_pahalilik": -0.12,
        "gort": 0.3,
        "spread": 0.04
    }
}
```

### 5.4. Explainability Storage

```python
class ExplainabilityStore:
    """
    Explainability verilerini saklar.
    """
    
    def __init__(self):
        self.decisions: List[DecisionExplanation] = []
        self.filtered: List[FilterExplanation] = []
        self.steps: List[StepExplanation] = []
    
    def add_decision(self, decision: DecisionExplanation):
        """Karar ekle"""
        self.decisions.append(decision)
    
    def add_filtered(self, filtered: FilterExplanation):
        """Filtrelenmiş ekle"""
        self.filtered.append(filtered)
    
    def add_step(self, step: StepExplanation):
        """Adım ekle"""
        self.steps.append(step)
    
    def get_explanation_for_symbol(self, symbol: str) -> Dict[str, Any]:
        """Symbol için açıklama"""
        decisions = [d for d in self.decisions if d.symbol == symbol]
        filtered = [f for f in self.filtered if f.symbol == symbol]
        
        return {
            'symbol': symbol,
            'decisions': [d.__dict__ for d in decisions],
            'filtered': [f.__dict__ for f in filtered],
            'summary': {
                'total_decisions': len(decisions),
                'total_filtered': len(filtered)
            }
        }
    
    def get_cycle_summary(self, loop_count: int) -> Dict[str, Any]:
        """Cycle özeti"""
        cycle_decisions = [d for d in self.decisions if d.loop_count == loop_count]
        cycle_filtered = [f for f in self.filtered if f.loop_count == loop_count]
        cycle_steps = [s for s in self.steps if s.loop_count == loop_count]
        
        return {
            'loop_count': loop_count,
            'total_decisions': len(cycle_decisions),
            'total_filtered': len(cycle_filtered),
            'steps': [s.__dict__ for s in cycle_steps],
            'decision_breakdown': self._breakdown_decisions(cycle_decisions),
            'filter_breakdown': self._breakdown_filters(cycle_filtered)
        }
```

---

## 6. ÖNERİLEN MİMARİ (ÖZET)

### 6.1. Modül Yapısı

```
quant_engine/app/psfalgo/
├── __init__.py
├── runall_engine.py          # RUNALL cycle engine
├── karbotu_engine.py         # KARBOTU decision engine
├── reducemore_engine.py      # REDUCEMORE decision engine
├── addnewpos_engine.py        # ADDNEWPOS decision engine
├── decision_models.py         # Decision data models
├── explainability.py          # Explainability store
├── state_machine.py           # State machine definitions
└── config/
    └── psfalgo_rules.yaml     # KARBOTU/REDUCEMORE/ADDNEWPOS kuralları
```

### 6.2. API Endpoints

```python
# FastAPI endpoints
@router.post("/psfalgo/runall/start")
async def start_runall():
    """RUNALL'ı başlat"""
    await runall_engine.start_runall()
    return {"status": "started"}

@router.post("/psfalgo/runall/stop")
async def stop_runall():
    """RUNALL'ı durdur"""
    await runall_engine.stop_runall()
    return {"status": "stopped"}

@router.get("/psfalgo/state")
async def get_psfalgo_state():
    """PSFALGO state'ini al"""
    return runall_engine.get_state()

@router.get("/psfalgo/decisions/{loop_count}")
async def get_decisions(loop_count: int):
    """Cycle decision'larını al"""
    return explainability_store.get_cycle_summary(loop_count)

@router.get("/psfalgo/explain/{symbol}")
async def explain_symbol(symbol: str):
    """Symbol için açıklama"""
    return explainability_store.get_explanation_for_symbol(symbol)
```

### 6.3. WebSocket Events

```python
# WebSocket event types
{
    "type": "psfalgo_state",
    "data": { /* state data */ }
}

{
    "type": "psfalgo_decisions",
    "data": {
        "module": "KARBOTU",
        "decisions": [ /* ... */ ],
        "filtered_out": [ /* ... */ ]
    }
}

{
    "type": "psfalgo_step",
    "data": {
        "step_number": 2,
        "step_name": "Fbtot < 1.10",
        "summary": { /* ... */ }
    }
}
```

---

## 7. UYGULAMA ADIMLARI

### Adım 1: Decision Models
1. `decision_models.py` oluştur
2. `KarbotuInput`, `KarbotuOutput`, `KarbotuDecision` tanımla
3. `ReducemoreInput/Output/Decision` tanımla
4. `AddnewposInput/Output/Decision` tanımla

### Adım 2: Decision Engines
1. `karbotu_engine.py` - 13 adımlı decision engine
2. `reducemore_engine.py` - KARBOTU ile aynı mantık
3. `addnewpos_engine.py` - Yeni pozisyon açma logic

### Adım 3: RUNALL Engine
1. `runall_engine.py` - Async cycle engine
2. State machine implementasyonu
3. Timer yönetimi
4. Redis pub/sub entegrasyonu

### Adım 4: Explainability
1. `explainability.py` - Explanation store
2. Decision explanation generation
3. Filter explanation generation
4. API endpoints

### Adım 5: Frontend Integration
1. PSFALGO state display
2. Decision table
3. Explanation panel
4. Cycle history

---

## 8. SONUÇ

Bu tasarım, Janall'daki PSFALGO mantığını **birebir** koruyarak, **modern, async, explainable ve DRY-RUN** modunda çalışacak şekilde Quant_Engine'e taşır. Sistem:

- ✅ **Emir göndermez** (DRY-RUN)
- ✅ **Karar üretir** (Decision engines)
- ✅ **Açıklanabilir** (Explainability)
- ✅ **Async/Event-driven** (UI donmaz)
- ✅ **Deterministic** (Aynı input → Aynı output)
- ✅ **Redis pub/sub** (State publishing)
- ✅ **WebSocket broadcast** (Real-time UI)

**Sonraki Adım**: Emir gönderme aşamasına geçildiğinde, decision'ları execution engine'e göndermek yeterli olacak.




