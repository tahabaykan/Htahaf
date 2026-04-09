# 🚨 QUANT ENGINE — LLM OPERATIONAL GUIDE
# ═══════════════════════════════════════════════════════════════
# IF YOU ARE AN LLM (Claude, GPT, Gemini, or any AI assistant)
# AND THE USER IS ASKING ABOUT THE QUANT ENGINE, TRADING SYSTEM,
# TERMINAL ERRORS, OR DEBUGGING — YOU MUST READ THIS FILE FIRST.
#
# This file tells you WHERE to find logs, HOW the system works,
# and WHAT to check when something goes wrong.
# ═══════════════════════════════════════════════════════════════

---

## 🔴 STEP 1: WHEN USER REPORTS A PROBLEM — READ THE TERMINAL LOGS

### Terminal logs capture ALL output from every service session.

**Location:**
```
C:\StockTracker\quant_engine\data\logs\terminals\
```

**File naming:**
```
{service_name}_{YYYYMMDD}_{HHMMSS}.log
```

**The user may open/close terminals many times a day.** Each session creates a
separate log file. To find the MOST RECENT session for any service:

```powershell
# Find the latest backend log:
Get-ChildItem "C:\StockTracker\quant_engine\data\logs\terminals\backend_*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1

# Find the latest log for ANY service:
Get-ChildItem "C:\StockTracker\quant_engine\data\logs\terminals\*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 5

# Read the LAST 200 lines of the latest backend log:
Get-Content (
  Get-ChildItem "C:\StockTracker\quant_engine\data\logs\terminals\backend_*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
).FullName -Tail 200

# Search for errors across ALL recent logs:
Get-ChildItem "C:\StockTracker\quant_engine\data\logs\terminals\*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 5 |
  ForEach-Object { Select-String -Path $_.FullName -Pattern "ERROR|CRITICAL|Exception|Traceback" }
```

### Service Name → Log File Prefix

| Service (from baslat.py) | Log prefix | What runs inside |
|--------------------------|-----------|------------------|
| 1. Backend (FastAPI) | `backend_` | API + XNL Engine + ETF Guard + MM Decision |
| 3. Deeper Analysis Worker | `worker1_` | Deep analysis jobs |
| 4. Ticker Alert Worker | `ticker_alert_worker1_` | Price alerts |
| 5. Decision Helper Worker | `decision_helper_worker1_` | Decision pipeline |
| 6. Decision Helper V2 Worker | `decision_helper_v2_worker1_` | V2 pipeline |
| 7. Truth Ticks Cluster | `cluster_launcher_` | 6 truth tick workers |
| 8. Venue Collector | `venue_collector_worker1_` | Shadow mode data |
| 9. Greatest MM Worker | `greatest_mm_worker1_` | MM quant scoring |
| 10. Market Context Worker | `market_context_worker1_` | L1 market data feed |
| 11. QeBench Worker | `qebench_worker1_` | Fill recovery |
| 12. RevnBookCheck Terminal | `revnbookcheck_terminal_` | REV order recovery |
| 13. L1 Feed Terminal | `l1_feed_worker_` | 30s L1 updates |
| 14. QAGENTT Agent | `qagentt_learner_` | Learning agent |

### There is also a daily LOGURU log (structured, includes all processes sharing the same import):
```
C:\StockTracker\quant_engine\data\logs\app\quant_engine_YYYY-MM-DD.log
```
This file is rotated daily, compressed after 1 day, and retained for 7 days.

---

## 🔴 STEP 2: UNDERSTAND THE SYSTEM ARCHITECTURE

### Project Root
```
C:\StockTracker\quant_engine\
```

### Engine Execution Order (XNL Initial Cycle)
```
Phase 1:   REV + LT_TRIM    (decrease orders)      — HIGHEST priority
Phase 2:   KARBOTU           (decrease orders)
Phase 2.5: PATADD            (increase, priority=17) — pattern-based
Phase 3:   ADDNEWPOS         (increase, priority=15) — tumcsv-based
  ↓ exposure deducted
Phase 4:   MM                (increase, priority=10) — uses REMAINING exposure
  └── symbols claimed by PATADD/ADDNEWPOS are EXCLUDED from MM
```

### Key Subsystems

| Subsystem | Key File | Purpose |
|-----------|----------|---------|
| **MM Engine** | `app/mm/greatest_mm_engine.py` | 5-scenario MM score formula |
| **MM Decision** | `app/mm/greatest_mm_decision_engine.py` | Son5Tick + Volav + scoring → Decision |
| **PATADD** | `app/psfalgo/patadd_engine.py` | Ex-div pattern position increase |
| **ADDNEWPOS** | `app/psfalgo/addnewpos_engine.py` | New position opening |
| **XNL Engine** | `app/xnl/xnl_engine.py` | Automated trading cycle orchestrator |
| **Truth Ticks** | `app/market_data/truth_ticks_engine.py` | Tick filtering + Volav computation |
| **ETF Guard** | `app/terminals/etf_guard_terminal.py` | Market circuit breaker (cancel on ETF drops) |
| **GenObs** | `app/analysis/genobs_service.py` | Dashboard data aggregator |
| **Exposure** | `app/psfalgo/free_exposure_engine.py` | Free exposure calculation |

