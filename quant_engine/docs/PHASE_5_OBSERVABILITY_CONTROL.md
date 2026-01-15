# Phase 5: Observability & Control Layer

## 📋 Genel Bakış

Phase 5, RUNALL + execution sisteminin **DIŞARIDAN gözlemlenebilir, kontrol edilebilir ve güvenli** hale getirilmesini sağlar.

**ÖNEMLİ**: Decision ve execution layer'a **ASLA dokunulmaz**. Sadece state, visibility ve kontrol eklenir.

---

## 🎯 Hedefler

1. **RUNALL State API**: Current state, cycle info, dry_run flag
2. **Execution Observability**: Son N ExecutionPlan, executed/skipped/error sayıları
3. **Decision Observability**: Son cycle DecisionResponse snapshot (READ-ONLY)
4. **Manual Controls**: RUNALL start/stop, dry_run toggle, emergency STOP
5. **Logging & Audit**: cycle_id bazlı log, decision→execution trace, human-readable audit trail

---

## 📁 Dosya Yapısı

```
quant_engine/app/psfalgo/
├── runall_state_api.py      # State API (observability & control)
├── runall_engine.py          # RUNALL orchestrator (updated: recording)
└── execution_engine.py        # Execution engine (no changes)

quant_engine/app/api/
└── psfalgo_routes.py         # REST API endpoints

quant_engine/tests/
└── test_runall_state_api.py  # Test suite
```

---

## 🔧 Bileşenler

### 1. RunallStateAPI (`runall_state_api.py`)

**Sorumluluklar:**
- Read-only state access
- Manual controls (start/stop/toggle)
- Execution observability (last N plans)
- Decision observability (last cycle snapshots)
- Audit trail

**Özellikler:**
- `get_state_snapshot()`: Current RUNALL state
- `get_execution_history(last_n)`: Last N execution plans
- `get_decision_snapshot(source)`: Last cycle DecisionResponse
- `record_execution_plan()`: Record execution for observability
- `record_decision_response()`: Record decision snapshot (READ-ONLY)
- `add_audit_entry()`: Add audit trail entry
- `start_runall()` / `stop_runall()`: Manual controls
- `toggle_dry_run()`: Toggle dry-run mode
- `emergency_stop()`: Emergency stop (immediate)

**Data Models:**
- `RunallStateSnapshot`: State snapshot
- `ExecutionObservability`: Execution plan observability
- `DecisionObservability`: Decision snapshot (READ-ONLY)

### 2. PSFALGO REST API (`psfalgo_routes.py`)

**Endpoints:**

#### State API
- `GET /api/psfalgo/state` - Get current RUNALL state
- `POST /api/psfalgo/start` - Start RUNALL (manual control)
- `POST /api/psfalgo/stop` - Stop RUNALL (manual control)
- `POST /api/psfalgo/emergency-stop` - Emergency stop
- `POST /api/psfalgo/toggle-dry-run` - Toggle dry-run mode

#### Execution Observability
- `GET /api/psfalgo/execution/history?last_n=10` - Get last N execution plans
- `GET /api/psfalgo/execution/last?source=KARBOTU` - Get last execution for source

#### Decision Observability (READ-ONLY)
- `GET /api/psfalgo/decision/snapshot?source=KARBOTU` - Get last cycle DecisionResponse snapshot

#### Audit Trail
- `GET /api/psfalgo/audit/trail?last_n=50` - Get last N audit entries

### 3. RUNALL Integration

**Değişiklikler:**
- `_step_run_karbotu()`: Decision snapshot recording
- `_step_run_reducemore()`: Decision snapshot recording
- `_step_run_addnewpos()`: Decision snapshot recording
- Execution plan recording (after execution)

**ÖNEMLİ**: Sadece **recording** yapılır, decision/execution logic'e dokunulmaz.

---

## 🔍 Observability Özellikleri

### 1. RUNALL State

```json
{
  "global_state": "RUNNING",
  "cycle_state": "KARBOTU_RUNNING",
  "cycle_id": 42,
  "loop_running": true,
  "dry_run_mode": true,
  "cycle_start_time": "2025-12-15T01:00:00",
  "next_cycle_time": "2025-12-15T01:01:00",
  "exposure": {
    "pot_total": 50000.0,
    "pot_max": 100000.0,
    "long_lots": 2000.0,
    "short_lots": 0.0,
    "net_exposure": 2000.0
  }
}
```

### 2. Execution Observability

```json
{
  "cycle_id": 42,
  "source": "KARBOTU",
  "execution_timestamp": "2025-12-15T01:00:05",
  "total_intents": 3,
  "executed_count": 2,
  "skipped_count": 1,
  "error_count": 0,
  "dry_run": true,
  "intents": [...]
}
```

### 3. Decision Observability (READ-ONLY)

```json
{
  "cycle_id": 42,
  "source": "KARBOTU",
  "decision_timestamp": "2025-12-15T01:00:00",
  "total_decisions": 2,
  "total_filtered": 1,
  "execution_time_ms": 15.2,
  "decisions": [...],
  "filtered_out": [...],
  "step_summary": {...}
}
```

