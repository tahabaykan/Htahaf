# Phase 6: Shadow Live (DRY-RUN Operations)

## 📋 Genel Bakış

Phase 6, sistemin **gerçek piyasa saatlerinde, gerçek market data ile, tamamen dry-run modunda** uzun süre çalıştırılmasını ve davranışının gözlemlenmesini sağlar.

**ÖNEMLİ**: Decision, execution ve observability layer'a **ASLA dokunulmaz**. Sadece orchestration, metrik ve raporlama eklenir.

---

## 🎯 Hedefler

1. **Shadow Live Runner**: Market open → start, close → stop
2. **Session Metrics**: Günlük toplam cycle, decision, execution metrikleri
3. **Safety Guards**: Max intents per cycle/day, aşıldığında BLOCKED
4. **Shadow Reports**: Gün sonu özet rapor (JSON + human-readable)
5. **ZERO RISK**: dry_run ASLA false yapılmayacak, broker adapter çağrısı YOK

---

## 📁 Dosya Yapısı

```
quant_engine/app/psfalgo/
└── shadow_live_runner.py    # Shadow Live Runner orchestrator

quant_engine/app/api/
└── psfalgo_routes.py         # Shadow Live API endpoints (updated)

quant_engine/reports/shadow/
└── shadow_report_YYYY-MM-DD.json    # Daily shadow reports
└── shadow_report_YYYY-MM-DD.txt     # Human-readable reports
```

---

## 🔧 Bileşenler

### 1. ShadowLiveRunner (`shadow_live_runner.py`)

**Sorumluluklar:**
- Market-aware start/stop (market open → start, close → stop)
- Session metrics collection
- Safety guards (max limits)
- Shadow report generation

**Özellikler:**
- `start()`: Start shadow live runner
- `stop()`: Stop shadow live runner
- `_runner_loop()`: Main loop (checks market status, manages RUNALL)
- `_collect_cycle_metrics()`: Collect metrics from current cycle
- `_check_safety_guards()`: Check max limits, block if exceeded
- `_generate_shadow_report()`: Generate end-of-day report

**Data Models:**
- `SessionMetrics`: Daily session metrics
- `SessionStatus`: Runner status enum

**Safety Guards:**
- `max_intents_per_cycle`: Default 20
- `max_intents_per_day`: Default 300
- Aşıldığında RUNALL → BLOCKED

### 2. Shadow Live API (`psfalgo_routes.py`)

**Endpoints:**
- `POST /api/psfalgo/shadow/start` - Start Shadow Live Runner
- `POST /api/psfalgo/shadow/stop` - Stop Shadow Live Runner
- `GET /api/psfalgo/shadow/status` - Get status and session metrics

---

## 📊 Session Metrics

### Cycle Metrics
- `total_cycles`: Günlük toplam cycle sayısı
- `successful_cycles`: Başarılı cycle sayısı
- `failed_cycles`: Başarısız cycle sayısı

### Decision Metrics
- `karbotu_decisions`: KARBOTU decision sayısı
- `reducemore_decisions`: REDUCEMORE decision sayısı
- `addnewpos_decisions`: ADDNEWPOS decision sayısı
- `total_decisions`: Toplam decision sayısı
- `total_filtered`: Toplam filtrelenen sayısı

### Execution Metrics
- `total_intents`: Toplam intent sayısı
- `executed_intents`: Executed intent sayısı
- `skipped_intents`: Skipped intent sayısı
- `error_intents`: Error intent sayısı
- `execution_rate`: Execution oranı (%)

### Intent Breakdown
- `sell_intents`: SELL intent sayısı
- `buy_intents`: BUY intent sayısı
- `add_intents`: ADD intent sayısı

### Safety Guards
- `max_intents_per_cycle_hit`: Max intents per cycle aşım sayısı
- `max_intents_per_day_hit`: Max intents per day aşıldı mı?

### Top Lists
- `top_symbols`: En çok decision üreten symbol'ler (top 10)
- `top_filter_reasons`: En çok filtrelenen nedenler (top 10)

---

## 🛡️ Safety Guards

### Max Intents Per Cycle
- **Default**: 20
- **Trigger**: Last execution plan'deki total_intents > max_intents_per_cycle
- **Action**: RUNALL → BLOCKED, session → BLOCKED

### Max Intents Per Day
- **Default**: 300
- **Trigger**: Session total_intents > max_intents_per_day
- **Action**: RUNALL → BLOCKED, session → BLOCKED

---

## 📄 Shadow Reports

### JSON Report (`shadow_report_YYYY-MM-DD.json`)

