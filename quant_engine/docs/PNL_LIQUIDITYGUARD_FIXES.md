# PnL Calculation Fix & LiquidityGuard Implementation

## A) Dual-Ledger PnL Logic Fix

### Problem

The original implementation incorrectly calculated intraday realized PnL using `befday_cost` (prev_close) as the baseline. This mixed overnight baseline positions with intraday trading decisions.

### Solution

**New Model:**
1. **BefDay Ledger (Baseline)**: 
   - `befday_qty` and `befday_cost=prev_close` are used ONLY for baseline/carry reporting
   - Do NOT use `befday_cost` for intraday realized PnL

2. **Intraday Ledger (Today's Decisions)**:
   - Intraday realized PnL computed using TODAY's fills only
   - Maintain `intraday_avg_fill_price` per symbol per account for today's fills
   - Realized PnL recognized when intraday-opened inventory is closed/reduced within the same day
   - If inventory opened today is carried overnight, it becomes part of next day's baseline (not "intraday realized")

### Implementation

**New Component: `IntradayTracker`**
- Tracks intraday positions separately (long and short)
- Maintains weighted average fill prices for intraday positions
- Calculates realized PnL only when closing intraday-opened positions
- Uses FIFO-like logic: closing long uses `intraday_long_avg_price`, closing short uses `intraday_short_avg_price`

**Updated: `DailyLedger.record_fill()`**
- Uses `IntradayTracker` to calculate realized PnL
- No longer uses `befday_cost` for intraday PnL
- Separates baseline carry from intraday performance

**Updated: `OrderEvent`**
- Added `order_action` field (BUY or SELL) for PnL calculation
- Added `account_id` field for multi-account support

### Test Scenario

```
befday_qty=2000 at prev_close=15.00
today buy 1000 at 15.20
today sell 1000 at 15.30

Expected: intraday realized pnl = +0.10 * 1000 = +100
```

**Result**: ✅ Passes - PnL calculated correctly using intraday fill prices only.

## B) LiquidityGuard / Pre-Trade Sizing Constraints

### Purpose

Prevents order spam and respects market liquidity by applying sizing constraints before sending orders.

### Configuration

**File**: `app/config/liquidity_limits.yaml`

```yaml
global:
  min_lot: 200  # Minimum order size
  scale_factor: 1000  # Divide avg_adv by this to get base_max
  residual_close_policy: "defer"

buckets:
  LT:
    enabled: true
    max_cap: null  # No cap (only base_max)
  
  MM:
    enabled: true
    max_cap: 2000  # Capped at 2000

residual:
  allow_near_close: true  # Within 2 minutes of close
  allow_hard_derisk: true  # During HARD_DERISK
  allow_soft_derisk: false  # During SOFT_DERISK
  near_close_threshold: 2
```

### Rules

1. **Base Max Calculation**:
   ```
   base_max = max(round(avg_adv / scale_factor), min_lot)
   ```

2. **Bucket-Specific Max**:
   - **LT**: `max_qty = base_max` (NO upper cap)
   - **MM**: `max_qty = min(base_max, mm_max_cap)` where `mm_max_cap = 2000`

3. **Quantity Clamping**:
   ```
   qty = clamp(desired_qty, min_lot, max_qty)
   ```

4. **Residual Handling**:
   - If `residual < min_lot`, generally defer (do not spam)
   - Allow residual if:
     - Near close (`minutes_to_close <= 2`) AND `allow_near_close=true`
     - OR `intent_type=HARD_DERISK` AND `allow_hard_derisk=true`
     - OR `intent_type=SOFT_DERISK` AND `allow_soft_derisk=true`

### Integration

**Execution Service**:
- `LiquidityGuard` applied before order creation
- Validates and adjusts quantity from intent
- Logs adjustments and deferrals
- Deferred orders are not sent (returns early)

### Test Scenarios

#### B1: LT Order Not Capped at 2000
```
Desired: 5000 shares
Avg ADV: 10M shares/day
Base Max: 10000
Bucket: LT

Result: Clamped to 5000 (not capped at 2000)
```

#### B2: MM Order Capped at 2000
```
Desired: 5000 shares
Avg ADV: 10M shares/day
Base Max: 10000
Bucket: MM
MM Max Cap: 2000

Result: Clamped to 2000 (min of base_max and mm_max_cap)
```

#### B3: Min Lot Enforced
```
Desired: 100 shares
Min Lot: 200
Not near close

Result: Deferred (qty=0)
```

#### B4: Residual Handling Near Close
```
Desired: 100 shares (< min_lot)
Minutes to Close: 1
Intent Type: HARD_DERISK

Result: Allowed (qty=100)
```

## Usage

### Running Tests

```bash
# From project root (StockTracker directory)
cd quant_engine
python workers/run_pnl_liquidity_tests.py

# Or from quant_engine directory directly
python workers/run_pnl_liquidity_tests.py
```

### Configuration

Edit `app/config/liquidity_limits.yaml` to adjust:
- `min_lot`: Minimum order size
- `scale_factor`: ADV scaling factor
- `buckets.MM.max_cap`: MM order cap
- `residual.*`: Residual handling policies

### Logs

LiquidityGuard logs:
- `✂️ [LiquidityGuard] Adjusted`: Quantity was adjusted
- `🛑 [LiquidityGuard] Deferred`: Order was deferred due to residual

## Files Changed

### New Files
- `app/event_driven/reporting/intraday_tracker.py`: Intraday position tracking
- `app/event_driven/execution/liquidity_guard.py`: LiquidityGuard module
- `app/config/liquidity_limits.yaml`: Configuration
- `app/event_driven/testing/pnl_liquidity_tests.py`: Test scenarios

### Modified Files
- `app/event_driven/reporting/daily_ledger.py`: Uses IntradayTracker
- `app/event_driven/reporting/dual_ledger.py`: Removed incorrect PnL calculation
- `app/event_driven/contracts/events.py`: Added `order_action` and `account_id` to OrderEvent
- `app/event_driven/execution/service.py`: Integrated LiquidityGuard

## Next Steps

1. **Real ADV Lookup**: Replace mock `avg_adv` with real market data
2. **Session State Integration**: Get `minutes_to_close` from session state
3. **Multi-Account Support**: Handle different accounts in LiquidityGuard
4. **Historical Analysis**: Track LiquidityGuard adjustments over time

