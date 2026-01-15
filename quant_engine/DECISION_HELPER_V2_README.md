# DecisionHelperV2 - Modal Price Flow Engine

## 🎯 Overview

DecisionHelperV2 is a **microstructure-aware decision engine** specifically designed for **illiquid preferred stocks and CEF instruments**. Unlike the original DecisionHelper, it uses **modal price flow** instead of first/last trade displacement, making it more robust for sparse trading environments.

## 🔑 Key Differences from DecisionHelper

| Feature | DecisionHelper | DecisionHelperV2 |
|---------|---------------|------------------|
| **Price Metric** | First/Last trade displacement | **Modal displacement** (GRPAN1) |
| **Outlier Handling** | Basic filtering | **Outlier ratio flag** |
| **Price Clustering** | N/A | **GRPAN1/GRPAN2** dual concentration |
| **Flow Analysis** | Simple displacement | **Flow Efficiency** metric |
| **State Classification** | Basic thresholds | **Real Flow Score (RFS)** composite |

## 📊 Core Concepts

### Modal Displacement

**NOT** using first/last trade prices. Instead:

```
GRPAN1_start = Modal price at window start (first half)
GRPAN1_end   = Modal price at window end (second half)

Modal_Displacement = GRPAN1_end - GRPAN1_start
```

This represents **true price migration** and ignores single outlier prints.

### GRPAN (Grouped Real Print Analyzer)

For each window:

1. **Weighting:**
   - `size >= 100 lots` → weight = 1.0
   - `size 10-99 lots` → weight = 0.25

2. **Price Clustering:**
   - Price bin range: ±0.03 USD
   - Compute weighted density per price

3. **GRPAN1 (Primary Modal Price):**
   - Price with highest weighted density
   - `GRPAN1_conf = cluster_weight / total_weight`

4. **GRPAN2 (Secondary Modal Price):**
   - Must be at least 0.06 USD away from GRPAN1
   - Same clustering logic
   - `GRPAN2_conf` computed similarly

### Real Flow Score (RFS)

Composite score combining multiple factors:

```
RFS = 0.30 * D_norm +
      0.20 * R_norm +
      0.20 * S_norm * sign(D_norm) +
      0.15 * E_norm * sign(D_norm) +
      0.15 * sign(Net_Pressure)

RFS ∈ [-1.0, +1.0]
```

Where:
- `D_norm`: Normalized modal displacement
- `R_norm`: Normalized RWVAP difference
- `S_norm`: Normalized SRPAN score
- `E_norm`: Normalized flow efficiency
- `Net_Pressure`: Aggressor-based pressure

## 📈 Metrics

### 1. Modal Displacement
- **Formula**: `GRPAN1_end - GRPAN1_start`
- **Range**: Typically -0.30 to +0.30 USD
- **Normalized**: `clamp(displacement / 0.30, -1, +1)`

### 2. RWVAP (Robust VWAP)
- **Formula**: `sum(price * size) / sum(size)` (excluding extreme prints)
- **Filter**: Exclude prints where `size > AVG_ADV`
- **RWVAP_Diff**: `GRPAN1_end - RWVAP`

### 3. ADV Fraction
- **Formula**: `window_volume / AVG_ADV`
- **Normalized**: `clamp(adv_fraction / 1.0, 0, 1)`

### 4. Flow Efficiency
- **Formula**: `abs(Modal_Displacement) / max(ADV_Fraction, 0.01)`
- **Normalized**: `clamp(efficiency / 3.0, 0, 1)`

### 5. SRPAN Score
- **Balance Score (60%)**: `100 - abs(GRPAN1_conf - GRPAN2_conf)`
- **Total Concentration (15%)**: `min(100, (GRPAN1_conf + GRPAN2_conf) * 100)`
- **Spread Score (25%)**: Linear interpolation between 0.06¢ and 0.30¢
- **Final**: Weighted sum of all three

### 6. Outlier Ratio
- **Formula**: `max_single_print_size / window_volume`
- **Flag**: `SINGLE_PRINT_EVENT` if ratio > 0.40

