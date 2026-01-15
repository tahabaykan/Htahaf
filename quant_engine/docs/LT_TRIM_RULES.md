# LT Trim Rules - Mean-Reversion Reduction Logic

Tactical LT-side trim logic for preferred stocks with multi-step reductions.

## Engine Behavior

| Regime       | LT_TRIM Status   |
|--------------|------------------|
| NORMAL       | ✅ Active        |
| SOFT_DERISK  | ✅ Active        |
| HARD_DERISK  | ❌ Suppressed    |
| CLOSE        | ❌ Suppressed    |

## Sizing

| Position Size | Behavior |
|---------------|----------|
| < 200 lot     | Trim exact quantity (55 → 55) |
| >= 200 lot    | 20% step, rounded to 100s, min 200 |

**Step Sizing:** Each step is 20% of **CURRENT REMAINING** position, not day-start.

**Daily Cap:** Max 80% of max observed daily size.

## LONG Spread-Score Table (Ask Sell Pahalılık)

| Spread (cents) | Min Pahalılık |
|----------------|---------------|
| 0.01 - 0.06    | >= 0.08       |
| 0.06 - 0.10    | >= 0.05       |
| 0.10 - 0.15    | >= 0.02       |
| 0.15 - 0.25    | >= -0.02      |
| 0.25 - 0.45    | >= -0.05      |
| >= 0.45        | >= -0.08      |

## SHORT Spread-Score Table (Bid Buy Ucuzluk)

| Spread (cents) | Max Ucuzluk |
|----------------|-------------|
| 0.01 - 0.06    | <= -0.08    |
| 0.06 - 0.10    | <= -0.05    |
| 0.10 - 0.15    | <= -0.02    |
| 0.15 - 0.25    | <= 0.02     |
| 0.25 - 0.45    | <= 0.05     |
| >= 0.45        | <= 0.08     |

## Ladder Pricing

**When ladder level found:**
- LONG trim: `level_price - 0.01` (1 tick in front)
- SHORT trim: `level_price + 0.01` (1 tick in front)

**Fallback (no ladder):**
- LONG: `ask - (spread × 0.15)`
- SHORT: `bid + (spread × 0.15)`

## Ladder Targets

| Target | Step Size |
|--------|-----------|
| 0.10c  | 20% of remaining |
| 0.20c  | 20% of remaining |
| 0.40c  | 20% of remaining |

## Aggressive Illiquid Trim

**SPREAD-DOMINANT trigger (60% immediate):**

| Side  | Condition |
|-------|-----------|
| LONG  | `spread >= 0.25` AND `ask_sell_expensive_score >= +0.25` |
| SHORT | `spread >= 0.25` AND `bid_buy_cheap_score < 0` AND `<= -0.25` |

**Note:** SHORT aggressive trim only triggers if score is **unambiguously negative** (cheap).
