# MM CHURN STABLE MARKET REPORT
Date: 2025-12-23T02:48:05.678488
Duration: 300.0s

## Timeline
- `T=0.0s` **PREF_A** NEW BUY @ 24.52
- `T=0.0s` **PREF_A** NEW SELL @ 24.58
- `T=150.0s` 📡 **L1 SNAPSHOT ARRIVED** (Unchanged)
- `T=200.0s` 📈 **MARKET MOVED** (Bid:24.55/Ask:24.65)
- `T=200.0s` **PREF_A** REPLACE BUY @ 24.56
- `T=200.0s` **PREF_A** REPLACE SELL @ 24.64

## KPI Summary
- Total Engine Cycles: 300
- Actual Updates/Orders: 4
- Frozen (Stale > 90s): 68
- Skipped (No Change): 230

## Verification Checks
- ✅ **Initial Entry**: Placed orders at T=0.
- ✅ **Silence Verified**: Minimal updates during unchanged market.
- ✅ **Stale Freeze**: Logic activated > 90s age.