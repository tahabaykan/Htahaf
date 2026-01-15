# HARD_DERISK Exit Preference Engine: Deterministic Ranking

This document outlines the STRICT, deterministic logic for ranking and selecting stock positions for reduction during `HARD_DERISK` and `CLOSE` regimes.

## Core Philosophy

"Profit priority remains first-class at all times. Near close, the engine must act immediately (no waiting), selecting the least-damaging exits deterministically rather than panicking to flatten."

1.  **Profit First**: Always prefer realizing gains over taking losses.
2.  **Least Damage**: If losses are necessary, take the smallest ones first.
3.  **Immediate Action**: In `HARD_DERISK` or `CLOSE`, we do not wait for price improvement. We take the best available action NOW.
4.  **No Residuals**: Low confidence does **NOT** block full exits. It only limits *new* entry sizing.

## Ranking Logic (Deterministic / Lexicographic)

Positions are sorted based on a strict tuple comparison. Weighted sums are NOT used.

### A. Bucket Priority (MM vs LT)
**Default Policy**: Reduce Market Maker (MM) inventory first.
**Exception**: If `Cost_MM > 1.8 * Cost_LT` (for the required reduction notional), switch to LT.

### B. MM Candidate Ranking
Sort MM positions by the following keys (applied in order):

1.  **Profitability**:
    *   **Tier 1**: Profitable positions (Ranked by Profit Amount Descending).
    *   **Tier 2**: Losing positions (Ranked by Loss Amount Ascending - smallest loss first).
2.  **Execution Proximity**:
    *   Closer to executable side (Bid for Longs, Ask for Shorts) is better.
3.  **Truth Context**:
    *   Closer to recent Truth Ticks is better (validates price reality).
    *   **Note**: Truth context is used only as a validation/tie-break signal and must never override Profit/Loss ordering.
4.  **Spread**:
    *   Narrow spread preferred. (Hold wide spreads if possible).
5.  **Liquidity**:
    *   Illiquid preferred (Tie-breaker: take the "gift" of an exit).

### C. LT Candidate Ranking (If used)
Sort LT positions by:
1.  **PnL**: Best Profit / Smallest Loss first.
2.  **Execution Proximity**: Closer is better.
3.  **Spread**: Narrow first.
4.  **Liquidity**: Illiquid first.

## Action Planner

### 1. Selection
1.  Separate positions into MM and LT buckets.
2.  Sort each bucket using the rules above.
3.  Select top MM candidate.
4.  Calculate Slippage Cost for target reduction size:
    *   $$Cost_{MM} = Qty \times |ExecPrice_{MM} - TruthPrice|$$
    *   $$Cost_{LT} = Qty \times |ExecPrice_{LT} - TruthPrice|$$
5.  **Compare**:
    *   If $$Cost_{MM} > 1.8 \times Cost_{LT}$$: Select LT candidate instead.
    *   else: Select MM candidate.

### 3. Truth Price Fallback
For cost calculations, `TruthPrice` is determined by:
1.  **Dominant Price (GRPAN1)**: If available.
2.  **Last Price**: Fallback.
3.  **Mid Price**: Final backup.

### 4. Sizing & Constraints
- **LiquidityGuard**:
    - Min trade size: 200 lots.
    - Max MM trade size: ~2000 lots per clip.
- **Low Confidence**:
    - Does **NOT** prevent full flattening.
    - **Rule**: If confidence is low (< 25), new MM *churn* orders must use minimum size (200). Exit orders are effectively uncapped.

## Time Regimes

- **LATE (<= 15m to close)**:
    - Activate Hard Exit logic.
    - Determine Price: Use `TruthPrice` if valid/reachable, else `BestBid/Ask`.
- **CLOSE (<= 2m to close)**:
    - "Time-critical" but "Rational" sorting.
    - Use **Marketable Limits** (hit bid/ask).
    - **Goal**: Reduce exposure immediately, but strictly following the Profit > Loss > Reality ranking. **DO NOT** break strict ordering.
