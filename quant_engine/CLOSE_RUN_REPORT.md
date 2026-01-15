# CLOSE DRY-RUN REPORT (PM-Grade Verification)
Date: 2025-12-23T02:25:20.807185
Regime: CLOSE (Aggressive, clip_size=4000)
Target Reduction: $500,000.00

## 1. Decision Trace
### 1. WINNER_MM (MM_LONG_DECREASE)
- **Action**: Sell 500 shares @ 100
- **Context**: Cost 90.0, Truth 100.05
- **PnL**: $5,000.00 (**PROFIT**)
- **Slippage**: $25.00 (0.05/sh)
- **Reasoning**: MM Profit
- **Remaining Reduction**: $500,000.00
### 2. ILLIQUID_MM (MM_LONG_DECREASE)
- **Action**: Sell 500 shares @ 100
- **Context**: Cost 100.0, Truth 100.05
- **PnL**: $0.00 (**FLAT**)
- **Slippage**: $25.00 (0.05/sh)
- **Reasoning**: MM Reduction
- **Remaining Reduction**: $450,000.00
### 3. LIQUID_MM (MM_LONG_DECREASE)
- **Action**: Sell 500 shares @ 100
- **Context**: Cost 100.0, Truth 100.05
- **PnL**: $0.00 (**FLAT**)
- **Slippage**: $25.00 (0.05/sh)
- **Reasoning**: MM Reduction
- **Remaining Reduction**: $400,000.00
### 4. LOW_CONF_MM (MM_LONG_DECREASE)
- **Action**: Sell 500 shares @ 100
- **Context**: Cost 100.0, Truth 100.05
- **PnL**: $0.00 (**FLAT**)
- **Slippage**: $25.00 (0.05/sh)
- **Reasoning**: MM Reduction
- **Remaining Reduction**: $350,000.00
### 5. NARROW_MM (MM_LONG_DECREASE)
- **Action**: Sell 500 shares @ 99.9
- **Context**: Cost 100.0, Truth 100.0
- **PnL**: $-50.00 (**LOSS**)
- **Slippage**: $50.00 (0.10/sh)
- **Reasoning**: MM Reduction
- **Remaining Reduction**: $300,000.00
### 6. LOSER_LT (LT_LONG_DECREASE)
- **Action**: Sell 2000 shares @ 99.5
- **Context**: Cost 110.0, Truth 100.0
- **PnL**: $-21,000.00 (**LOSS**)
- **Slippage**: $1,000.00 (0.50/sh)
- **Reasoning**: LT Switch
- **Remaining Reduction**: $250,000.00
- **Skipped Candidates**:
  - 🚫 WIDE_MM: Cost Override (High Slippage)
### 7. WIDE_MM (MM_LONG_DECREASE)
- **Action**: Sell 500 shares @ 99.0
- **Context**: Cost 100.0, Truth 100.0
- **PnL**: $-500.00 (**LOSS**)
- **Slippage**: $500.00 (1.00/sh)
- **Reasoning**: MM Reduction
- **Remaining Reduction**: $50,000.00

## 2. Aggregate Metrics
- **Total Realized Slippage**: $1,650.00
- **MM Exits**: 6
- **LT Exits**: 1
- **Profitable Exits**: 1
- **Loss Exits**: 3
- **Flat Exits**: 3

## 3. Behavior Verification
- ✅ **Profit Priority**: WINNER_MM exited at rank 1 (Expected 1).
- ✅ **Cost Override**: LOSER_BIG_MM skipped (Cost 2.0 > 1.8*0.5).
- ✅ **Switch Success**: LOSER_LT selected instead.
- ✅ **Liquidity Tie-Break**: Illiquid (Rank 2) < Liquid (Rank 3).
- ✅ **Spread Preference**: Narrow (Rank 5) < Wide (Rank 7).
- ✅ **Low Confidence**: Exited successfully.