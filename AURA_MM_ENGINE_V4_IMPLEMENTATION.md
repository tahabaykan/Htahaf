# Aura MM Engine v4 - Progressive Benchmark-Shock Quoting Model

## Özet

Aura MM Engine v4, preferred stock'lar için gerçek market-making (spread trading) yapılabilirliğini ölçen bir sistemdir. Bu versiyon, progressive benchmark-shock quoting model ve tradeable MM constraints ile geliştirilmiştir.

## Temel Değişiklikler

### 1. Progressive Benchmark-Shock Quoting Model

**Eski Yaklaşım:** Tek threshold "PFF shock" mantığı

**Yeni Yaklaşım:** Step-based levels

```python
pff_step = 0.04  # Her shock level = $0.04
shock_level = floor(abs(pff_change_now) / pff_step)
shock_impulse = floor(abs(pff_delta_5m) / pff_step)
effective_shock = max(shock_level, shock_impulse)
shock_dir = sign(pff_change_now)
```

**Örnek Senaryolar:**

- **PFF değişimi = $0.08 (yukarı):**
  - `shock_level = floor(0.08 / 0.04) = 2`
  - `effective_shock = 2`
  - Quote aggressiveness artar

- **PFF değişimi = $0.12 (aşağı):**
  - `shock_level = floor(0.12 / 0.04) = 3`
  - `effective_shock = 3`
  - Daha agresif quote positioning

### 2. Adaptive Quote Aggressiveness

**Base Fraction:** `0.15` (spread'in %15'i)

**Max Fraction:** `0.30` (spread'in %30'u)

**Shock-based increment:**
```python
shock_frac = min(max_frac, base_frac + 0.03 * effective_shock)
```

**Front-run booster:**
```python
effective_frac = min(max_frac, shock_frac + 0.02 * front_run_steps)
```

**Örnek Hesaplama:**

- **Normal durum (shock = 0):**
  - `effective_frac = 0.15`
  - Spread = $0.10 → Buy quote = bid + $0.015, Sell quote = ask - $0.015

- **Shock level = 2:**
  - `shock_frac = 0.15 + 0.03 * 2 = 0.21`
  - Spread = $0.10 → Buy quote = bid + $0.021, Sell quote = ask - $0.021

- **Shock level = 3 + front_run_steps = 2:**
  - `shock_frac = 0.15 + 0.03 * 3 = 0.24`
  - `effective_frac = 0.24 + 0.02 * 2 = 0.28`
  - Spread = $0.10 → Buy quote = bid + $0.028, Sell quote = ask - $0.028

### 3. Tradeable MM Constraints

**Hard Constraints:**

1. **Minimum Market Spread:** `0.06$`
   - Eğer `spread < 0.06` → `tradeable_mm = False`
   - Reason: "Market spread too tight"

2. **Minimum Order Gap:** `0.04$`
   - Eğer `sell_quote - buy_quote < 0.04` → `tradeable_mm = False`
   - Reason: "Order gap too small"

**Örnek Senaryolar:**

- **Spread = $0.05:**
  - ❌ `tradeable_mm = False`
  - Reason: "Market spread 0.05 < 0.06"

- **Spread = $0.08, effective_frac = 0.15:**
  - Buy quote = bid + $0.012
  - Sell quote = ask - $0.012
  - Order gap = $0.08 - $0.024 = $0.056 ✅
  - `tradeable_mm = True`

- **Spread = $0.08, effective_frac = 0.30 (max):**
  - Buy quote = bid + $0.024
  - Sell quote = ask - $0.024
  - Order gap = $0.08 - $0.048 = $0.032 ❌
  - `tradeable_mm = False`
  - Reason: "Order gap 0.032 < 0.04"

### 4. MM-Anchor Selection (Tradeable Anchors)

**Volav Merge Process:**

1. **Initial merge:** `merge_threshold = min_gap * 0.90`
   - Yakın Volav'lar birleştirilir (noise temizleme)

2. **MM-Anchor merge pass:**
   - Volav'lar fiyat sırasına konur
   - Adjacent Volav'lar arası gap < 0.06 ise birleştirilir
   - Volume-weighted average center hesaplanır
   - Tüm gap'ler >= 0.06 olana kadar tekrarlanır

**Örnek:**

**Input Volavs:**
- Volav1: $18.21 (volume: 500)
- Volav2: $18.25 (volume: 300)
- Volav3: $18.29 (volume: 200)
- Volav4: $18.33 (volume: 400)

**Step 1: Initial merge (merge_threshold = 0.027):**
- Gap(18.21, 18.25) = 0.04 > 0.027 → Separate
- Gap(18.25, 18.29) = 0.04 > 0.027 → Separate
- Gap(18.29, 18.33) = 0.04 > 0.027 → Separate