### Critical Redis Keys

| Key Pattern | Contents | TTL |
|------------|----------|-----|
| `market:l1:{symbol}` | Bid/Ask/Last/Spread | 2 min |
| `truth_ticks:inspect:{symbol}` | Truth ticks + path_dataset + Volav | 1 hour |
| `truthtick:latest:{symbol}` | Latest single truth tick | 10 min |
| `janall:metrics:{symbol}` | Fbtot, SFStot, FINAL_THG | varies |
| `etf_guard:state` | ETF Guard frozen/running state | 60s |
| `positions:{account}:{symbol}` | Current positions | varies |

---

## 🔴 STEP 3: KEY CONCEPTS

### Truth Ticks
- Only ticks with size ≥ 15 are considered
- FNRA venue: ONLY sizes 100 or 200 are allowed (strict binary rule)
- All other venues: any size ≥ 15 is valid
- These filtered prints are called "Truth Ticks"

### Son5Tick
- Mode (most frequent price) of last 5 truth ticks
- Used as the reference price in MM formula

### Volav (Volume-Averaged Levels)
- Clusters of truth ticks by price where heavy volume traded
- Volav1 = the #1 volume zone price
- **Always computed from 1-HOUR window** (fallback: 4h for illiquid)
- Used in MM Scenario 5 (VOLAV_ANCHOR) as Son5Tick replacement

### MM Formula
```
MM_Long  = 200×b + 4×(b/a) - 50×Ucuzluk
MM_Short = 200×a + 4×(a/b) + 50×Pahalilik

Where:
  b = Son5Tick - Entry    (distance from reference price to entry)
  a = Ask/Bid - Son5Tick  (distance to other side)
```

### ETF Guard
- Monitors: SPY, IWM, KRE, TLT, IEF, PFF every 15 seconds
- BEARISH trigger → cancel all BUY orders + freeze XNL 30s
- BULLISH trigger → cancel all SELL orders + freeze XNL 30s
- Runs INSIDE the backend process, not as a separate terminal

### Fbtot / SFStot
- Fbtot > 1.0 = stock is CHEAP relative to group (good for LONG)
- SFStot < 1.0 = stock is EXPENSIVE relative to group (good for SHORT)

---

## 🔴 STEP 4: COMMON DEBUGGING SCENARIOS

| User says... | What to check |
|-------------|---------------|
| "Orders not going through" | Backend log → `[XNL]`, `[GREATEST_MM]`, `free exposure` |
| "MM not working" | Backend log → `[GREATEST_MM_DECISION]`, check `MM_MIN_SCORE` |
| "System frozen" | Backend log → `[ETF_GUARD]`, check for `FROZEN` |
| "No truth ticks" | Cluster log → hammer connection, tick_store errors |
| "Exposure wrong" | Backend log → `[FREE_EXPOSURE]`, `effective_free_pct` |
| "PATADD not firing" | Backend log → `[PATADD]`, check filter reasons |
| "Connection issues" | Backend log → `[HAMMER]`, `[IBKR]`, `ConnectionError` |
| "Prices stale" | Check if Market Context Worker or L1 Feed running |

### Quick Error Search (run these PowerShell commands):

```powershell
# All errors in today's logs:
Select-String -Path "C:\StockTracker\quant_engine\data\logs\terminals\*_$(Get-Date -Format 'yyyyMMdd')*.log" -Pattern "ERROR|CRITICAL" | Select-Object -Last 30

# ETF Guard triggers today:
Select-String -Path "C:\StockTracker\quant_engine\data\logs\terminals\backend_*.log" -Pattern "ETF_GUARD.*TRIGGER" | Select-Object -Last 10

# MM rejection reasons:
Select-String -Path "C:\StockTracker\quant_engine\data\logs\terminals\backend_*.log" -Pattern "GREATEST_MM.*skipped|GREATEST_MM.*BLOCKED" | Select-Object -Last 20
```

---

## 📁 OTHER IMPORTANT FILES

| File | Purpose |
|------|---------|
| `baslat.py` | Main launcher — starts all terminals with log capture |
| `_tee_wrapper.py` | Captures terminal stdout+stderr to log files |
| `app/core/logger.py` | Loguru config (console + daily file + optional extra) |
| `app/config/settings.py` | Environment variables and defaults |
| `app/xnl/mm_settings.py` | MM-specific settings (thresholds, lot modes) |

---

## 🔴 STEP 5: DUAL PROCESS — DATA ISOLATION (CRITICAL)

### The system supports two broker accounts running simultaneously (Dual Process).
### You MUST understand which data is **SHARED** and which is **PER-ACCOUNT ISOLATED**.

### 🌍 SHARED DATA (Same for Both Accounts — Broker-Independent)

These are market/scoring data — a stock's valuation doesn't change based on which account holds it.