## 🎯 State Classification

Based on RFS and additional conditions:

```python
if RFS > +0.40:
    BUYER_DOMINANT
elif RFS < -0.40:
    SELLER_DOMINANT
elif abs(Modal_Displacement) < 0.03 and ADV_Fraction > 0.10:
    ABSORPTION
elif abs(Modal_Displacement) > 0.10 and ADV_Fraction < 0.05:
    VACUUM
else:
    NEUTRAL
```

## 📋 Rolling Windows

- **pan_10m**: 10 minutes
- **pan_30m**: 30 minutes
- **pan_1h**: 1 hour
- **pan_3h**: 3 hours
- **pan_1d**: 1 day (trading hours)

**Minimum Requirements:**
- At least 8 valid ticks per window
- If not met: `state = NO_SIGNAL_ILLIQUID`

## 🔧 Data Filters

**Included:**
- ✅ `tradesOnly = true` (only real trades)
- ✅ `size >= 10 lots`
- ✅ `price > 0`
- ✅ `bf = false` (no backfilled ticks)

**Excluded:**
- ❌ Bid/ask updates (`size = 0`)
- ❌ Pseudo-ticks (`bf = true`)
- ❌ Small prints (`size < 10 lots`)
- ❌ Extreme prints (`size > AVG_ADV`) for RWVAP

## 🚀 Usage

### 1. Start Worker

```bash
python -m app.workers.decision_helper_v2_worker
```

Or via `baslat.py` (automated startup).

### 2. Submit Job via API

```python
POST /api/decision-helper-v2/submit-job
{
    "symbols": ["CNO PRA", "WRB PRE"],  # Optional: if None, process all
    "windows": ["pan_10m", "pan_30m", "pan_1h"]  # Optional: defaults shown
}
```

### 3. Retrieve Results

```python
GET /api/decision-helper-v2/result/{symbol}/{window}
GET /api/decision-helper-v2/results/{symbol}  # All windows
```

## 📤 Output Format

```json
{
    "grpan1_start": 21.70,
    "grpan1_end": 21.85,
    "modal_displacement": 0.15,
    "rwvap": 21.75,
    "rwvap_diff": 0.10,
    "adv_fraction": 0.25,
    "flow_efficiency": 0.60,
    "srpan_score": 72.5,
    "rfs": 0.55,
    "state": "BUYER_DOMINANT",
    "flags": [],
    "grpan1_conf": 0.65,
    "grpan2": 21.90,
    "grpan2_conf": 0.35,
    "outlier_ratio": 0.15,
    "tick_count": 45,
    "window_volume": 2500.0,
    "updated_at": "2025-12-19T15:30:00"
}
```

## 🔍 Why Modal Flow?

### Problem with First/Last Displacement

In illiquid markets:
- Single outlier print can skew displacement
- Bid/ask updates create false signals
- Sparse trading makes first/last unreliable

### Solution: Modal Price Flow

- **GRPAN1** represents the **true price level** where most trading occurs
- **Modal displacement** shows **genuine price migration**, not noise
- **Outlier ratio** flags single-print events
- **Flow efficiency** measures price movement per unit volume

## 🎯 Use Cases

1. **Illiquid Preferred Stocks**: CNO-PRA, WRB-PRE, etc.
2. **CEF Instruments**: Closed-end funds with sparse trading
3. **Baby Bonds**: Low-volume fixed income securities
4. **Microstructure Analysis**: Understanding true price flow

## ⚠️ Important Notes

- **DO NOT** refactor existing DecisionHelper
- DecisionHelperV2 runs **independently**
- Redis-compatible for parallel execution
- Safe for illiquid instruments
- Minimum 8 ticks per window required

## 📚 Related Documentation

- `METRIKLER_FORMULLER.md` - GRPAN, RWVAP, SRPAN formulas
- `DECISION_HELPER_METRIKLER.md` - Original DecisionHelper metrics
- `DECISION_HELPER_ILLIQUID_FIX.md` - Illiquid product fixes