```json
{
  "session_date": "2025-12-15",
  "session_start_time": "2025-12-15T09:30:00",
  "session_end_time": "2025-12-15T16:00:00",
  "session_duration_minutes": 390,
  "status": "STOPPED",
  "blocked_reason": null,
  "metrics": {
    "cycles": {
      "total": 390,
      "successful": 385,
      "failed": 5
    },
    "decisions": {
      "karbotu": 45,
      "reducemore": 12,
      "addnewpos": 23,
      "total": 80,
      "filtered": 120
    },
    "execution": {
      "total_intents": 80,
      "executed": 75,
      "skipped": 5,
      "errors": 0,
      "execution_rate": 93.75
    },
    "intent_breakdown": {
      "sell": 50,
      "buy": 20,
      "add": 10
    },
    "safety_guards": {
      "max_intents_per_cycle_hit": 0,
      "max_intents_per_day_hit": false
    }
  },
  "top_symbols": {
    "MS PRK": 15,
    "WFC PRY": 12,
    ...
  },
  "top_filter_reasons": {
    "Cooldown active": 45,
    "Metrics not available": 30,
    ...
  }
}
```

### Human-Readable Report (`shadow_report_YYYY-MM-DD.txt`)

```
================================================================================
SHADOW LIVE REPORT - 2025-12-15
================================================================================

Session Duration: 09:30:00 - 16:00:00
Status: STOPPED

CYCLE METRICS
--------------------------------------------------------------------------------
Total Cycles: 390
Successful: 385
Failed: 5

DECISION METRICS
--------------------------------------------------------------------------------
KARBOTU: 45
REDUCEMORE: 12
ADDNEWPOS: 23
Total Decisions: 80
Total Filtered: 120

EXECUTION METRICS
--------------------------------------------------------------------------------
Total Intents: 80
Executed: 75
Skipped: 5
Errors: 0
Execution Rate: 93.75%

INTENT BREAKDOWN
--------------------------------------------------------------------------------
SELL: 50
BUY: 20
ADD: 10

SAFETY GUARDS
--------------------------------------------------------------------------------
Max Intents Per Cycle Hit: 0
Max Intents Per Day Hit: false

TOP 10 SYMBOLS (by decision count)
--------------------------------------------------------------------------------
  MS PRK: 15
  WFC PRY: 12
  ...

TOP 10 FILTER REASONS
--------------------------------------------------------------------------------
  Cooldown active: 45
  Metrics not available: 30
  ...

================================================================================
END OF REPORT
================================================================================
```

---

## 🚀 Kullanım

### 1. Shadow Live Runner'ı Başlat

```python
from app.psfalgo.shadow_live_runner import initialize_shadow_live_runner

runner = initialize_shadow_live_runner(config={
    'max_intents_per_cycle': 20,
    'max_intents_per_day': 300,
    'check_interval_seconds': 60
})

await runner.start()
```

### 2. API ile Başlat

```bash
POST /api/psfalgo/shadow/start
```

### 3. Status Kontrolü

```bash
GET /api/psfalgo/shadow/status
```

### 4. Durdur

```bash
POST /api/psfalgo/shadow/stop
```

---

## ⚠️ Önemli Notlar

1. **ZERO RISK**:
   - `dry_run` ASLA `false` yapılmayacak
   - Broker adapter çağrısı YOK
   - Execution layer değişmeyecek

2. **NO LOGIC CHANGES**:
   - Decision engine'lere ASLA dokunulmaz
   - Execution logic ASLA değişmeyecek
   - Sadece orchestration + metrik + raporlama

3. **Market-Aware**:
   - Market open → RUNALL start
   - Market close → RUNALL stop
   - TradingCalendar kullanılır

4. **Safety Guards**:
   - Max limits aşıldığında RUNALL → BLOCKED
   - Session → BLOCKED
   - Blocked reason kaydedilir

5. **Shadow Reports**:
   - Gün sonu otomatik rapor
   - JSON + human-readable format
   - `quant_engine/reports/shadow/` dizininde

---

## 📈 Sonraki Adımlar

1. ✅ ShadowLiveRunner oluşturuldu
2. ✅ API endpoints eklendi
3. ✅ Session metrics collection
4. ✅ Safety guards
5. ✅ Shadow report generation
6. ⏳ Test shadow live runner
7. ⏳ Haftalarca çalıştır ve gözlemle

---

## 🎯 Phase 6 Durumu

**TAMAMLANDI** ✅

- ShadowLiveRunner: ✅
- Market-aware orchestration: ✅
- Session metrics: ✅
- Safety guards: ✅
- Shadow reports: ✅
- API endpoints: ✅

**Sistem artık gerçek piyasa saatlerinde, gerçek market data ile, tamamen dry-run modunda uzun süre çalıştırılabilir!** 🔍