| Data | Source | Notes |
|------|--------|-------|
| **L1 Market Data** (bid/ask/last/spread) | Hammer Pro → DataFabric → Redis `market:l1:{symbol}` | ALWAYS from Hammer Pro, even for IBKR accounts |
| **Static Metrics** (FINAL_THG, GORT) | `StaticDataStore` → `janalldata.csv` | Loaded once per day |
| **Derived Scores** (FINAL_BB, FINAL_FB, ucuzluk/pahalilik) | `MetricsSnapshotAPI` (singleton, no account_id) | Computed from L1 + static data |
| **JFIN Candidates** | `StaticDataStore.get_all_symbols()` | Eligible symbol universe |
| **GRPAN / RWVAP Metrics** | Engine singletons | Group analysis, volume-weighted levels |
| **File Group Assignment** (BB, FB, SAS, SFS) | `grouping.py` → CSV | Which pool each symbol belongs to |
| **Truth Ticks / Volav** | Truth Ticks Cluster workers | Market microstructure data |
| **MM Settings** (est_cur_ratio, lot_mode) | `mm_settings.py` store | Same MM parameters for all accounts |

### 🔐 PER-ACCOUNT ISOLATED DATA (Separate for Each Account)

These are account-specific — positions, orders, and risk limits differ per broker account.

| Data | Key / Mechanism | Isolation Method |
|------|----------------|------------------|
| **Positions** | `psfalgo:positions:{account_id}` | Separate Redis key per account |
| **Exposure** (pot_total, cur_pct, pot_pct) | `psfalgo:exposure:{account_id}` | Separate Redis key per account |
| **Open Orders** | `psfalgo:open_orders:{account_id}` | Separate Redis key per account |
| **REV Order Queue** | `psfalgo:rev_queue:{account_id}` | Separate Redis key per account |
| **MinMax Area** (daily qty limits) | `minmaxarea_ham.csv` / `minmaxarea_ped.csv` | Separate CSV file per account |
| **Port Adjuster** (pot_max, avg_price) | V2 store `get_config(account_id)` | Account-parameterized function |
| **ADDNEWPOS Settings** | `get_settings(account_id)` | Per-account settings store |
| **HEAVY Settings** | `psfalgo:heavy_settings:{account_id}` | Separate Redis key per account |
| **Free Exposure** | `calculate_free_exposure(account_id)` | Account-parameterized function |
| **Exposure Thresholds** | `is_hard_risk_mode(account_id, ...)` | Per-account threshold service |
| **OrderController Tracking** | `_orders[provider]` partition | Partitioned dict by account_id |
| **Proposals** | ProposalStore with `account_id` filter | Filterable by account_id |

### 🔒 Account Pinning Mechanism (CRITICAL)

When XNL Engine starts for an account, `_active_account_id` is **pinned** at `start()` time.
All subsequent cycles (initial, front, refresh) use this pinned ID — they **NEVER** call
`get_trading_context()` at runtime. This prevents the account from "drifting" if the
DualProcessRunner switches accounts between cycles.

```
XNL.start()      → self._active_account_id = current_account  # PINNED
XNL.front_cycle  → uses self._active_account_id               # NOT get_trading_context()
XNL.refresh      → uses self._active_account_id               # NOT get_trading_context()
XNL.stop()       → self._active_account_id = None             # CLEARED
```

### Dual Process Flow (per account phase)

```
DualProcessRunner._run_loop():
  for account in [account_a, account_b]:
    1. Switch trading context → account
    2. Publish to Redis (all consumer keys)
    3. Cancel ALL open orders for this account
    4. Check & queue REV orders (DualAccountRevService)
    5. XNL.start(account)
       └── _run_initial_cycle(account)
           ├── prepare_cycle_request(account)  ← positions/exposure per-account
           ├── LT_TRIM → KARBOTU → PATADD → ADDNEWPOS → MM
           └── _send_orders_with_frontlama()
    6. Wait LONGEST_FRONT_CYCLE_SECONDS (3.5 min)
       └── Front cycles re-price existing orders using pinned account
    7. XNL.stop() — orders LEFT in market (not cancelled)
    8. Loop to next account
```

### ⚠️ COMMON MISTAKES TO AVOID

| Mistake | Why It's Wrong |
|---------|---------------|
| Using `get_trading_context()` inside XNL cycles | Account may have switched; use `_active_account_id` |
| Assuming MetricsSnapshotAPI is per-account | It's SHARED — market data is broker-independent |
| Mixing position data between accounts | Positions are keyed by `account_id` in Redis; never cross-read |
| Calling broker API without checking account_id | HAMPRO uses Hammer API; IBKR_PED uses IBKR Gateway |
| Starting DualProcess while STOPPING | Race condition — must wait for old task to complete |

---

> **REMEMBER:** The user expects you to READ the actual log files when debugging.
> Don't just guess — use the PowerShell commands above to find the latest logs,
> read them, and identify the actual error. The logs contain timestamps, module
> names, and full tracebacks. Everything you need is there.
