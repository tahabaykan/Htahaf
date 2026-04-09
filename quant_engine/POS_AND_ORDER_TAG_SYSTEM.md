# POS & ORDER TAG SYSTEM — Definitive Reference

> **Version**: Dual Tag v4 (Per-Account)  
> **Last Updated**: 2026-03-07  
> **Scope**: All trading engines, fill processing, frontlama, REV orders

---

## Table of Contents

1. [Overview](#overview)
2. [POS TAG (Position Tag)](#pos-tag)
3. [ORDER TAG (v4 Format)](#order-tag-v4-format)
4. [Engine → Tag Mapping](#engine--tag-mapping)
5. [Tag Lifecycle (Birth → Fill → REV)](#tag-lifecycle)
6. [Frontlama Tag Classification](#frontlama-tag-classification)
7. [Per-Account Isolation](#per-account-isolation)
8. [Cycle Timing & Routing](#cycle-timing--routing)
9. [REV Order Tags](#rev-order-tags)
10. [FR_ Prefix (Frontlama Modified)](#fr_-prefix)
11. [OZEL Liquidation Tags](#ozel-liquidation-tags)
12. [Rules & Constraints](#rules--constraints)
13. [Scenarios (50+ Examples)](#scenarios)
14. [File Reference](#file-reference)

---

## Overview

The Quant Engine uses a **Dual Tag v4** system with two independent tag dimensions:

```
┌────────────────────────────────────────────────────────────┐
│  POS TAG   =  What TYPE of position is this?  (MM or LT)  │
│  ORDER TAG =  Full order classification (4-part v4)        │
└────────────────────────────────────────────────────────────┘
```

**POS TAG** = Position-level tag stored in Redis per account per symbol.  
**ORDER TAG** = Order-level tag embedded in every order sent to broker.

Together, they determine:
- Which engines can operate on which positions
- Frontlama sacrifice limits (how aggressively an order can be fronted)
- REV order thresholds (take-profit vs reload dollar amounts)
- Cycle timing (how often orders are re-evaluated)

---

## POS TAG

### What Is It?

POS TAG answers: **"Is this position a Market-Making (MM) position or a Long-Term (LT) position?"**

| POS TAG | Meaning | Set By | Engines That Operate |
|:-------:|---------|--------|---------------------|
| **MM** | Market-Making position | MM engine fill | MM (increase), KB/TRIM (decrease) |
| **LT** | Long-Term position | PA/AN engine fill | PA/AN (increase), KB/TRIM (decrease) |

### Storage

```
Redis Key: psfalgo:pos_tags:{account_id}
Format:    JSON dict → {"AAPL": "MM", "GOOG": "LT", "TSLA": "MM"}

Examples:
  psfalgo:pos_tags:HAMPRO   → {"KEY-J": "MM", "AHL": "LT", "DCOMG": "MM"}
  psfalgo:pos_tags:IBKR_PED → {"KEY-J": "MM", "AHL": "LT", "DCOMG": "LT"}
```

> **CRITICAL**: Each account has its OWN POS TAG store. The same symbol CAN have
> different POS TAGs across accounts (e.g., DCOMG = MM in HAMPRO, LT in IBKR_PED).

### POS TAG Rules

```
RULE 1: "POS TAG follows the first engine that opens the position"
  - MM engine opens position → POS TAG = MM
  - PA/AN engine opens position → POS TAG = LT

RULE 2: "PA/AN always converts to LT (dominance rule)"
  - Existing MM position + PA fill same direction → POS TAG changes MM → LT
  - LT is dominant — once set, only position closure resets it

RULE 3: "MM never overwrites LT"
  - If POS TAG = LT and MM fill arrives → POS TAG stays LT
  - MM only sets tag when current tag is NOT LT

RULE 4: "DEC engines don't change POS TAG"
  - KB fill → POS TAG unchanged
  - TRIM fill → POS TAG unchanged  
  - Only INC engines (MM, PA, AN) affect POS TAG

RULE 5: "Position closure removes POS TAG"
  - qty → 0 → POS TAG deleted from Redis
  - Next position opening gets fresh POS TAG assignment
```

### Default Value

If a symbol has no POS TAG in Redis: **defaults to "MM"** (migration default for existing positions).

### Code Reference

```python
# app/psfalgo/position_tag_store.py
store = get_position_tag_store()
tag = store.get_tag("AAPL", "HAMPRO")     # → "MM" or "LT"
store.set_tag("AAPL", "LT", "HAMPRO")     # Set explicitly
store.update_on_fill("AAPL", "PA", "HAMPRO")  # PA fill → LT
store.remove_tag("AAPL", "HAMPRO")         # Position closed
```

---

## ORDER TAG (v4 Format)

### Format

```
{POS}_{ENGINE}_{DIRECTION}_{ACTION}

POS       = MM | LT           (from POS TAG)
ENGINE    = MM | PA | AN | KB | TRIM
DIRECTION = LONG | SHORT
ACTION    = INC | DEC
```

### All Possible v4 Tags

#### INCREASE Tags (New Risk / Position Growth)

| Tag | Engine | Direction | Meaning |
|-----|--------|-----------|---------|
| `MM_MM_LONG_INC` | MM | Long | MM engine buys new long position |
| `MM_MM_SHORT_INC` | MM | Short | MM engine sells new short position |
| `LT_PA_LONG_INC` | PATADD | Long | PATADD adds to long position |
| `LT_PA_SHORT_INC` | PATADD | Short | PATADD adds to short position |
| `LT_AN_LONG_INC` | ADDNEWPOS | Long | ADDNEWPOS opens new long |
| `LT_AN_SHORT_INC` | ADDNEWPOS | Short | ADDNEWPOS opens new short |

#### DECREASE Tags (Risk Reduction / Profit Taking)

| Tag | Engine | Direction | Meaning |
|-----|--------|-----------|---------|
| `MM_KB_LONG_DEC` | Karbotu | Long | KB sells MM long position |
| `MM_KB_SHORT_DEC` | Karbotu | Short | KB covers MM short position |
| `LT_KB_LONG_DEC` | Karbotu | Long | KB sells LT long position |
| `LT_KB_SHORT_DEC` | Karbotu | Short | KB covers LT short position |
| `MM_TRIM_LONG_DEC` | LT_TRIM | Long | TRIM sells MM long position |
| `MM_TRIM_SHORT_DEC` | LT_TRIM | Short | TRIM covers MM short position |
| `LT_TRIM_LONG_DEC` | LT_TRIM | Long | TRIM sells LT long position |
| `LT_TRIM_SHORT_DEC` | LT_TRIM | Short | TRIM covers LT short position |

### Why 4 Parts?

The 4-part format ensures:
1. **POS TAG** is embedded → frontlama knows MM vs LT sacrifice limits
2. **ENGINE** is preserved → REV orders know which engine originated the fill
3. **DIRECTION** is explicit → no ambiguity about LONG vs SHORT
4. **ACTION** is explicit → INC vs DEC determines cycle routing

---

## Engine → Tag Mapping

### MM Engine (Greatest MM)

```
Always produces: MM_MM_{LONG|SHORT}_INC
POS TAG: Always MM (hardcoded)
ENGINE: Always MM

Example:
  MM decides BUY AAPL → tag = "MM_MM_LONG_INC"
  MM decides SELL TSLA → tag = "MM_MM_SHORT_INC"
```

**Code**: `xnl_engine.py` lines ~1450-1560

### PATADD Engine

```
Always produces: LT_PA_{LONG|SHORT}_INC
POS TAG: Always LT (hardcoded — PA always results in LT)
ENGINE: Always PA

Example:
  PA decides BUY GOOG → tag = "LT_PA_LONG_INC"
  PA decides SELL MSFT → tag = "LT_PA_SHORT_INC"
```

**Why always LT?** PATADD is a long-term engine. When PA fills, the POS TAG
transitions to LT. So the tag should reflect the RESULT, not the current state.

**Code**: `xnl_engine.py` lines ~1289-1306

### ADDNEWPOS Engine

```
Always produces: LT_AN_{LONG|SHORT}_INC
POS TAG: Always LT (hardcoded — same logic as PATADD)
ENGINE: Always AN

Example:
  AN decides BUY XOM → tag = "LT_AN_LONG_INC"
  AN decides SELL CVX → tag = "LT_AN_SHORT_INC"
```

**Code**: `xnl_engine.py` lines ~1160-1170

### KARBOTU Engine

```
Produces: {POS}_KB_{LONG|SHORT}_DEC
POS TAG: Dynamic — fetched from PositionTagStore(account_id)
ENGINE: Always KB

Example (HAMPRO, DCOMG is MM):
  KB decides SELL DCOMG → store.get_tag("DCOMG", "HAMPRO") → "MM"
  → tag = "MM_KB_LONG_DEC"

Example (IBKR_PED, DCOMG is LT):
  KB decides SELL DCOMG → store.get_tag("DCOMG", "IBKR_PED") → "LT"
  → tag = "LT_KB_LONG_DEC"
```

> **CRITICAL**: Karbotu reads POS TAG dynamically from Redis.
> Same symbol CAN produce different tags in different accounts!

**Code**: `karbotu_engine_v2.py` lines ~295-310 (LONG), ~485-500 (SHORT)

### LT_TRIM Engine

```
Produces: {POS}_TRIM_{LONG|SHORT}_DEC
POS TAG: Dynamic — fetched from PositionTagStore(account_id)
ENGINE: Always TRIM

Example:
  TRIM decides SELL BKW → store.get_tag("BKW", "HAMPRO") → "LT"
  → tag = "LT_TRIM_LONG_DEC"
```

**Code**: `xnl_engine.py` lines ~862-870

---

## Tag Lifecycle

### Phase 1: Order Generation

```
Engine runs → produces order with v4 tag
Example: KARBOTU → {symbol: "AHL", action: "SELL", qty: 200, tag: "LT_KB_LONG_DEC"}
```

### Phase 2: Frontlama (optional)

```
Front cycle evaluates order → if fronting approved:
  tag gains "FR_" prefix → "FR_LT_KB_LONG_DEC"
  price adjusted closer to truth tick
```

### Phase 3: Broker Send

```
Order sent to broker (Hammer Pro or IBKR) with tag as orderRef.
Broker sees: FR_LT_KB_LONG_DEC (or LT_KB_LONG_DEC if not fronted)
```

### Phase 4: Fill Processing

```
Fill received → fill_tag_handler processes:

1. Extract engine from tag:
   "FR_LT_KB_LONG_DEC" → strip FR_ → "LT_KB_LONG_DEC" → engine = "KB"

2. Update POS TAG:
   KB is DEC engine → POS TAG unchanged
   (PA/AN would set LT, MM would set MM if not already LT)

3. Update PositionTagManager (legacy int/ov tracking)

4. Check if position closed (qty=0) → remove POS TAG
```

### Phase 5: REV Order (optional)

```
RevnBookCheck detects gap between befday and current qty:
  befday=600, current=400 → gap=200 → REV BUY 200

REV tag constructed from original fill:
  Original fill tag: "LT_KB_LONG_DEC"
  → strategy_prefix = "LT", engine_prefix = "KB"
  → full_tag = "LT_KB_LONG_DEC" (v4 format preserved)

REV type determined by INC/DEC:
  DEC fill → RELOAD REV (refill position)
  INC fill → TAKE PROFIT REV (capture profit on new addition)

REV thresholds based on POS TAG:
  MM + TAKE PROFIT → $0.05
  LT + TAKE PROFIT → $0.09
  MM + RELOAD     → $0.13
  LT + RELOAD     → $0.08
```

---

## Frontlama Tag Classification

Frontlama maps v4 order tags to 8 OrderTag enums to determine sacrifice limits:

### Step 1: Direct Substring Match

```python
if 'MM_LONG_INC' in tag:  return OrderTag.MM_LONG_INC   # Catches MM_MM_LONG_INC
if 'LT_LONG_INC' in tag:  return OrderTag.LT_LONG_INC   # Catches raw LT_LONG_INC
if 'MM_LONG_DEC' in tag:  return OrderTag.MM_LONG_DEC   # Catches MM_MM_LONG_DEC
# ... etc for all 8 tags
```

### Step 2: Legacy Parser (engine-prefixed tags)

When Step 1 fails (most v4 tags with engine prefix like KB, PA, TRIM):

```python
is_lt  = 'LT' in tag or 'TRIM' in tag
is_mm  = 'MM' in tag
is_inc = 'INC' in tag
is_dec = 'DEC' in tag
is_long = 'LONG' in tag
is_short = 'SHORT' in tag
# → Maps to correct 8-tag enum
```

### Complete Mapping Table

| v4 Tag | OrderTag Enum | Sacrifice |
|--------|---------------|-----------|
| `MM_MM_LONG_INC` | MM_LONG_INC | $0.07, 7% |
| `MM_MM_SHORT_INC` | MM_SHORT_INC | $0.07, 7% |
| `LT_PA_LONG_INC` | LT_LONG_INC | $0.10, 10% |
| `LT_PA_SHORT_INC` | LT_SHORT_INC | $0.10, 10% |
| `LT_AN_LONG_INC` | LT_LONG_INC | $0.10, 10% |
| `LT_AN_SHORT_INC` | LT_SHORT_INC | $0.10, 10% |
| `MM_KB_LONG_DEC` | MM_LONG_DEC | $0.60, 50% |
| `MM_KB_SHORT_DEC` | MM_SHORT_DEC | $0.60, 50% |
| `LT_KB_LONG_DEC` | LT_LONG_DEC | $0.35, 25% |
| `LT_KB_SHORT_DEC` | LT_SHORT_DEC | $0.35, 25% |
| `LT_TRIM_LONG_DEC` | LT_LONG_DEC | $0.35, 25% |
| `MM_TRIM_SHORT_DEC` | MM_SHORT_DEC | $0.60, 50% |
| `OZEL_MM_MM_LONG_DEC` | MM_LONG_DEC | $0.60, 50% |
| `FR_LT_KB_LONG_DEC` | LT_LONG_DEC | $0.35, 25% |

---

## Per-Account Isolation

### The Problem (Pre-v4)

Before the per-account fix, PositionTagStore used a SINGLE Redis key:
```
psfalgo:pos_tags → {"DCOMG": "MM", "BKW": "LT"}  // SHARED!
```

If HAMPRO got a PA fill on DCOMG → tag changed to LT → IBKR_PED would
incorrectly see DCOMG as LT even though it was still MM there.

### The Solution (v4)

Each account now has its own Redis key:
```
psfalgo:pos_tags:HAMPRO   → {"DCOMG": "MM", "BKW": "LT"}
psfalgo:pos_tags:IBKR_PED → {"DCOMG": "LT", "BKW": "MM"}
```

### How account_id Flows Through the System

```
DualProcessRunner
  ├── Sets active account in Redis
  │     psfalgo:xnl:running_account = "HAMPRO"
  │
  ├── XNL Engine start(account_id="HAMPRO")
  │     └── _active_account_id = "HAMPRO"
  │
  ├── Engine Order Generation
  │     ├── _run_karbotu(account_id) → KB reads store.get_tag(sym, account_id)
  │     ├── _run_lt_trim(account_id) → TRIM reads store.get_tag(sym, account_id)
  │     ├── _run_patadd(account_id) → Always LT (hardcoded)
  │     ├── _run_addnewpos(account_id) → Always LT (hardcoded)
  │     └── _run_mm(account_id) → checks store.get_tag for LT block
  │
  ├── Fill Processing
  │     ├── Hammer fill → account_id="HAMPRO" (hardcoded in listener)
  │     └── IBKR fill → account_id="IBKR_PED" (hardcoded in connector)
  │     └── fill_tag_handler → store.update_on_fill(sym, engine, account_id)
  │
  └── RevnBookCheck
        └── store.get_tag(sym) → auto-resolves via Redis active_account
```

### Fallback Resolution

When `account_id` is not explicitly provided (e.g., revnbookcheck):

```python
def _resolve_account(self, account_id=None):
    if account_id in KNOWN_ACCOUNTS:
        return account_id
    
    # Priority 1: psfalgo:xnl:running_account (set by DualProcessRunner)
    # Priority 2: psfalgo:trading:account_mode (set by TradingAccountContext)
    # Fallback:   "HAMPRO" (primary account)
```

---

## Cycle Timing & Routing

### How Orders Are Routed to Cycles

XNL Engine uses **substring matching** on the order tag to classify:

```python
if category == LT_INCREASE:
    matches = ('LT' in tag or 'PAT' in tag) and 'INC' in tag

if category == LT_DECREASE:
    matches = ('LT' in tag or 'KARBOTU' in tag or 'HEAVY' in tag) and 'DEC' in tag

if category == MM_INCREASE:
    matches = 'MM' in tag and 'INC' in tag

if category == MM_DECREASE:
    matches = 'MM' in tag and 'DEC' in tag
```

### Routing Examples

| Order Tag | LT_INC? | LT_DEC? | MM_INC? | MM_DEC? | Result |
|-----------|:-------:|:-------:|:-------:|:-------:|--------|
| `LT_PA_LONG_INC` | ✅ | | | | LT_INCREASE |
| `LT_AN_SHORT_INC` | ✅ | | | | LT_INCREASE |
| `LT_KB_LONG_DEC` | | ✅ | | | LT_DECREASE |
| `LT_TRIM_LONG_DEC` | | ✅ | | | LT_DECREASE |
| `MM_KB_LONG_DEC` | | | | ✅ | MM_DECREASE |
| `MM_TRIM_SHORT_DEC` | | | | ✅ | MM_DECREASE |
| `MM_MM_LONG_INC` | | | ✅ | | MM_INCREASE |
| `MM_MM_SHORT_INC` | | | ✅ | | MM_INCREASE |
| `OZEL_MM_MM_LONG_DEC` | | | | ✅ | MM_DECREASE |
| `FR_LT_PA_LONG_INC` | ✅ | | | | LT_INCREASE |

### Timing Table

| Category | Front Cycle | Refresh Cycle | Description |
|----------|:-----------:|:-------------:|------------|
| LT_INCREASE | 3.5 min | 8 min | Most conservative — new LT risk |
| LT_DECREASE | 2 min | 5 min | Aggressive — reduce LT position |
| MM_INCREASE | 2 min | 3 min | Controlled — new MM risk |
| MM_DECREASE | 30 sec | 1 min | Most aggressive — lock in MM profit |

---

## REV Order Tags

REV (Reversal) orders are generated by `revnbookcheck.py` to reconcile
the difference between befday (expected) and current (actual) position quantities.

### REV Tag Format

```
REV_{TYPE}_{POS}_{ENGINE}_{ACTION}

TYPE   = TP (Take Profit) | RL (Reload)
POS    = MM | LT
ENGINE = MM | PA | AN | KB | TRIM
ACTION = BUY | SELL
```

### REV Type Determination

```
Original fill was INC (increase) → REV is TAKE PROFIT
  "Position grew → reversed → take the profit"
  
Original fill was DEC (decrease) → REV is RELOAD
  "Position shrank → reversed → reload back to original size"
```

### REV Threshold Table

| POS TAG | REV Type | Threshold | Meaning |
|:-------:|----------|:---------:|---------|
| MM | Take Profit | $0.05 | MM position profit — tight target |
| LT | Take Profit | $0.09 | LT position profit — wider target |
| MM | Reload | $0.13 | MM reload — generous to refill |
| LT | Reload | $0.08 | LT reload — moderate refill |

### REV Examples

```
Scenario 1: KB sold 200 shares of MM long position
  Fill tag: MM_KB_LONG_DEC → DEC → RELOAD type
  POS TAG: MM → threshold = $0.13
  REV tag: REV_RL_MM_KB_BUY
  
Scenario 2: PA bought 400 shares (new LT long)
  Fill tag: LT_PA_LONG_INC → INC → TAKE PROFIT type
  POS TAG: LT → threshold = $0.09
  REV tag: REV_TP_LT_PA_SELL

Scenario 3: MM opened new short position
  Fill tag: MM_MM_SHORT_INC → INC → TAKE PROFIT type
  POS TAG: MM → threshold = $0.05
  REV tag: REV_TP_MM_MM_BUY
```

### Important: REV Orders Do NOT Go Through Frontlama

REV orders are sent directly to the broker by `revorder_engine.py`.
They are never evaluated by the frontlama engine.

---

## FR_ Prefix

When frontlama modifies an order's price, the tag gets an `FR_` prefix:

```
Original: LT_KB_LONG_DEC
After front: FR_LT_KB_LONG_DEC
```

### Rules

1. **Added exactly once**: `if not tag.startswith('FR_'): tag = f"FR_{tag}"`
2. **Never doubled**: `FR_FR_` is impossible
3. **Does not affect tag classification**: parsers extract MM/LT/INC/DEC correctly
4. **Preserved through fill processing**: `_extract_engine_tag` strips `FR_` first

---

## OZEL Liquidation Tags

When PA/AN wants to trade in the OPPOSITE direction of an existing MM position,
the MM position must be liquidated first.

```
Scenario: MM long +500, PA wants SHORT
  → OZEL liquidation order: SELL 500 @ aggressive price
  → Tag: OZEL_MM_MM_LONG_DEC

Scenario: MM short -300, AN wants LONG  
  → OZEL liquidation order: BUY 300 @ aggressive price
  → Tag: OZEL_MM_MM_SHORT_DEC
```

### OZEL Tag Properties

- Routes to **MM_DECREASE** cycle (30-second front cycle — fastest!)
- Gets **MM_LONG_DEC** sacrifice limits ($0.60, 50% — most aggressive!)
- Ensures liquidation happens quickly so PA/AN can trade next cycle

---

## Rules & Constraints

### Engine Priority (Highest → Lowest)

```
1. LT_TRIM     (immediate risk reduction)
2. KARBOTU     (step-based profit taking)
3. PATADD      (long-term additions)
4. ADDNEWPOS   (new long-term positions)
5. MM          (market-making — lowest priority)
```

### Direction Conflict Resolution

```
Same symbol, same direction:
  → LOT COORDINATION: second engine gets remaining lot only

Same symbol, opposite direction:
  → MM loses to ANY non-MM engine (always)
  → Non-MM vs Non-MM: price gap ≥ $0.08 → both kept; < $0.08 → first wins
```

### MM Engine LT Position Block

```
MM engine CANNOT operate on LT positions.
If store.get_tag(symbol, account_id) == "LT" AND position exists:
  → MM order BLOCKED for this symbol
  → Only KB/TRIM can decrease LT positions
  → Only PA/AN can increase LT positions
```

### Lot Rules

```
DECREASE (KB, TRIM):
  Minimum: 125 lots
  Rounding: floor to 100
  400-lot rule: if remaining < 400 after sell → sell entire position

INCREASE (PA, AN):
  Minimum: 200 lots
  Rounding: round to 100

MM:
  Minimum: 200 lots
  Dynamic: based on free exposure and AVG_ADV
```

### MinMax Area Validation

Every order is validated against daily min/max trading limits per symbol.
If order would exceed max → lot is trimmed or order is blocked.

---

## Scenarios

### Scenario 1: Normal Karbotu Sell (MM Position)

```
Account: HAMPRO
Symbol: KEY-J, Position: +800 (LONG)
POS TAG: store.get_tag("KEY-J", "HAMPRO") → "MM"

Engine: Karbotu Step 3 (40%)
  Raw lot: 800 × 0.40 = 320
  Rounded: floor(320/100) × 100 = 300
  Check: 300 ≥ 125 → ✅
  Remaining: 800 - 300 = 500 ≥ 400 → no 400-lot rule

Order: SELL 300 KEY-J
Tag: "MM_KB_LONG_DEC"
Cycle: MM_DECREASE (30-sec front cycle)
Sacrifice: $0.60 max, 50% ratio max
```

### Scenario 2: Same Symbol, Different Accounts

```
HAMPRO:   DCOMG POS TAG = MM
IBKR_PED: DCOMG POS TAG = LT

Karbotu runs for HAMPRO:
  store.get_tag("DCOMG", "HAMPRO") → "MM"
  Tag: "MM_KB_LONG_DEC" → MM_DECREASE cycle (30 sec)

Karbotu runs for IBKR_PED:
  store.get_tag("DCOMG", "IBKR_PED") → "LT"
  Tag: "LT_KB_LONG_DEC" → LT_DECREASE cycle (2 min)

→ Same symbol, same engine, DIFFERENT tags and DIFFERENT cycles!
→ Per-account isolation working correctly.
```

### Scenario 3: PA Fill Changes POS TAG

```
Account: HAMPRO
Symbol: KEY-J, Position: +800 (LONG), POS TAG: MM

PATADD generates: BUY 400 KEY-J, tag: "LT_PA_LONG_INC"
Order fills on broker.

fill_tag_handler receives fill:
  account_id = "HAMPRO"
  tag = "LT_PA_LONG_INC" → engine = "PA"
  store.update_on_fill("KEY-J", "PA", "HAMPRO")
  → PA is INC engine → set_tag("KEY-J", "LT", "HAMPRO")

POS TAG: HAMPRO/KEY-J: MM → LT
IBKR_PED/KEY-J: still MM (not affected!)

Next Karbotu cycle for HAMPRO:
  store.get_tag("KEY-J", "HAMPRO") → "LT"
  Tag: "LT_KB_LONG_DEC" (was MM_KB before PA fill!)
```

### Scenario 4: MM Blocked on LT Position

```
Account: IBKR_PED
Symbol: AHL, Position: +600 (LONG), POS TAG: LT

Greatest MM also wants to BUY AHL (good MM score).

xnl_engine._run_mm:
  store.get_tag("AHL", "IBKR_PED") → "LT"
  pos exists AND pos.qty > 0 AND tag == "LT"
  → ❌ BLOCKED: "MM cannot operate on LT positions"

Result: MM skips AHL, picks next-best symbol.
```

### Scenario 5: OZEL Liquidation

```
Account: HAMPRO
Symbol: SRE, Position: -500 (SHORT), POS TAG: MM

PATADD wants to BUY SRE (LONG direction = opposite to current SHORT).

proposal_engine.RULE 3:
  PA wants LONG, position is SHORT → OPPOSITE DIRECTION
  → Generate OZEL liquidation order

OZEL order:
  Action: BUY 500 (close the short)
  Price: bid + spread × 0.15
  Tag: "OZEL_MM_MM_SHORT_DEC"
  
Cycle: MM_DECREASE (30-sec front, $0.60/50% sacrifice)
  → Aggressive liquidation! PA's order comes next cycle after fill.
```

### Scenario 6: REV After KB Fill

```
Account: IBKR_PED
Symbol: KEY-J, befday: +500, current after KB fill: +300
Gap: 500 - 300 = 200

Original fill tag: "MM_KB_LONG_DEC"
  strategy_prefix = "MM" (parts[0])
  engine_prefix = "KB" (parts[1])

REV type: DEC → RELOAD
POS TAG: "MM" → threshold = $0.13

REV order:
  Action: BUY 200 KEY-J
  Tag: "REV_RL_MM_KB_BUY"
  Threshold: $0.13 from last fill price

REV sent directly to broker (NOT through frontlama).
```

### Scenario 7: Frontlama Front Cycle

```
Account: HAMPRO
Open order: AHL SELL 200 @ $34.75, tag: "LT_TRIM_LONG_DEC"
Cycle: LT_DECREASE (2 min front cycle)

After 2 minutes, front cycle runs:
  L1: Bid=34.68, Ask=34.82, Spread=0.14
  Base price: 34.82 - (0.14 × 0.15) = $34.799
  
  Truth tick: $34.73 (NYSE, 200 lot, valid)
  Front price: 34.73 - 0.01 = $34.72

  Sacrifice: |34.799 - 34.72| = $0.079
  Ratio: 0.079 / 0.14 = 56.4%
  
  Tag → OrderTag.LT_LONG_DEC → limits: $0.35, 25%
  Cent: 0.079 ≤ 0.35 → ✅
  Ratio: 56.4% > 25% → ❌ REJECTED

  → Price stays at $34.75. Not fronted.
```

### Scenario 8: Position Closed, POS TAG Removed

```
Account: HAMPRO
Symbol: TEF, Position: -125 (SHORT), POS TAG: MM

Karbotu BUY 125 TEF fills:
  fill_tag_handler:
    account_id = "HAMPRO"
    engine = "KB" → DEC → POS TAG unchanged
    
    Position close check:
    psfalgo:positions:HAMPRO → TEF qty = 0
    → handle_position_closed("TEF", "HAMPRO")
    → store.remove_tag("TEF", "HAMPRO")

POS TAG: HAMPRO/TEF: REMOVED

Next time MM or PA opens TEF in HAMPRO:
  store.get_tag("TEF", "HAMPRO") → "MM" (default)
```

### Scenario 9: Befday Initialization

```
System startup. befday_tracker processes befham.csv:

Position: KEY-J +800, book=MM
Position: AHL +600, book=LT
Position: TEF -400, book=MM

befday_tracker:
  store.initialize_from_befday(positions, account_id="HAMPRO")
  → Sets: HAMPRO/KEY-J=MM, HAMPRO/AHL=LT, HAMPRO/TEF=MM

  store.initialize_from_befday(positions, account_id="IBKR_PED")
  → Sets: IBKR_PED/KEY-J=MM, IBKR_PED/AHL=LT, IBKR_PED/TEF=MM

Both accounts initialized independently from their own befday CSVs.
```

### Scenario 10: Exposure Blocks Frontlama INC

```
Account: HAMPRO, Exposure: 93%
Open order: GARAN BUY 400 @ $18.35, tag: "LT_AN_LONG_INC"

Front cycle runs:
  Tag → OrderTag.LT_LONG_INC → INCREASE tag
  Exposure 93% → 90-95% bracket
  → INCREASE: FORBIDDEN
  
  → ❌ EXPOSURE_BLOCKS_INCREASE_93.0%
  → BUY order NOT fronted (stays at conservative price)
  
But if exposure drops to 65%:
  → Ratio limit: base 10% + 0% = 10% (no adjustment)
  → Fronting allowed within normal limits
```

---

## File Reference

| File | Role |
|------|------|
| `app/psfalgo/position_tag_store.py` | POS TAG storage (Redis, per-account) |
| `app/psfalgo/fill_tag_handler.py` | Fill → POS TAG update bridge |
| `app/psfalgo/proposal_engine.py` | Order proposal with POS TAG rules |
| `app/psfalgo/karbotu_engine_v2.py` | KB tag generation (dynamic POS TAG) |
| `app/xnl/xnl_engine.py` | All engine orchestration, MM/TRIM/PA/AN tags |
| `app/terminals/frontlama_engine.py` | Tag classification, sacrifice limits |
| `app/terminals/revnbookcheck.py` | REV tag generation (v4 format) |
| `app/trading/hammer_fills_listener.py` | HAMPRO fill → tag handler |
| `app/ibkr/ib_native_connector.py` | IBKR fill → tag handler |
| `app/psfalgo/befday_tracker.py` | Befday → POS TAG initialization |
| `app/xnl/dual_process_runner.py` | Account switching, active_account publish |
