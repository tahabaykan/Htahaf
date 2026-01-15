# LT Band Drift Controller

## Overview

The LT Band Drift Controller monitors LT long/short gross band ranges and generates gentle corrective intents when bands are violated. It operates with tolerance (bands can be violated for 1-2 days) and never forces aggressive actions.

## Configuration

In `risk_rules.yaml`:

```yaml
buckets:
  LT:
    band_drift:
      long_pct_range: [60.0, 70.0]  # LT long should be 60-70% of LT bucket
      short_pct_range: [30.0, 40.0]  # LT short should be 30-40% of LT bucket
      tolerance_days: 2  # Band can be violated for up to 2 days
      corrective_intent_size_pct: 0.02  # 2% of position for gentle correction
      use_limit_orders: true  # Use limit orders near truth tick
      prefer_positive_pnl: true  # Prefer actions with positive/acceptable PnL
```

## How It Works

### 1. Band Monitoring

The Decision Engine checks LT band drift in NORMAL mode:
- Calculates LT long/short percentages (as % of equity)
- Compares against configured band ranges
- If violated, generates corrective action

### 2. Corrective Action Selection

Based on which band is violated:

**LT Short Too High** (> 40%):
- Prefer: `LT_SHORT_DECREASE` (close short positions)
- Or: `LT_LONG_INCREASE` (add long positions)

**LT Short Too Low** (< 30%):
- Prefer: `LT_SHORT_INCREASE` (open short positions)
- Or: `LT_LONG_DECREASE` (reduce long positions)

**LT Long Too High** (> 70%):
- Prefer: `LT_LONG_DECREASE` (close long positions)
- Or: `LT_SHORT_INCREASE` (open short positions)

**LT Long Too Low** (< 60%):
- Prefer: `LT_LONG_INCREASE` (add long positions)
- Or: `LT_SHORT_DECREASE` (close short positions)

### 3. Gentle Correction

Corrective intents are:
- **Low Priority**: Priority = 1 (vs 5-10 for derisk)
- **Small Size**: 2% of position (configurable)
- **Limit Orders**: Near truth tick (± $0.01, stub)
- **PnL-Aware**: Prefers positions with positive/acceptable PnL
- **Hard Cap Safe**: Never violates global 130% hard cap

### 4. Position Selection

The controller selects positions for correction based on:
1. **Bucket Match**: Only LT positions
2. **Size Preference**: Smaller positions preferred (gentle)
3. **PnL Preference**: Positive PnL positions preferred (if enabled)
4. **Classification Match**: Prefers positions matching preferred classifications

## Example Flow

1. **Current State**:
   - LT long: 75% (above max 70%)
   - LT short: 25% (below min 30%)
   - Gross exposure: 110%

2. **Detection**:
   - LT long too high → prefer `LT_LONG_DECREASE` or `LT_SHORT_INCREASE`

3. **Action**:
   - Selects largest LT long position (e.g., AAPL, 100 shares @ $150)
   - Calculates gentle quantity: 2% = 2 shares
   - Generates intent: `LT_LONG_DECREASE`, SELL 2 AAPL @ $149.99 (limit)

4. **Execution**:
   - Intent flows to Execution Service
   - Order placed with classification preserved
   - Fill recorded in Daily Ledger

## Tolerance

- Bands can be violated for up to `tolerance_days` (default: 2 days)
- No aggressive actions during tolerance period
- Corrective intents are gentle and low-priority
- System continues normal operation

## Hard Cap Protection

Corrective intents **never** violate the global 130% hard cap:
- Before generating intent, checks if action would exceed cap
- If risk-increasing and would exceed cap, skips correction
- Logs warning if correction skipped due to cap

## Integration

The LT Band Controller is integrated into the Decision Engine:
- Runs in NORMAL mode (after risk checks pass)
- Operates independently of derisk logic
- Can run concurrently with other intents

## Logging

Corrective intents are logged with:
- Classification: `[LT_LONG_DECREASE]` etc.
- Priority: `(low priority)`
- Reason: `LT band drift correction: LT_LONG_TOO_HIGH`

## Files

- `app/event_driven/decision_engine/lt_band_controller.py`: Controller logic
- `app/event_driven/decision_engine/engine.py`: Integration
- `app/config/risk_rules.yaml`: Configuration