### 4. Audit Trail

```json
{
  "timestamp": "2025-12-15T01:00:00",
  "event": "RUNALL_STARTED",
  "cycle_id": 42,
  "details": {
    "manual": true
  }
}
```

---

## 🎮 Manual Controls

### Start RUNALL
```bash
POST /api/psfalgo/start
```

### Stop RUNALL
```bash
POST /api/psfalgo/stop
```

### Emergency Stop
```bash
POST /api/psfalgo/emergency-stop
```
**Not**: Immediately stops RUNALL and execution, marks as BLOCKED.

### Toggle Dry-Run
```bash
POST /api/psfalgo/toggle-dry-run
```
**Not**: Toggles both RUNALL and ExecutionEngine dry_run mode.

---

## 📊 Logging & Audit

### Cycle-Based Logging

Her cycle için:
- Cycle ID
- Start/end timestamps
- Decision counts
- Execution counts
- Errors (if any)

### Decision → Execution Trace

Her decision için:
- Decision timestamp
- Cycle ID
- Source (KARBOTU/REDUCEMORE/ADDNEWPOS)
- Execution intent mapping
- Execution status (EXECUTED/SKIPPED/ERROR)

### Audit Trail

Human-readable audit trail:
- Event name
- Timestamp
- Cycle ID (if applicable)
- Details (JSON)

**Events:**
- `RUNALL_STARTED`
- `RUNALL_STOPPED`
- `DRY_RUN_TOGGLED`
- `EMERGENCY_STOP`
- `EXECUTION_COMPLETE`
- `DECISION_RECORDED`

---

## ✅ Test Sonuçları

```
=== RunallStateAPI Test ===

1. Testing state snapshot (no engine):
   No engine available (expected)

2. Testing decision response recording:
   Recorded: 1 decisions, 0 filtered
   Source: KARBOTU, Cycle: 1

3. Testing execution plan recording:
   Recorded: 1 execution plans in history
   Last: KARBOTU cycle=1, 1 executed, 0 skipped

4. Testing audit trail:
   Recorded: 1 audit entries
   Last: TEST_EVENT at 2025-12-15T01:56:03.470033

5. Testing manual controls (no engine):
   Start result: False - RunallEngine not available
   Toggle dry-run result: False - RunallEngine not available

[OK] RunallStateAPI test complete
```

---

## 🚀 Kullanım

### 1. State API'yi Initialize Et

```python
from app.psfalgo.runall_state_api import initialize_runall_state_api, get_runall_state_api

# Initialize
initialize_runall_state_api()

# Get instance
state_api = get_runall_state_api()
```

### 2. RUNALL Engine'i Bağla

```python
from app.psfalgo.runall_engine import RunallEngine

runall_engine = RunallEngine(config={...})
state_api.set_runall_engine(runall_engine)
```

### 3. State Snapshot Al

```python
snapshot = state_api.get_state_snapshot()
print(f"State: {snapshot.global_state}, Cycle: {snapshot.cycle_id}")
```

### 4. Execution History Al

```python
history = state_api.get_execution_history(last_n=10)
for obs in history:
    print(f"{obs.source}: {obs.executed_count} executed, {obs.skipped_count} skipped")
```

### 5. Decision Snapshot Al

```python
snapshot = state_api.get_decision_snapshot('KARBOTU')
print(f"Decisions: {snapshot.total_decisions}, Filtered: {snapshot.total_filtered}")
```

### 6. Manual Control

```python
# Start RUNALL
result = await state_api.start_runall()

# Stop RUNALL
result = await state_api.stop_runall()

# Toggle dry-run
result = state_api.toggle_dry_run()

# Emergency stop
result = await state_api.emergency_stop()
```

---

## ⚠️ Önemli Notlar

1. **Decision/Execution Logic'e Dokunma**: Sadece recording yapılır, logic değişmez.
2. **Read-Only Decision Observability**: Decision snapshots sadece görüntülenir, değiştirilmez.
3. **Manual Controls**: Start/stop/toggle sadece RUNALL lifecycle'ı kontrol eder, decision/execution logic'e dokunmaz.
4. **Emergency Stop**: Execution çağrısını keser, RUNALL'ı BLOCKED durumuna alır.
5. **Audit Trail**: Human-readable, cycle_id bazlı, decision→execution trace içerir.

---

## 📈 Sonraki Adımlar

1. ✅ RunallStateAPI oluşturuldu
2. ✅ PSFALGO REST API routes oluşturuldu
3. ✅ RUNALL integration (recording) tamamlandı
4. ⏳ API endpoints test edilecek
5. ⏳ Frontend integration (UI for observability)

---

## 🎯 Phase 5 Durumu

**TAMAMLANDI** ✅

- RunallStateAPI: ✅
- REST API Routes: ✅
- RUNALL Integration: ✅
- Test Suite: ✅
- Documentation: ✅

**Sistem artık CAM GİBİ gözlemlenebilir!** 🔍






