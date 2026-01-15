# Decision Helper - Illiquid Products Fix

## Problem

Decision Helper was producing false signals for illiquid preferred stocks and baby bonds (e.g., CNO-PRA) because:

1. **Pseudo-ticks included**: OHLC backfilled ticks (`bf=true`) were counted as trades
2. **Bid/ask updates counted**: Market data updates (size=0) were treated as trades
3. **ADV Fraction inflated**: False volume from pseudo-ticks and bid/ask updates created impossible values (e.g., 541%)
4. **Trade Frequency wrong**: Tick frequency was used instead of real trade frequency
5. **Absorption false positives**: Illiquid products with no real activity were classified as "ABSORPTION"

## Solution

### 1. Real Trade Filtering

**Only REAL TRADES are now included:**
- ✅ `bf=false` (no pseudo-ticks from OHLC backfills)
- ✅ `price > 0` (must have a trade price)
- ✅ `size > 0` (must have trade size)
- ✅ `size <= avg_adv` (exclude FINRA/ADFN prints)

**Excluded:**
- ❌ Backfilled ticks (`bf=true`)
- ❌ Bid/ask updates (`size=0`)
- ❌ Invalid ticks (`price=0`)

### 2. Illiquid Detection

**Hard threshold for signals:**
- If `real_trade_count < 5` → Return `ILLIQUID_NO_SIGNAL` state
- Prevents false signals from insufficient data

### 3. Absorption Protection

**Minimum trade requirement:**
- Absorption requires `trade_count >= 10` (was unlimited)
- Prevents illiquid products from being classified as "ABSORPTION"

### 4. getTicks Configuration

**Worker bootstrap:**
- Changed `tradesOnly=False` → `tradesOnly=True`
- Ensures only real trades are fetched from Hammer Pro
- Filters out bid/ask updates at the source

### 5. Rolling Window Fix

**Window calculation:**
- Uses `last_print_time` instead of `current_time`
- Correctly handles bootstrap data (historical ticks)
- Window: `[last_print_time - window_seconds, last_print_time]`

## State Classification Updates

### New States

**ILLIQUID_NO_SIGNAL:**
- Triggered when `real_trade_count < 5`
- Confidence: 0.0
- Reason: "Too few real trades - insufficient data for signal"

### Updated Logic

**ABSORPTION:**
- Now requires `trade_count >= 10`
- Prevents false positives in illiquid products

**All other states:**
- Require `trade_count >= 5`
- Return `NEUTRAL` with low confidence if insufficient trades

## Metrics Calculation

### ADV Fraction
- **Before**: Included pseudo-ticks and bid/ask updates
- **After**: Only real trade volume (`sum(size)` where `bf=false`, `price>0`, `size>0`)

### Trade Frequency
- **Before**: `len(all_ticks) / window_minutes` (included bid/ask updates)
- **After**: `len(real_trades) / window_minutes` (only real trades)

### Price Displacement
- **Before**: Could use bid/ask updates (price changes without trades)
- **After**: Only real trade prices

## Example: CNO-PRA

### Before Fix
- **State**: ABSORPTION (false positive)
- **ADV Fraction**: 541% (impossible - includes pseudo-ticks)
- **Trade Frequency**: 6.1 (includes bid/ask updates)
- **Real trades**: ~1-2 per day

### After Fix
- **State**: ILLIQUID_NO_SIGNAL
- **ADV Fraction**: 0.0% (no real trades in window)
- **Trade Frequency**: 0.0 (no real trades)
- **Real trades**: < 5 → No signal

## Configuration

### Thresholds (in `_classify_state`)

```python
MIN_TRADES_FOR_SIGNAL = 5      # Minimum real trades for any signal
MIN_TRADES_FOR_ABSORPTION = 10  # Absorption requires more trades
```

### Filtering (in `compute_metrics`)

```python
# Only include if:
- bf == False
- price > 0
- size > 0
- size <= avg_adv
```

## Testing

To verify the fix:

1. Check illiquid products (CNO-PRA, etc.)
2. Verify state is `ILLIQUID_NO_SIGNAL` when `real_trade_count < 5`
3. Verify ADV Fraction is realistic (not 500%+)
4. Verify Trade Frequency matches actual trade count
5. Verify Absorption only triggers with `trade_count >= 10`

## Notes

- This fix is **critical** for illiquid preferred stocks and baby bonds
- Liquid products are unaffected (they have sufficient real trades)
- The system now correctly distinguishes between:
  - Real market activity (trades)
  - Market data updates (bid/ask changes)
  - Pseudo-data (OHLC backfills)