**Step 2: MM-Anchor merge (gap < 0.06):**
- Gap(18.21, 18.25) = 0.04 < 0.06 → Merge
  - Merged: $18.23 (volume: 800) = (18.21*500 + 18.25*300) / 800
- Gap(18.29, 18.33) = 0.04 < 0.06 → Merge
  - Merged: $18.31 (volume: 600) = (18.29*200 + 18.33*400) / 600
- Gap(18.23, 18.31) = 0.08 >= 0.06 → Separate ✅

**Final MM-Anchors:**
- Anchor1: $18.23 (volume: 800)
- Anchor2: $18.31 (volume: 600)
- Gap: $0.08 >= $0.06 ✅

### 5. Two-Sidedness / Homogeneity Scoring

**Volume Share Calculation:**
```python
share1 = a1_volume / (a1_volume + a2_volume)
share2 = a2_volume / (a1_volume + a2_volume)
balance = 1 - abs(share1 - share2)
```

**Extreme One-Sidedness Penalty:**
- Eğer `max(share1, share2) > 0.95` → `two_sided_score *= 0.5`

**Örnek Senaryolar:**

- **50/50 split:**
  - `balance = 1 - abs(0.5 - 0.5) = 1.0` ✅ Mükemmel

- **80/20 split:**
  - `balance = 1 - abs(0.8 - 0.2) = 0.4` ⚠️ Hâlâ oynanabilir

- **95/5 split:**
  - `balance = 1 - abs(0.95 - 0.05) = 0.1`
  - `two_sided_score = 0.1 * 0.5 = 0.05` ❌ Ağır ceza

### 6. Confidence Function (Continuous, Not Hard Kill)

**Eski Yaklaşım:** `ticks < 15` → Hard kill (N/A)

**Yeni Yaklaşım:** Continuous confidence function

```python
tick_score = 1 - exp(-ticks / 12)
volume_score = 1 - exp(-volume_fraction / 0.15)
confidence = (tick_score + volume_score) / 2
```

**Örnek Senaryolar:**

- **3 ticks, volume_fraction = 0.05:**
  - `tick_score = 1 - exp(-3/12) = 0.22`
  - `volume_score = 1 - exp(-0.05/0.15) = 0.28`
  - `confidence = (0.22 + 0.28) / 2 = 0.25` ⚠️ Düşük confidence

- **15 ticks, volume_fraction = 0.15:**
  - `tick_score = 1 - exp(-15/12) = 0.71`
  - `volume_score = 1 - exp(-0.15/0.15) = 0.63`
  - `confidence = (0.71 + 0.63) / 2 = 0.67` ✅ Orta confidence

- **50 ticks, volume_fraction = 0.30:**
  - `tick_score = 1 - exp(-50/12) = 0.98`
  - `volume_score = 1 - exp(-0.30/0.15) = 0.86`
  - `confidence = (0.98 + 0.86) / 2 = 0.92` ✅ Yüksek confidence

### 7. Relative Value Bias Metrics

**Hesaplama:**
```python
symbol_change = last_truth_price - prev_close
bench_change = pff_change_now
buy_cheap = bench_change - symbol_change
sell_rich = symbol_change - bench_change
```

**Skew Sizing:**
- Eğer `buy_cheap > 0.05` → `buy_size_mult = 1.2` (buy tarafına daha fazla)
- Eğer `sell_rich > 0.05` → `sell_size_mult = 1.2` (sell tarafına daha fazla)

**Örnek Senaryolar:**

- **Symbol = $22.50, prev_close = $22.40, PFF change = +$0.10:**
  - `symbol_change = 22.50 - 22.40 = +$0.10`
  - `bench_change = +$0.10`
  - `buy_cheap = 0.10 - 0.10 = $0.00` → Neutral
  - `sell_rich = 0.10 - 0.10 = $0.00` → Neutral

- **Symbol = $22.50, prev_close = $22.40, PFF change = +$0.15:**
  - `symbol_change = +$0.10`
  - `bench_change = +$0.15`
  - `buy_cheap = 0.15 - 0.10 = +$0.05` → Symbol cheap relative to benchmark
  - `buy_size_mult = 1.2` → Buy tarafına %20 daha fazla

- **Symbol = $22.50, prev_close = $22.40, PFF change = +$0.05:**
  - `symbol_change = +$0.10`
  - `bench_change = +$0.05`
  - `sell_rich = 0.10 - 0.05 = +$0.05` → Symbol rich relative to benchmark
  - `sell_size_mult = 1.2` → Sell tarafına %20 daha fazla

## UI Değişiklikleri

### 1. Search/Filter Box
- Client-side symbol filtering
- Real-time search as you type

