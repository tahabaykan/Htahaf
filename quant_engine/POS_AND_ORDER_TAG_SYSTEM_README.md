# 📋 POS & ORDER TAG SYSTEM — Complete README

> **Version**: Dual Tag v4 (Per-Account)  
> **Last Updated**: 2026-03-07  
> **Purpose**: This document explains the ENTIRE tag-based order classification, routing, sacrifice, and lifecycle system used by the PSFALGO Quant Engine. It is designed to be read by developers AND LLMs to fully understand how positions and orders are tagged, tracked, and managed across dual accounts.

---

## Table of Contents

1. [Why Tags Exist — The Big Picture](#1-why-tags-exist--the-big-picture)
2. [The Two Tag Dimensions](#2-the-two-tag-dimensions)
3. [POS TAG — Position-Level Identity](#3-pos-tag--position-level-identity)
4. [ORDER TAG — The v4 Format](#4-order-tag--the-v4-format)
5. [Engine → Tag Mapping (Who Produces What)](#5-engine--tag-mapping-who-produces-what)
6. [Tag Lifecycle (Birth → Front → Fill → REV)](#6-tag-lifecycle-birth--front--fill--rev)
7. [Frontlama Tag Classification & Sacrifice Limits](#7-frontlama-tag-classification--sacrifice-limits)
8. [Cycle Timing & Routing](#8-cycle-timing--routing)
9. [Per-Account Isolation](#9-per-account-isolation)
10. [REV Order Tags](#10-rev-order-tags)
11. [Special Tags (FR_, OZEL_, REDUCEMORE)](#11-special-tags-fr_-ozel_-reducemore)
12. [Exposure-Based Adjustments](#12-exposure-based-adjustments)
13. [Engine Priority & Conflict Resolution](#13-engine-priority--conflict-resolution)
14. [Lot Rules](#14-lot-rules)
15. [30+ Real-World Scenarios](#15-30-real-world-scenarios)
16. [File Reference](#16-file-reference)
17. [FAQ & Common Confusions](#17-faq--common-confusions)

---

## 1. Why Tags Exist — The Big Picture

The Quant Engine runs **5+ independent trading engines** across **2 broker accounts** simultaneously. Without tags, it would be impossible to know:

- "Which engine created this order?"
- "Is this position part of our market-making strategy or long-term holding?"
- "How aggressively should frontlama push this order toward a fill?"
- "When the fill comes back, how should the REV (reversal) order be configured?"
- "Which cycle timer should manage this order's re-evaluation?"

**Tags solve ALL of these problems with a single, parseable string.**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THE TAG SYSTEM IN ONE DIAGRAM                    │
│                                                                     │
│  Engine produces order                                              │
│       ↓                                                             │
│  ORDER TAG assigned (e.g., LT_PA_LONG_INC)                         │
│       ↓                                                             │
│  Tag determines:                                                    │
│    ├── Cycle routing (LT_INCREASE → 3.5 min front cycle)            │
│    ├── Sacrifice limits ($0.10 max, 10% of spread)                  │
│    ├── Frontlama permission (INC = conservative)                    │
│    └── REV configuration (if filled → Take Profit $0.09)            │
│       ↓                                                             │
│  Fill received → POS TAG updated in Redis                           │
│       ↓                                                             │
│  POS TAG determines:                                                │
│    ├── Which engines can operate on this position next               │
│    ├── Future ORDER TAGs will embed this POS TAG                    │
│    └── REV thresholds (MM vs LT dollar amounts)                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Two Tag Dimensions

The system uses **two independent tag dimensions** that work together:

| Dimension | Scope | Stored Where | Example | Updates When |
|-----------|-------|-------------|---------|-------------|
| **POS TAG** | Per position, per account | Redis `psfalgo:pos_tags:{account_id}` | `"MM"` or `"LT"` | On fill (INC engines only) |
| **ORDER TAG** | Per order | Embedded in order's `tag` field | `"LT_PA_LONG_INC"` | At order creation time |

**Key distinction**: POS TAG is about *what the position IS*. ORDER TAG is about *what this specific order DOES*.

---

## 3. POS TAG — Position-Level Identity

### What Is It?

POS TAG answers one question: **"Is this position a Market-Making (MM) position or a Long-Term (LT) position?"**

```
POS TAG = MM  →  This position was opened by the MM engine (short-term spread capture)
POS TAG = LT  →  This position was opened by PA/AN engine (long-term conviction trade)
```

### Storage Format

```
Redis Key:  psfalgo:pos_tags:HAMPRO
Value:      {"KEY-J": "MM", "AHL": "LT", "DCOMG": "MM", "BKW": "LT"}

Redis Key:  psfalgo:pos_tags:IBKR_PED
Value:      {"KEY-J": "MM", "AHL": "LT", "DCOMG": "LT"}
                                           ^^^^^^^^^^^^
                               SAME SYMBOL, DIFFERENT TAG per account!
```

### The 5 Rules of POS TAG

```
╔══════════════════════════════════════════════════════════════════════════╗
║  RULE 1: "First engine sets the POS TAG"                               ║
║    • MM engine opens position → POS TAG = MM                           ║
║    • PA/AN engine opens position → POS TAG = LT                        ║
║                                                                        ║
║  RULE 2: "LT dominance — PA/AN always converts to LT"                  ║
║    • Existing MM position + PA fill same direction → MM becomes LT     ║
║    • Once LT, stays LT until position is fully closed                  ║
║                                                                        ║
║  RULE 3: "MM never overwrites LT"                                      ║
║    • If POS TAG = LT and MM fill arrives → POS TAG stays LT           ║
║                                                                        ║
║  RULE 4: "DEC engines don't change POS TAG"                            ║
║    • KB (Karbotu) fill → POS TAG unchanged                            ║
║    • TRIM (LT_TRIM) fill → POS TAG unchanged                         ║
║                                                                        ║
║  RULE 5: "Position closure removes POS TAG"                            ║
║    • qty reaches 0 → POS TAG deleted from Redis                       ║
║    • Next engine to open this symbol gets a fresh POS TAG              ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### Default Value

If a symbol has no POS TAG entry in Redis → **defaults to "MM"** (migration default for pre-existing positions).

### Code

```python
# app/psfalgo/position_tag_store.py
store = get_position_tag_store()
tag = store.get_tag("AAPL", "HAMPRO")         # Returns "MM" or "LT"
store.set_tag("AAPL", "LT", "HAMPRO")         # Explicit set
store.update_on_fill("AAPL", "PA", "HAMPRO")   # PA fill → LT
store.remove_tag("AAPL", "HAMPRO")             # Position closed
```

---

## 4. ORDER TAG — The v4 Format

### Format Specification

```
{POS}_{ENGINE}_{DIRECTION}_{ACTION}

  POS       =  MM | LT                   (from POS TAG — what the position IS)
  ENGINE    =  MM | PA | AN | KB | TRIM   (which engine created this order)
  DIRECTION =  LONG | SHORT               (position direction)
  ACTION    =  INC | DEC                   (increasing or decreasing the position)
```

### All Valid v4 Tags

#### INCREASE Tags (New Risk / Position Growth)

| ORDER TAG | Engine | What It Means | Broker Action |
|-----------|--------|---------------|---------------|
| `MM_MM_LONG_INC` | Greatest MM | MM engine opens new long | BUY |
| `MM_MM_SHORT_INC` | Greatest MM | MM engine opens new short | SELL/SHORT |
| `LT_PA_LONG_INC` | PATADD | Pattern-based new long | BUY |
| `LT_PA_SHORT_INC` | PATADD | Pattern-based new short | SELL/SHORT |
| `LT_AN_LONG_INC` | ADDNEWPOS | Auto-discovery new long | BUY |
| `LT_AN_SHORT_INC` | ADDNEWPOS | Auto-discovery new short | SELL/SHORT |

#### DECREASE Tags (Risk Reduction / Profit Taking)

| ORDER TAG | Engine | What It Means | Broker Action |
|-----------|--------|---------------|---------------|
| `MM_KB_LONG_DEC` | Karbotu | KB sells MM long position | SELL |
| `MM_KB_SHORT_DEC` | Karbotu | KB covers MM short position | BUY/COVER |
| `LT_KB_LONG_DEC` | Karbotu | KB sells LT long position | SELL |
| `LT_KB_SHORT_DEC` | Karbotu | KB covers LT short position | BUY/COVER |
| `MM_TRIM_LONG_DEC` | LT_TRIM | TRIM sells MM long position | SELL |
| `MM_TRIM_SHORT_DEC` | LT_TRIM | TRIM covers MM short position | BUY/COVER |
| `LT_TRIM_LONG_DEC` | LT_TRIM | TRIM sells LT long position | SELL |
| `LT_TRIM_SHORT_DEC` | LT_TRIM | TRIM covers LT short position | BUY/COVER |

### Why 4 Parts?

Each part serves a distinct downstream consumer:

```
LT_PA_LONG_INC
│  │   │    │
│  │   │    └── ACTION: INC → Frontlama knows "this adds risk" → strict limits
│  │   └─────── DIRECTION: LONG → REV knows which way to reverse
│  └─────────── ENGINE: PA → Fill handler knows to set POS TAG = LT
└────────────── POS TAG: LT → Cycle router sends to LT_INCREASE (3.5 min)
```

---

## 5. Engine → Tag Mapping (Who Produces What)

### MM Engine (Greatest MM)

```
Always produces: MM_MM_{LONG|SHORT}_INC
POS part: Always "MM" (hardcoded)
ENGINE part: Always "MM"
ACTION: Always "INC" (MM only opens new positions)

Example: MM decides BUY DCOMG → tag = "MM_MM_LONG_INC"
```

### PATADD Engine

```
Always produces: LT_PA_{LONG|SHORT}_INC
POS part: Always "LT" (hardcoded — PA ALWAYS results in LT)
ENGINE part: Always "PA"
ACTION: Always "INC" (PA only adds to positions)

Example: PA decides BUY GOOG → tag = "LT_PA_LONG_INC"
```

### ADDNEWPOS Engine

```
Always produces: LT_AN_{LONG|SHORT}_INC
POS part: Always "LT" (same logic as PA)
ENGINE part: Always "AN"
ACTION: Always "INC" (AN only creates new positions)

Example: AN decides SHORT CVX → tag = "LT_AN_SHORT_INC"
```

### KARBOTU Engine (Dynamic POS TAG!)

```
Produces: {POS}_KB_{LONG|SHORT}_DEC
POS part: DYNAMIC — reads from PositionTagStore for the ACTIVE ACCOUNT
ENGINE part: Always "KB"
ACTION: Always "DEC" (KB only reduces positions)

CRITICAL: Same symbol CAN produce DIFFERENT tags in different accounts!

Example (HAMPRO, DCOMG is MM):
  store.get_tag("DCOMG", "HAMPRO") → "MM"
  → tag = "MM_KB_LONG_DEC"

Example (IBKR_PED, DCOMG is LT):
  store.get_tag("DCOMG", "IBKR_PED") → "LT"
  → tag = "LT_KB_LONG_DEC"
```

### LT_TRIM Engine (Dynamic POS TAG!)

```
Produces: {POS}_TRIM_{LONG|SHORT}_DEC
POS part: DYNAMIC — reads from PositionTagStore
ENGINE part: Always "TRIM"
ACTION: Always "DEC" (TRIM only reduces positions)

Example: store.get_tag("BKW", "HAMPRO") → "LT"
  → tag = "LT_TRIM_LONG_DEC"
```

---

## 6. Tag Lifecycle (Birth → Front → Fill → REV)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         COMPLETE TAG LIFECYCLE                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  PHASE 1: ENGINE CREATES ORDER                                         │
│  ─────────────────────────────                                         │
│  Karbotu → {symbol:"AHL", action:"SELL", qty:200, tag:"LT_KB_LONG_DEC"}│
│                                                                        │
│  PHASE 2: FRONTLAMA EVALUATES (optional)                               │
│  ──────────────────────────────────────                                 │
│  Front cycle fires → tag gets "FR_" prefix if price modified           │
│  tag: "LT_KB_LONG_DEC" → "FR_LT_KB_LONG_DEC"                         │
│  price: $34.75 → $34.72 (1¢ below truth tick)                          │
│                                                                        │
│  PHASE 3: BROKER SEND                                                  │
│  ────────────────────                                                  │
│  Order sent to Hammer Pro or IBKR with tag as orderRef                 │
│  Broker sees: FR_LT_KB_LONG_DEC                                       │
│                                                                        │
│  PHASE 4: FILL PROCESSING                                              │
│  ────────────────────────                                              │
│  fill_tag_handler receives fill:                                       │
│    1. Strip prefixes: FR_LT_KB_LONG_DEC → LT_KB_LONG_DEC              │
│    2. Extract engine: parts[1] = "KB"                                  │
│    3. KB is DEC engine → POS TAG unchanged                             │
│    4. Check if qty=0 → if so, remove POS TAG                          │
│                                                                        │
│  PHASE 5: REV ORDER (if applicable)                                    │
│  ──────────────────────────────────                                    │
│  RevnBookCheck detects: befday=600, current=400 → gap=200              │
│    Original fill tag: "LT_KB_LONG_DEC" → DEC → RELOAD type            │
│    POS TAG: "LT" → threshold = $0.08                                  │
│    REV order: BUY 200, tag = "REV_RL_LT_KB_BUY"                       │
│    Sent DIRECTLY to broker (NOT through frontlama!)                    │
│                                                                        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Frontlama Tag Classification & Sacrifice Limits

### How Frontlama Classifies Tags

Frontlama maps every ORDER TAG to one of **8 OrderTag enums** using substring matching:

```python
# STEP 1: Direct match (catches v4 tags)
if 'MM_LONG_INC' in tag:  → OrderTag.MM_LONG_INC   # Catches "MM_MM_LONG_INC"
if 'LT_LONG_DEC' in tag:  → OrderTag.LT_LONG_DEC   # Catches "LT_KB_LONG_DEC"

# STEP 2: Legacy parse (fallback for old-format tags)
is_lt  = 'LT' in tag or 'TRIM' in tag
is_mm  = 'MM' in tag
is_inc = 'INC' in tag
is_dec = 'DEC' in tag
# → combines these booleans to pick the right enum
```

### The 4 Sacrifice Tiers

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  SACRIFICE LIMITS — How much price "edge" can frontlama give up            ║
╠════════════════╦═══════════╦════════════╦════════════════════════════════════╣
║  Tag Category  ║ Max Cent  ║ Max Ratio  ║ Philosophy                        ║
╠════════════════╬═══════════╬════════════╬════════════════════════════════════╣
║  MM_*_DEC      ║  $0.60    ║   50%      ║ 🔥 Kar kilitleme — EN AGRESİF     ║
║  LT_*_DEC      ║  $0.35    ║   25%      ║ 🟢 Pozisyon azaltma — agresif     ║
║  LT_*_INC      ║  $0.10    ║   10%      ║ 🟡 Yeni LT risk — kısıtlı        ║
║  MM_*_INC      ║  $0.07    ║    7%      ║ 🔴 Yeni MM risk — EN KATI         ║
╚════════════════╩═══════════╩════════════╩════════════════════════════════════╝

BOTH conditions must pass:
  ✅ sacrificed_cents ≤ max_cent_limit
  ✅ sacrifice_ratio  ≤ max_ratio_limit (ratio = cents / spread)

If EITHER fails → fronting REJECTED, order stays at original price.
```

### Base Price Calculation

Sacrifice is ALWAYS measured from the **Base Price** — where the order WOULD be placed from scratch:

```
SELL order: base_price = ask - (spread × 0.15)
BUY order:  base_price = bid + (spread × 0.15)

Then: sacrificed_cents = |base_price - front_price|
      sacrifice_ratio  = sacrificed_cents / spread
```

### Front Price Calculation

```
SELL → front_price = truth_tick - $0.01  (go below truth to get filled)
BUY  → front_price = truth_tick + $0.01  (go above truth to get filled)
```

### Truth Tick Validation

Not every trade print is trustworthy. Frontlama validates:

```
FNRA/FINRA/DARK venues: size MUST be exactly 100 or 200 (no odd lots)
Other venues (NYSE, ARCA): size ≥ 15
No price / No size → REJECTED (no fronting without valid truth tick)
Spread < $0.04 → REJECTED (spread too tight for fronting)
```

---

## 8. Cycle Timing & Routing

### The 4 Cycle Categories

Every order is routed to one of 4 cycle categories based on tag substring matching:

```python
if ('LT' in tag or 'PAT' in tag) and 'INC' in tag:   → LT_INCREASE
if ('LT' in tag or 'KARBOTU' in tag) and 'DEC' in tag: → LT_DECREASE
if 'MM' in tag and 'INC' in tag:                       → MM_INCREASE
if 'MM' in tag and 'DEC' in tag:                       → MM_DECREASE
```

### Cycle Timing Table

```
╔═══════════════╦═══════════════╦═══════════════╦══════════════════════════════════╗
║  Category     ║  Front Cycle  ║  Refresh      ║  Description                     ║
╠═══════════════╬═══════════════╬═══════════════╬══════════════════════════════════╣
║  LT_INCREASE  ║   3.5 min     ║   8 min       ║  Most conservative (new LT risk) ║
║  LT_DECREASE  ║   2 min       ║   5 min       ║  Aggressive (reduce LT position) ║
║  MM_INCREASE  ║   2 min       ║   3 min       ║  Controlled (new MM risk)         ║
║  MM_DECREASE  ║   30 sec      ║   1 min       ║  🔥 Most aggressive (MM profit)   ║
╚═══════════════╩═══════════════╩═══════════════╩══════════════════════════════════╝
```

**Why MM_DECREASE is 30 seconds**: OZEL tasfiye (liquidation) and Karbotu MM profit-taking orders need to execute FAST. Every 30 seconds, frontlama re-evaluates these orders and pushes them closer to the truth tick.

### Routing Examples

| ORDER TAG | Routes To | Front Cycle |
|-----------|-----------|-------------|
| `LT_PA_LONG_INC` | LT_INCREASE | 3.5 min |
| `LT_AN_SHORT_INC` | LT_INCREASE | 3.5 min |
| `LT_KB_LONG_DEC` | LT_DECREASE | 2 min |
| `LT_TRIM_LONG_DEC` | LT_DECREASE | 2 min |
| `MM_KB_LONG_DEC` | MM_DECREASE | 30 sec |
| `MM_TRIM_SHORT_DEC` | MM_DECREASE | 30 sec |
| `MM_MM_LONG_INC` | MM_INCREASE | 2 min |
| `OZEL_MM_MM_LONG_DEC` | MM_DECREASE | 30 sec |
| `FR_LT_PA_LONG_INC` | LT_INCREASE | 3.5 min |

---

## 9. Per-Account Isolation

### The Problem (Pre-v4)

Before per-account isolation, a **single Redis key** was shared:

```
psfalgo:pos_tags → {"DCOMG": "MM", "BKW": "LT"}  // SHARED across accounts!
```

If HAMPRO got a PA fill on DCOMG (→ LT), IBKR_PED would **incorrectly** see DCOMG as LT even though IBKR_PED's DCOMG was still an MM position.

### The Solution (v4)

Each account now has its **own Redis key**:

```
psfalgo:pos_tags:HAMPRO   → {"DCOMG": "MM", "BKW": "LT"}
psfalgo:pos_tags:IBKR_PED → {"DCOMG": "LT", "BKW": "MM"}
```

### How account_id Flows Through the System

```
DualProcessRunner
  ├── Sets active account: psfalgo:xnl:running_account = "HAMPRO"
  ├── Calls XNLEngine.start(account_id="HAMPRO")
  │     └── _active_account_id = "HAMPRO" (PINNED at start, never changes mid-run)
  │
  ├── Engine Order Generation
  │     ├── _run_karbotu(account_id) → KB reads store.get_tag(sym, "HAMPRO")
  │     ├── _run_lt_trim(account_id) → TRIM reads store.get_tag(sym, "HAMPRO")
  │     ├── _run_patadd(account_id) → Always LT (hardcoded)
  │     └── _run_mm(account_id) → checks store.get_tag for LT block
  │
  ├── Fill Processing
  │     ├── Hammer fill → account_id="HAMPRO"
  │     └── IBKR fill → account_id="IBKR_PED"
  │     └── fill_tag_handler → store.update_on_fill(sym, engine, account_id)
  │
  └── Account Resolution Fallback
        Priority 1: psfalgo:xnl:running_account
        Priority 2: psfalgo:trading:account_mode
        Fallback:   "HAMPRO" (primary account)
```

---

## 10. REV Order Tags

### REV Format

```
REV_{TYPE}_{POS}_{ENGINE}_{ACTION}

TYPE   = TP (Take Profit) | RL (Reload)
POS    = MM | LT
ENGINE = MM | PA | AN | KB | TRIM
ACTION = BUY | SELL
```

### REV Type Logic

```
Original fill was INC (position grew)   → REV type = TAKE PROFIT
  "We added, now we reverse to lock profit"

Original fill was DEC (position shrank) → REV type = RELOAD
  "We reduced, now we reverse to refill"
```

### REV Threshold Table

| POS TAG | REV Type | Dollar Threshold | Logic |
|:-------:|----------|:----------------:|-------|
| MM | Take Profit | $0.05 | MM profit — tight target (quick in/out) |
| LT | Take Profit | $0.09 | LT profit — wider target (more conviction) |
| MM | Reload | $0.13 | MM reload — generous to refill cheaply |
| LT | Reload | $0.08 | LT reload — moderate refill target |

### REV Example

```
KB sold 200 shares of MM long position (HAMPRO/KEY-J):
  Fill tag: MM_KB_LONG_DEC → DEC → RELOAD type
  POS TAG: MM → threshold = $0.13
  REV tag: REV_RL_MM_KB_BUY
  → BUY 200 KEY-J, threshold $0.13 below fill price
  → Sent DIRECTLY to broker (bypasses frontlama entirely!)
```

### ⚠️ CRITICAL: REV Orders Do NOT Go Through Frontlama

REV orders use their own pricing logic in `revorder_engine.py` and are sent **directly** to the broker. They are never evaluated by the frontlama sacrifice system.

---

## 11. Special Tags (FR_, OZEL_, REDUCEMORE)

### FR_ Prefix (Frontlama Modified)

When frontlama modifies an order's price, the tag gets an `FR_` prefix:

```
Original:      LT_KB_LONG_DEC
After front:   FR_LT_KB_LONG_DEC
```

**Rules**:
- Added exactly once: `if not tag.startswith('FR_'): tag = f"FR_{tag}"`
- `FR_FR_` is impossible (guard prevents double-prefix)
- Does NOT affect tag classification (parsers handle it)
- Preserved through fill processing (stripped during engine extraction)

### OZEL_ Prefix (Forced Liquidation)

When PA/AN wants to trade in the **opposite direction** of an existing MM position:

```
Scenario: MM long +500, PA wants SHORT
  → OZEL liquidation: SELL 500 @ aggressive price
  → Tag: OZEL_MM_MM_LONG_DEC
  → Routes to MM_DECREASE (30 sec cycle, $0.60/50% sacrifice!)
  → After liquidation, PA order comes in next cycle
```

### REDUCEMORE Tags

Emergency position reduction when exposure is critically high:

```
REDUCEMORE_LONG_DEC           → Standard emergency sell
REDUCEMORE_LONG_DEC_EMERGENCY → Critical emergency sell
```

---

## 12. Exposure-Based Adjustments

Frontlama adjusts **ratio limits** (never cent limits) based on portfolio exposure:

```
╔═══════════════════╦════════════════════════════╦══════════════════════════════════╗
║  Exposure Level   ║  INC Orders                ║  DEC Orders                      ║
╠═══════════════════╬════════════════════════════╬══════════════════════════════════╣
║  < 60%            ║  ratio +5% (more lenient)  ║  ratio +5% (more lenient)        ║
║  60-70% (BASE)    ║  No change                 ║  No change                       ║
║  70-80%           ║  ratio -5% (tighter)       ║  ratio -5% (tighter)             ║
║  80-90%           ║  ratio -8% (much tighter)  ║  ratio -8% (much tighter)        ║
║  90-95%           ║  ❌ FORBIDDEN               ║  ratio +3% (encourage sells!)    ║
║  95-100%+         ║  ❌ FORBIDDEN               ║  ratio +5% (maximum urgency!)    ║
╚═══════════════════╩════════════════════════════╩══════════════════════════════════╝
```

**Key insight**: At 90%+ exposure, INC orders are BLOCKED from fronting (cannot push harder to buy), but DEC orders get MORE aggressive fronting (push harder to sell/reduce).

---

## 13. Engine Priority & Conflict Resolution

### Execution Priority (Highest → Lowest)

```
1. LT_TRIM      →  Immediate risk reduction (runs first)
2. KARBOTU      →  Step-based profit taking
3. PATADD       →  Pattern-based position additions
4. ADDNEWPOS    →  Auto-discovery new positions
5. MM           →  Market-making (lowest priority)
```

### Symbol Exclusion Rule

**A symbol can only belong to ONE engine per cycle.** If LT_TRIM claims AAPL, Karbotu skips AAPL, and MM skips AAPL.

### Direction Conflict Resolution

```
Same symbol, SAME direction:
  → LOT COORDINATION: second engine gets remaining lot only

Same symbol, OPPOSITE direction:
  → MM loses to ANY non-MM engine (always)
  → Non-MM vs Non-MM: price gap ≥ $0.08 → both kept; < $0.08 → first wins

MM LT Position Block:
  → MM engine CANNOT operate on LT-tagged positions
  → If store.get_tag(symbol) == "LT" AND position exists → MM BLOCKED
```

---

## 14. Lot Rules

```
DECREASE (KB, TRIM):
  Minimum: 125 lots
  Rounding: floor to 100
  400-lot rule: if remaining < 400 after sell → sell ENTIRE position

INCREASE (PA, AN):
  Minimum: 200 lots
  Rounding: round to 100

MM:
  Minimum: 200 lots
  Dynamic: based on free exposure and AVG_ADV
```

---

## 15. 30+ Real-World Scenarios

### Scenario 1: Normal Karbotu Sell on MM Position

```
Account: HAMPRO | Symbol: KEY-J | Position: +800 (LONG) | POS TAG: MM

Karbotu Step 3 (40%):
  Raw lot: 800 × 0.40 = 320 → floor(320/100)×100 = 300
  300 ≥ 125 → ✅ | Remaining: 800-300 = 500 ≥ 400 → no 400-lot rule

Order: SELL 300 KEY-J | Tag: "MM_KB_LONG_DEC"
Cycle: MM_DECREASE → 30 sec front cycle
Sacrifice: $0.60 max, 50% ratio max
```

### Scenario 2: Same Symbol, Different Accounts

```
HAMPRO:   DCOMG POS TAG = MM →  KB tag = "MM_KB_LONG_DEC" → MM_DECREASE (30 sec)
IBKR_PED: DCOMG POS TAG = LT →  KB tag = "LT_KB_LONG_DEC" → LT_DECREASE (2 min)

→ SAME symbol, SAME engine, DIFFERENT tags, DIFFERENT cycles!
```

### Scenario 3: PA Fill Changes POS TAG

```
Account: HAMPRO | Symbol: KEY-J | POS TAG: MM | Position: +800

PATADD generates: BUY 400 KEY-J, tag: "LT_PA_LONG_INC" → fill happens

fill_tag_handler:
  engine = "PA" → PA is INC engine → set_tag("KEY-J", "LT", "HAMPRO")
  POS TAG: MM → LT (for HAMPRO only! IBKR_PED still MM)

Next KB cycle for HAMPRO:
  store.get_tag("KEY-J", "HAMPRO") → "LT"
  Tag: "LT_KB_LONG_DEC" (was "MM_KB_LONG_DEC" before PA fill!)
  → Now routes to LT_DECREASE (2 min) instead of MM_DECREASE (30 sec)
```

### Scenario 4: MM Blocked on LT Position

```
Account: IBKR_PED | Symbol: AHL | Position: +600 | POS TAG: LT

Greatest MM wants to BUY AHL (good MM score):
  store.get_tag("AHL", "IBKR_PED") → "LT"
  pos exists AND qty > 0 AND tag == "LT"
  → ❌ BLOCKED: "MM cannot operate on LT positions"
  MM picks next-best symbol instead.
```

### Scenario 5: OZEL Liquidation Before PA

```
Account: HAMPRO | Symbol: SRE | Position: -500 (SHORT) | POS TAG: MM

PATADD wants LONG on SRE (opposite direction):
  → OZEL liquidation: BUY 500 @ ask-spread×0.15
  → Tag: "OZEL_MM_MM_SHORT_DEC"
  → Cycle: MM_DECREASE (30 sec, $0.60/50% sacrifice — most aggressive!)
  → After fill: PA order comes next cycle with "LT_PA_LONG_INC"
```

### Scenario 6: REV After KB Fill

```
Account: IBKR_PED | Symbol: KEY-J | befday: +500, current: +300 (after KB fill)

Gap: 500-300 = 200 | Original fill tag: "MM_KB_LONG_DEC"
  strategy_prefix = "MM" | engine_prefix = "KB"
  DEC → RELOAD | POS TAG MM → threshold $0.13

REV: BUY 200 KEY-J | Tag: "REV_RL_MM_KB_BUY" | Threshold: $0.13
→ Sent directly to broker (NOT through frontlama)
```

### Scenario 7: Frontlama Front Cycle — Ratio Rejection

```
Account: HAMPRO | Order: AHL SELL 200 @ $34.75 | Tag: "LT_TRIM_LONG_DEC"
L1: Bid=34.68, Ask=34.82, Spread=0.14

Base price: 34.82 - (0.14 × 0.15) = $34.799
Truth tick: $34.73 (NYSE, 200 lot) → Front price: 34.73 - 0.01 = $34.72

Sacrifice: |34.799 - 34.72| = $0.079
Ratio: 0.079 / 0.14 = 56.4%

Tag → LT_LONG_DEC → limits: $0.35, 25%
  Cent: 0.079 ≤ 0.35 → ✅
  Ratio: 56.4% > 25% → ❌ REJECTED

→ Price stays at $34.75. Not fronted this cycle.
```

### Scenario 8: Position Closure Removes POS TAG

```
Account: HAMPRO | Symbol: TEF | Position: -125 (SHORT) | POS TAG: MM

KB BUY 125 TEF fills:
  engine = "KB" → DEC → POS TAG unchanged
  Position close check: TEF qty = 0
  → store.remove_tag("TEF", "HAMPRO")
  → POS TAG: REMOVED

Next time any engine opens TEF in HAMPRO:
  store.get_tag("TEF", "HAMPRO") → "MM" (default)
```

### Scenario 9: Befday Initialization

```
System startup, befday_tracker processes befham.csv:
  KEY-J +800 book=MM, AHL +600 book=LT, TEF -400 book=MM

  store.initialize_from_befday(positions, account_id="HAMPRO")
  → HAMPRO: {KEY-J: MM, AHL: LT, TEF: MM}

  store.initialize_from_befday(positions, account_id="IBKR_PED")
  → IBKR_PED: {KEY-J: MM, AHL: LT, TEF: MM}
```

### Scenario 10: High Exposure Blocks INC Fronting

```
Account: HAMPRO | Exposure: 93%
Open order: BUY 400 GARAN @ $18.35 | Tag: "LT_AN_LONG_INC"

Front cycle:
  Tag → LT_LONG_INC → INCREASE tag
  Exposure 93% ≥ 90% → INCREASE: FORBIDDEN
  → ❌ EXPOSURE_BLOCKS_INCREASE_93.0%
  → Order stays at $18.35 (not fronted, but still working)
```

### Scenario 11: FR_ Prefix Through Lifecycle

```
Order created: tag = "LT_KB_LONG_DEC"
Frontlama fronts: tag = "FR_LT_KB_LONG_DEC", price $34.75 → $34.72
Fill received: strip FR_ → "LT_KB_LONG_DEC" → engine = "KB"
  → KB is DEC → POS TAG unchanged
  → REV created: "REV_RL_LT_KB_BUY" 

→ FR_ prefix is cosmetic — only marks "this was fronted"
→ All parsers strip it before processing
```

### Scenario 12: MM Engine Opens New Position (No Prior POS TAG)

```
Account: HAMPRO | Symbol: NEW_STOCK | No existing position, no POS TAG

MM decides BUY 400 NEW_STOCK:
  Tag: "MM_MM_LONG_INC"
  Order fills

fill_tag_handler:
  engine = "MM" → MM is INC engine → set_tag("NEW_STOCK", "MM", "HAMPRO")
  POS TAG: (none) → MM

→ Next time KB/TRIM runs: store.get_tag("NEW_STOCK", "HAMPRO") → "MM"
→ Tags will be: "MM_KB_LONG_DEC" or "MM_TRIM_LONG_DEC"
```

### Scenario 13: LT Dominance — PA Overwrites MM

```
Account: HAMPRO | Symbol: ABC | Position: +400 (LONG) | POS TAG: MM

PATADD decides BUY 300 ABC (same direction as existing long):
  Tag: "LT_PA_LONG_INC" → fill happens

fill_tag_handler:
  engine = "PA" → PA always sets LT
  POS TAG: MM → LT (LT dominance rule!)

Now MM engine tries to operate on ABC:
  store.get_tag("ABC", "HAMPRO") → "LT"
  pos exists AND tag == "LT" → ❌ MM BLOCKED
  
→ PA converted the position from MM to LT permanently (until closed)
→ Only KB/TRIM can decrease it, only PA/AN can increase it
```

### Scenario 14: Dual Account Front Cycle Independence

```
DualProcessRunner alternates:
  Cycle 1: XNL starts for HAMPRO → pins _active_account_id = "HAMPRO"
    → All front cycles use HAMPRO tags
    → KB reads store.get_tag(sym, "HAMPRO")

  After 3.5 min: XNL stops for HAMPRO, starts for IBKR_PED
  Cycle 2: XNL starts for IBKR_PED → pins _active_account_id = "IBKR_PED"
    → All front cycles use IBKR_PED tags
    → KB reads store.get_tag(sym, "IBKR_PED")

→ No cross-account contamination! Account ID is PINNED at start().
```

---

## 16. File Reference

| File | Role |
|------|------|
| `app/psfalgo/position_tag_store.py` | POS TAG storage (Redis, per-account, MM/LT) |
| `app/psfalgo/fill_tag_handler.py` | Fill → POS TAG update bridge + engine extraction |
| `app/psfalgo/position_tags.py` | Legacy PositionTagManager (int/ov tracking) |
| `app/psfalgo/tag_utils.py` | Strategy tag resolution utility |
| `app/core/tag_generator.py` | Enhanced tag generator with stage/step info |
| `app/psfalgo/proposal_engine.py` | Order proposal with OZEL and POS TAG rules |
| `app/psfalgo/karbotu_engine_v2.py` | KB tag generation (dynamic POS TAG lookup) |
| `app/xnl/xnl_engine.py` | Engine orchestration, cycle timing, tag routing |
| `app/terminals/frontlama_engine.py` | Tag classification, 8-tag enums, sacrifice limits |
| `app/terminals/revnbookcheck.py` | REV tag generation (TP/RL, v4 format) |
| `app/trading/hammer_fills_listener.py` | HAMPRO fill → tag handler |
| `app/ibkr/ib_native_connector.py` | IBKR fill → tag handler |
| `app/psfalgo/befday_tracker.py` | Befday → POS TAG initialization |
| `app/xnl/dual_process_runner.py` | Account switching, active_account publish |

---

## 17. FAQ & Common Confusions

### Q: Can frontlama "reverse" or "flip" a position?

**NO.** Frontlama only adjusts the PRICE of an existing order. It never changes direction, quantity, or creates new orders. If a position appears "reversed," it's because the upstream engine issued a new order.

### Q: Why does MM_INCREASE have stricter limits than LT_INCREASE?

MM trades are short-term spread captures — every cent of entry price matters more. LT trades have longer time horizons, so $0.03 extra on entry is acceptable for better fill probability.

### Q: Can the same symbol have different POS TAGs in different accounts?

**YES.** This is by design. DCOMG can be MM in HAMPRO and LT in IBKR_PED. Each account has its own Redis key. This commonly happens when one account gets a PA fill but the other doesn't.

### Q: Do REV orders go through frontlama?

**NO.** REV orders are sent directly to the broker by `revorder_engine.py`. They have their own pricing logic (orderbook-first strategy) and are never evaluated by frontlama's sacrifice system.

### Q: What happens if POS TAG is missing?

It defaults to **"MM"**. This is the migration default for positions that existed before the tag system was implemented.

### Q: Can DEC engines (KB, TRIM) change POS TAG?

**NO.** Only INC engines (MM, PA, AN) affect POS TAG. This is by design — reducing a position shouldn't change what TYPE of position it is.

### Q: What does the FR_ prefix actually DO?

Nothing functional — it's a **marker**. `FR_LT_KB_LONG_DEC` is processed identically to `LT_KB_LONG_DEC` by all downstream systems. The prefix only indicates "this order's price was modified by frontlama." All parsers strip it before processing.

### Q: Why is MM_DECREASE the fastest cycle (30 sec)?

Because MM_DECREASE includes OZEL liquidation orders (forced MM closure before PA/AN can trade opposite direction) and Karbotu MM profit-taking. Both need to execute as fast as possible — OZEL because PA is waiting, and KB(MM) because MM profits are time-sensitive.

---

> **End of Document**
> 
> This README is the single source of truth for the POS & ORDER TAG system.  
> For architecture details, see the [Quant Engine Master Guide](../knowledge/quant_engine_master_guide/).  
> For the raw tag reference, see [POS_AND_ORDER_TAG_SYSTEM.md](./POS_AND_ORDER_TAG_SYSTEM.md).