### 2. Text Colors (Readable Contrast)
- **Normal text:** `#1f2937` (dark gray, readable on white)
- **Secondary text:** `#4b5563` (medium gray)
- **Disabled/N/A:** `#9ca3af` (light gray)
- **No gray-on-white:** Tüm text colors kontrast garantili

### 3. Field Rename
- **"Buy Zone" / "Sell Zone"** → **"Anchor Zone 1 (Buy)" / "Anchor Zone 2 (Sell)"**
- **"Buy Price" / "Sell Price"** → **"Trade Quote (Buy)" / "Trade Quote (Sell)"**
- Anchor detayları: `price | volume | tick_count | %share`

### 4. Tradeable MM Display
- Eğer `tradeable_mm = False`:
  - Trade Quotes: `N/A` + reason (küçük font, light gray)
  - Expected Profit: `N/A` (light gray)

## Örnek Senaryolar ve Sonuçlar

### Senaryo 1: Normal Market, İki Taraflı Flow

**Input:**
- Symbol: AHL PRE
- Spread: $0.08
- PFF change: +$0.04
- Anchor1: $22.25 (volume: 800, 50%)
- Anchor2: $22.33 (volume: 800, 50%)
- Anchor gap: $0.08

**Hesaplama:**
- `shock_level = floor(0.04 / 0.04) = 1`
- `effective_frac = 0.15 + 0.03 * 1 = 0.18`
- `buy_quote = bid + 0.08 * 0.18 = bid + $0.014`
- `sell_quote = ask - 0.08 * 0.18 = ask - $0.014`
- `order_gap = 0.08 - 0.028 = $0.052 >= 0.04` ✅
- `two_sided_score = 1.0` (50/50)
- `tradeable_mm = True`

**Sonuç:**
- MM Score: Yüksek (two-sided + tradeable)
- Trade Quotes: Gösterilir
- Expected Profit: Hesaplanır

### Senaryo 2: PFF Shock, Tek Taraflı Flow

**Input:**
- Symbol: MS PRO
- Spread: $0.10
- PFF change: +$0.12 (shock level = 3)
- Anchor1: $23.50 (volume: 950, 95%)
- Anchor2: $23.60 (volume: 50, 5%)
- Anchor gap: $0.10

**Hesaplama:**
- `effective_frac = 0.15 + 0.03 * 3 = 0.24`
- `buy_quote = bid + 0.10 * 0.24 = bid + $0.024`
- `sell_quote = ask - 0.10 * 0.24 = ask - $0.024`
- `order_gap = 0.10 - 0.048 = $0.052 >= 0.04` ✅
- `two_sided_score = (1 - abs(0.95 - 0.05)) * 0.5 = 0.05` ❌ (extreme penalty)
- `tradeable_mm = True` (ama düşük score)

**Sonuç:**
- MM Score: Düşük (one-sided penalty)
- Trade Quotes: Gösterilir (ama düşük confidence)
- Expected Profit: Hesaplanır

### Senaryo 3: Tight Spread, Tradeable Değil

**Input:**
- Symbol: REGCO
- Spread: $0.04
- Anchor gap: $0.08

**Hesaplama:**
- `spread = $0.04 < $0.06` ❌
- `tradeable_mm = False`
- Reason: "Market spread 0.04 < 0.06"

**Sonuç:**
- MM Score: 0 (gating)
- Trade Quotes: `N/A` + reason
- Expected Profit: `N/A`

### Senaryo 4: Relative Value Bias (Symbol Cheap)

**Input:**
- Symbol: FITBI
- Spread: $0.08
- Last truth price: $18.50
- Prev close: $18.45
- PFF change: +$0.10

**Hesaplama:**
- `symbol_change = 18.50 - 18.45 = +$0.05`
- `bench_change = +$0.10`
- `buy_cheap = 0.10 - 0.05 = +$0.05` ✅
- `buy_size_mult = 1.2`

**Sonuç:**
- Buy tarafına %20 daha fazla size önerilir
- Symbol benchmark'a göre ucuz → buy opportunity

## Sonuç

Aura MM Engine v4, progressive benchmark-shock quoting model ve tradeable MM constraints ile:

1. ✅ **Gerçek MM mantığına uygun:** Spread + exit probability odaklı
2. ✅ **Adaptive aggressiveness:** PFF shock'a göre dinamik quote positioning
3. ✅ **Hard constraints:** Tradeable olmayan durumları filtreler
4. ✅ **Two-sided flow odaklı:** Tek taraflı flow'ları cezalandırır
5. ✅ **Relative value aware:** Benchmark'a göre ucuz/pahalı hisseleri tespit eder
6. ✅ **Continuous confidence:** Hard kill yerine smooth confidence function

Bu sistem, preferred stock micro-structure'a özel optimize edilmiş, gerçek market maker davranışını yansıtan bir screener ve execution assistant'tır.



