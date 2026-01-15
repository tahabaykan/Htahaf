# RUNALL Detaylı Analiz - Janall vs Quant Engine

## 📋 Executive Summary

Bu rapor, **Janall** uygulamasındaki RUNALL'ın **TAM OLARAK** ne yaptığını, hangi veri kaynaklarını kullandığını, hangi koşulları kontrol ettiğini ve nasıl karar verdiğini **ADIM ADIM** açıklamaktadır. Ayrıca, Quant Engine'de aynı yapının nasıl implement edilmesi gerektiğini detaylandırmaktadır.

---

## 🎯 RUNALL Nedir?

**RUNALL**, PSFALGO sisteminin ana orchestrator'üdür. Sürekli çalışan bir döngü (cycle) içinde:
1. Pozisyonları analiz eder
2. Kar alma (KARBOTU) veya pozisyon azaltma (REDUCEMORE) kararları verir
3. Yeni pozisyon açma (ADDNEWPOS) kararları verir
4. Bu kararları emir önerilerine (proposal) dönüştürür
5. Kullanıcı onayı bekler

---

## 📊 Janall RUNALL - TAM AKIŞ

### Genel Yapı

```
┌─────────────────────────────────────────────────────────────┐
│                    JANALL RUNALL FLOW                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [User Click] → RUNALL Button                              │
│      │                                                      │
│      ├─> runall_loop_count++                               │
│      │                                                      │
│      ├─> Adım 1: Pozisyonları Güncelle                    │
│      │      │                                                │
│      │      └─> hammer.get_positions()                     │
│      │              │                                        │
│      │              └─> Take Profit Panel Tree'ye yaz     │
│      │                                                      │
│      ├─> Adım 2: DataFrame'i Güncelle                     │
│      │      │                                                │
│      │      └─> calculate_scores()                          │
│      │              │                                        │
│      │              ├─> hammer.get_market_data()            │
│      │              ├─> Skorları hesapla                    │
│      │              └─> DataFrame'e yaz                     │
│      │                                                      │
│      ├─> Adım 3: Exposure Hesapla                          │
│      │      │                                                │
│      │      └─> pot_total, pot_max hesapla                 │
│      │                                                      │
│      ├─> Adım 4: Mode Belirle (OFANSIF/DEFANSIF)          │
│      │      │                                                │
│      │      └─> pot_total / pot_max oranına göre           │
│      │                                                      │
│      ├─> Adım 5: KARBOTU veya REDUCEMORE                   │
│      │      │                                                │
│      │      ├─> OFANSIF → KARBOTU                           │
│      │      │      │                                          │
│      │      │      └─> karbotu_step_2_fbtot_lt_110()       │
│      │      │              │                                  │
│      │      │              ├─> Take Profit Panel Tree       │
│      │      │              ├─> DataFrame (Fbtot, Ask Sell)  │
│      │      │              ├─> Filter: fbtot < 1.10         │
│      │      │              ├─> Filter: ask_sell > -0.10     │
│      │      │              ├─> Lot: qty * 50%               │
│      │      │              └─> Confirmation Window          │
│      │      │                                                      │
│      │      └─> DEFANSIF → REDUCEMORE                       │
│      │              │                                          │
│      │              └─> reduce_more_step_2_fbtot_lt_110()   │
│      │                      │                                  │
│      │                      ├─> Take Profit Panel Tree       │
│      │                      ├─> DataFrame (Fbtot, Ask Sell)  │
│      │                      ├─> Filter: fbtot < 1.10         │
│      │                      ├─> Filter: ask_sell > -0.20     │
│      │                      ├─> Lot: qty * 100%             │
│      │                      └─> Confirmation Window          │
│      │                                                      │
│      ├─> Adım 6: ADDNEWPOS (Eğer pot_total < pot_max)     │
│      │      │                                                │
│      │      └─> FinalThgLotDistributor.distribute_lots()    │
│      │              │                                        │
│      │              ├─> DataFrame (ALL symbols)             │
│      │              ├─> Filter: bid_buy < -0.06, fbtot > 1.10│
│      │              ├─> JFIN Selection                      │
│      │              ├─> Portfolio Rules → Lot               │
│      │              ├─> MAXALW Check                       │
│      │              └─> Confirmation Window                │
│      │                                                      │
│      ├─> Adım 7: Emirleri Kontrol Et                      │
│      │      │                                                │
│      │      └─> hammer.get_orders()                        │
│      │                                                      │
│      ├─> Adım 8: Tüm Emirleri İptal Et (Opsiyonel)       │
│      │      │                                                │
│      │      └─> runall_cancel_orders_and_restart()         │
│      │                                                      │
│      └─> Adım 9: Döngüyü Tekrarla (60 saniye sonra)      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 ADIM ADIM DETAYLI ANALİZ

### ADIM 1: Pozisyonları Güncelle

**Janall:**
```python
# main_window.py - runall_loop()
def runall_loop(self):
    # 1. DATA SOURCE: Hammer Pro Positions
    positions = self.hammer.get_positions()
    
    # 2. DATA PROCESSING: Take Profit Panel Tree'ye yaz
    for pos in positions:
        symbol = pos['symbol']
        qty = pos['qty']
        avg_price = pos['avg_price']
        
        # Take Profit Panel Tree'ye ekle/güncelle
        self.take_profit_longs_panel.update_position(symbol, qty, avg_price)
```

**Veri Kaynakları:**
- **Hammer Pro API**: `hammer.get_positions()`
- **Format**: `[{'symbol': 'RLJ PRA', 'qty': 1000, 'avg_price': 25.50}, ...]`
- **Update Frequency**: Her RUNALL cycle'da (60 saniyede bir)

**Quant Engine'de Karşılığı:**
```python
# runall_engine.py - _step_update_exposure()
async def _step_update_exposure(self):
    # PositionSnapshotAPI.get_position_snapshot()
    #   ├─> HAMMER: hammer_positions_service.get_positions()
    #   └─> IBKR: ibkr_connector.get_positions()
```

---

### ADIM 2: DataFrame'i Güncelle (Skorları Hesapla)

**Janall:**
```python
# main_window.py - runall_loop()
def runall_loop(self):
    # 1. DATA SOURCE: DataFrame (self.df) - CSV'den yüklenen statik data
    #    - prev_close, FINAL_THG, MAXALW, GROUP, CGRUP, SMA63 chg, SMA246 chg
    
    # 2. DATA SOURCE: Live Market Data (Hammer)
    for symbol in self.df['PREF IBKR'].tolist():
        market_data = self.hammer.get_market_data(symbol)
        bid = market_data.get('bid')
        ask = market_data.get('ask')
        last = market_data.get('last')
        
        # 3. SKOR HESAPLAMA: calculate_scores()
        self.calculate_scores(symbol)
        #     │
        #     ├─> Bid Buy Ucuzluk = (bid - prev_close) / prev_close - benchmark_chg
        #     ├─> Ask Sell Pahalılık = (ask - prev_close) / prev_close - benchmark_chg
        #     ├─> Final_BB_skor = Bid Buy Ucuzluk * 800 + Fbtot
        #     ├─> Final_FB_skor = Front Buy Ucuzluk * 800 + Fbtot
        #     └─> DataFrame'e yaz: self.df.at[symbol, 'Final BB'] = final_bb
        
        # 4. GROUP METRICS: update_scores_with_market_data()
        self.update_scores_with_market_data(symbol)
        #     │
        #     ├─> Fbtot = Group içindeki rank (1.00 = en yüksek)
        #     ├─> SFStot = Group içindeki rank (shorts için)
        #     └─> GORT = Group ortalamasına göre performans
```

**Veri Kaynakları:**
- **DataFrame (self.df)**: CSV'den yüklenen statik data
  - `prev_close`, `FINAL_THG`, `MAXALW`, `GROUP`, `CGRUP`, `SMA63 chg`, `SMA246 chg`
- **Hammer Pro**: `hammer.get_market_data(symbol)` → `bid`, `ask`, `last`
- **Hesaplanan Skorlar**: `calculate_scores()` → DataFrame'e yazılır
- **Update Frequency**: Her RUNALL cycle'da (60 saniyede bir) TÜM symbol'ler için

**Quant Engine'de Karşılığı:**
```python
# DataFabric.get_fast_snapshot() - Event-driven
#   ├─> _live_data: bid, ask, last (L1Update'ten)
#   ├─> _static_data: prev_close, FINAL_THG, MAXALW, GROUP, CGRUP (CSV'den)
#   └─> _derived_data: Fbtot, Bid Buy Ucuzluk, Final_BB_skor (FastScoreCalculator)
```

---

### ADIM 3: Exposure Hesapla

**Janall:**
```python
# main_window.py - runall_loop()
def runall_loop(self):
    # 1. DATA SOURCE: Take Profit Panel Tree (pozisyonlar)
    total_long_value = 0
    total_short_value = 0
    
    for item in self.take_profit_longs_panel.tree.get_children():
        values = self.take_profit_longs_panel.tree.item(item)['values']
        qty = float(values[2])
        current_price = float(values[3])  # DataFrame'den veya market data'dan
        total_long_value += qty * current_price
    
    # 2. HESAPLAMA
    pot_total = total_long_value + abs(total_short_value)
    pot_max = 1000000  # Sabit veya config'den
    
    # 3. ORAN
    exposure_ratio = pot_total / pot_max
```

**Veri Kaynakları:**
- **Take Profit Panel Tree**: Pozisyonlar (qty, current_price)
- **DataFrame veya Market Data**: Current price
- **Config**: `pot_max` (sabit: 1,000,000)

**Quant Engine'de Karşılığı:**
```python
# ExposureCalculator.calculate_exposure()
#   ├─> PositionSnapshotAPI.get_position_snapshot()
#   └─> DataFabric.get_fast_snapshot() → current_price
```

---

### ADIM 4: Mode Belirle (OFANSIF/DEFANSIF)

**Janall:**
```python
# main_window.py - runall_loop()
def runall_loop(self):
    # 1. HESAPLAMA
    exposure_ratio = pot_total / pot_max
    
    # 2. MODE BELİRLEME
    if exposure_ratio < 0.60:  # %60'ın altında
        mode = 'OFANSIF'  # KARBOTU çalışacak
    else:
        mode = 'DEFANSIF'  # REDUCEMORE çalışacak
```

**Koşullar:**
- **OFANSIF**: `exposure_ratio < 0.60` → KARBOTU çalışır
- **DEFANSIF**: `exposure_ratio >= 0.60` → REDUCEMORE çalışır

**Quant Engine'de Karşılığı:**
```python
# runall_engine.py - _determine_exposure_mode()
def _determine_exposure_mode(self):
    if self.current_exposure.pot_total / self.current_exposure.pot_max < 0.60:
        return 'OFANSIF'
    else:
        return 'DEFANSIF'
```

---

### ADIM 5: KARBOTU veya REDUCEMORE

#### 5A. KARBOTU (OFANSIF Mode)

**Janall:**
```python
# main_window.py - karbotu_step_2_fbtot_lt_110()
def karbotu_step_2_fbtot_lt_110(self):
    # 1. DATA SOURCE: Take Profit Longs Panel Tree
    for item in self.take_profit_longs_panel.tree.get_children():
        values = self.take_profit_longs_panel.tree.item(item)['values']
        
        # 2. DATA SOURCE: DataFrame (self.df)
        symbol = values[1]  # PREF IBKR
        fbtot = float(values[5])  # Fbtot (DataFrame'den)
        ask_sell_pahalilik = float(values[8])  # Ask Sell Pahalılık (DataFrame'den)
        qty = float(values[2])  # Quantity (Hammer positions)
        
        # 3. FILTER CONDITIONS
        if fbtot < 1.10 and ask_sell_pahalilik > -0.10:
            # 4. LOT CALCULATION
            lot_percentage = 50  # Step 2: 50%
            calculated_lot = qty * (lot_percentage / 100)
            
            # 5. CONFIRMATION WINDOW
            self.karbotu_select_positions_and_confirm(
                filtered_positions, 
                "Ask Sell", 
                50, 
                "Adım 2"
            )
```

**Veri Kaynakları:**
- **Take Profit Panel Tree**: Pozisyonlar (symbol, qty)
- **DataFrame (self.df)**: `Fbtot`, `Ask Sell Pahalılık`
- **Filter Koşulları**:
  - `fbtot < 1.10`
  - `ask_sell_pahalilik > -0.10`
- **Lot Hesaplama**: `qty * 50%`

**KARBOTU Adımları (13 Adım):**
1. **Step 1**: GORT Filter (LONGS) - `gort > -1`, `ask_sell > -0.05`
2. **Step 2**: `fbtot < 1.10`, `ask_sell > -0.10` → **50%**
3. **Step 3**: `fbtot 1.11-1.45`, `ask_sell -0.05 to +0.04` → **25%**
4. **Step 4**: `fbtot 1.11-1.45`, `ask_sell > +0.05` → **50%**
5. **Step 5**: `fbtot 1.46-1.85`, `ask_sell +0.05 to +0.10` → **25%**
6. **Step 6**: `fbtot 1.46-1.85`, `ask_sell > +0.10` → **50%**
7. **Step 7**: `fbtot 1.86-2.10`, `ask_sell > +0.20` → **25%**
8. **Step 8**: GORT Filter (SHORTS) - `gort < 1`, `bid_buy < +0.05`
9. **Step 9**: `sfstot > 1.70` → **50%**
10. **Step 10**: `sfstot 1.40-1.69`, `bid_buy +0.05 to -0.04` → **25%**
11. **Step 11**: `sfstot 1.40-1.69`, `bid_buy < -0.05` → **50%**
12. **Step 12**: `sfstot 1.10-1.39`, `bid_buy +0.05 to -0.04` → **25%**
13. **Step 13**: `sfstot 1.10-1.39`, `bid_buy < -0.05` → **50%**

#### 5B. REDUCEMORE (DEFANSIF Mode)

**Janall:**
```python
# main_window.py - reduce_more_step_2_fbtot_lt_110()
def reduce_more_step_2_fbtot_lt_110(self):
    # 1. DATA SOURCE: Take Profit Longs Panel Tree (REDUCEMORE version)
    for item in self.take_profit_longs_panel_reducemore.tree.get_children():
        values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
        
        # 2. DATA SOURCE: DataFrame (self.df)
        symbol = values[1]
        fbtot = float(values[5])
        ask_sell_pahalilik = float(values[8])
        qty = float(values[2])
        
        # 3. FILTER CONDITIONS (DIFFERENT FROM KARBOTU)
        if fbtot < 1.10 and ask_sell_pahalilik > -0.20:  # -0.20 (not -0.10)
            # 4. LOT CALCULATION (DIFFERENT FROM KARBOTU)
            lot_percentage = 100  # Step 2: 100% (not 50%)
            calculated_lot = qty * (lot_percentage / 100)
```

**Farklar:**
- **Filter Threshold**: `ask_sell_pahalilik > -0.20` (KARBOTU'da `-0.10`)
- **Lot Percentage**: `100%` (KARBOTU'da `50%`)
- **Amaç**: Daha agresif pozisyon azaltma

**Quant Engine'de Karşılığı:**
```python
# runall_engine.py - _step_run_karbotu() veya _step_run_reducemore()
#   ├─> PositionSnapshotAPI.get_position_snapshot()
#   ├─> MetricsSnapshotAPI.get_metrics_snapshot()
#   └─> karbotu_decision_engine() veya reducemore_decision_engine()
```

---

### ADIM 6: ADDNEWPOS (Yeni Pozisyon Açma)

**Janall:**
```python
# final_thg_lot_distributor.py - distribute_lots()
class FinalThgLotDistributor:
    def distribute_lots(self):
        # 1. DATA SOURCE: DataFrame (self.df) - ALL symbols
        all_symbols = self.df['PREF IBKR'].tolist()
        
        # 2. DATA SOURCE: Live Market Data (Hammer)
        for symbol in all_symbols:
            market_data = self.main_window.hammer.get_market_data(symbol)
            bid = market_data.get('bid')
            ask = market_data.get('ask')
            last = market_data.get('last')
            
            # 3. DATA SOURCE: DataFrame - Static + Calculated
            row = self.df[self.df['PREF IBKR'] == symbol].iloc[0]
            final_bb = row.get('Final BB')
            final_fb = row.get('Final FB')
            fbtot = row.get('Fbtot')
            bid_buy_ucuzluk = row.get('Bid Buy Ucuzluk')
            sma63_chg = row.get('SMA63 chg')
            gort = row.get('GORT')
            maxalw = row.get('MAXALW')
            group = row.get('GROUP')
            cgrup = row.get('CGRUP')
            
            # 4. FILTER CONDITIONS
            # AddLong:
            if bid_buy_ucuzluk < -0.06 and fbtot > 1.10:
                # 5. JFIN SELECTION
                # Group-based selection:
                # - Each group: Top X% by Final_FB_skor
                # - Then: Top X% by Final_BB_skor
                # - Alpha-weighted lot distribution
                
                # 6. LOT CALCULATION
                # Portfolio rules:
                # - < 1%: MAXALW × 0.50, Portfolio × 5%
                # - 1-3%: MAXALW × 0.40, Portfolio × 4%
                # - 3-5%: MAXALW × 0.30, Portfolio × 3%
                # - 5-7%: MAXALW × 0.20, Portfolio × 2%
                # - 7-10%: MAXALW × 0.10, Portfolio × 1.5%
                # - >= 10%: MAXALW × 0.05, Portfolio × 1%
                
                # 7. MAXALW CHECK
                befday_qty = self.main_window.load_bef_position(symbol)
                current_qty = self.get_current_position(symbol)
                open_orders_qty = self.get_open_orders_sum(symbol)
                
                max_change_limit = maxalw * 3 / 4
                potential_daily_change = abs((current_qty + open_orders_qty + lot) - befday_qty)
                
                if potential_daily_change > max_change_limit:
                    # Block order
                    continue
                
                # 8. CONFIRMATION WINDOW
                self.show_order_confirmation_window(orders)
```

**Veri Kaynakları:**
- **DataFrame (self.df)**: TÜM symbol'ler (440 symbol)
- **Hammer Pro**: `bid`, `ask`, `last`
- **DataFrame (self.df)**: `Final_BB_skor`, `Final_FB_skor`, `Fbtot`, `Bid Buy Ucuzluk`, `SMA63 chg`, `GORT`, `MAXALW`, `GROUP`, `CGRUP`
- **CSV**: `befham.csv` veya `befibgun.csv` → `befday_qty`
- **Hammer Pro**: `get_positions()` → `current_qty`
- **Hammer Pro**: `get_orders()` → `open_orders_qty`

**Filter Koşulları:**
- `bid_buy_ucuzluk < -0.06`
- `fbtot > 1.10`
- `spread < 0.25` (opsiyonel)
- `AVG_ADV > 100.0` (opsiyonel)
- `sma63_chg < threshold` (opsiyonel)
- `gort < threshold` (opsiyonel)

**JFIN Selection Logic:**
1. **Group Selection**: Her grup için:
   - `Final_FB_skor`'a göre sırala (descending)
   - Top X% al (default: 50%)
   - Sonra `Final_BB_skor`'a göre sırala (descending)
   - Top X% al (default: 50%)
2. **Lot Distribution**: Alpha-weighted (Final_BB_skor based)
3. **MAXALW Limit**: `max_change_limit = maxalw * 3 / 4`

**Portfolio Rules (Lot Calculation):**
- `< 1%`: `min(MAXALW × 0.50, Portfolio × 5%)`
- `1-3%`: `min(MAXALW × 0.40, Portfolio × 4%)`
- `3-5%`: `min(MAXALW × 0.30, Portfolio × 3%)`
- `5-7%`: `min(MAXALW × 0.20, Portfolio × 2%)`
- `7-10%`: `min(MAXALW × 0.10, Portfolio × 1.5%)`
- `>= 10%`: `min(MAXALW × 0.05, Portfolio × 1%)`

**MAXALW Check:**
- `befday_qty`: CSV'den (`befham.csv` veya `befibgun.csv`)
- `current_qty`: `hammer.get_positions()`
- `open_orders_qty`: `hammer.get_orders()`
- `potential_daily_change = abs((current_qty + open_orders_qty + lot) - befday_qty)`
- **BLOCK if**: `potential_daily_change > maxalw * 3 / 4`

**Quant Engine'de Karşılığı:**
```python
# runall_engine.py - _step_run_addnewpos()
#   ├─> StaticDataStore.get_all_symbols() → ALL symbols
#   ├─> PositionSnapshotAPI.get_position_snapshot() → Existing positions
#   ├─> MetricsSnapshotAPI.get_metrics_snapshot() → ALL symbols
#   ├─> addnewpos_decision_engine() → Basic filter
#   └─> jfin_engine.transform() → JFIN selection + lot distribution
```

---

### ADIM 7: Emirleri Kontrol Et

**Janall:**
```python
# main_window.py - runall_loop()
def runall_loop(self):
    # 1. DATA SOURCE: Hammer Pro Orders
    orders = self.hammer.get_orders()
    
    # 2. KONTROL
    # Açık emirler varsa, MAXALW check için kullanılır
    # ADDNEWPOS'ta open_orders_qty hesaplanırken kullanılır
```

**Veri Kaynakları:**
- **Hammer Pro**: `hammer.get_orders()`
- **Kullanım**: MAXALW check'te `open_orders_qty` olarak

**Quant Engine'de Karşılığı:**
```python
# OrderSnapshotAPI.get_order_snapshot()
#   └─> hammer_orders_service.get_orders() veya ibkr_connector.get_orders()
```

---

### ADIM 8: Tüm Emirleri İptal Et (Opsiyonel)

**Janall:**
```python
# main_window.py - runall_cancel_orders_and_restart()
def runall_cancel_orders_and_restart(self):
    # 1. DATA SOURCE: Hammer Pro Orders
    orders = self.hammer.get_orders()
    
    # 2. İPTAL ET
    for order in orders:
        self.hammer.cancel_order(order['order_id'])
    
    # 3. DÖNGÜYÜ YENİDEN BAŞLAT
    self.runall_loop()
```

**Quant Engine'de Karşılığı:**
```python
# ExecutionEngine.cancel_all_orders()
#   └─> hammer_execution_service.cancel_all_orders() veya ibkr_connector.cancel_all_orders()
```

---

### ADIM 9: Döngüyü Tekrarla

**Janall:**
```python
# main_window.py - runall_loop()
def runall_loop(self):
    # ... tüm adımlar ...
    
    # 9. 60 saniye bekle ve tekrarla
    self.after(60000, self.runall_loop)  # 60 saniye = 60000 ms
```

**Cycle Interval**: 60 saniye (sabit)

**Quant Engine'de Karşılığı:**
```python
# runall_engine.py - _cycle_loop()
async def _cycle_loop(self):
    while self.loop_running:
        # ... tüm adımlar ...
        await asyncio.sleep(self.cycle_interval)  # Default: 60 saniye
```

---

## 📊 VERİ KAYNAKLARI ÖZET TABLOSU

| Adım | Veri | Janall Kaynağı | Quant Engine Kaynağı |
|------|------|----------------|---------------------|
| **1. Pozisyonlar** | Positions | `hammer.get_positions()` | `PositionSnapshotAPI` |
| **2. Market Data** | bid/ask/last | `hammer.get_market_data()` | `DataFabric._live_data` |
| **2. Skorlar** | Fbtot, Final_BB, Final_FB | `calculate_scores()` → DataFrame | `DataFabric._derived_data` |
| **2. Static Data** | prev_close, MAXALW, GROUP | DataFrame (CSV) | `DataFabric._static_data` |
| **3. Exposure** | pot_total, pot_max | Take Profit Panel Tree | `ExposureCalculator` |
| **5. KARBOTU** | Fbtot, Ask Sell | DataFrame | `MetricsSnapshotAPI` |
| **5. REDUCEMORE** | Fbtot, Ask Sell | DataFrame | `MetricsSnapshotAPI` |
| **6. ADDNEWPOS** | ALL symbols | DataFrame | `StaticDataStore` |
| **6. ADDNEWPOS** | Final_BB, Final_FB | DataFrame | `DataFabric._derived_data` |
| **6. ADDNEWPOS** | befday_qty | CSV (`befham.csv`) | `BefDayTracker` veya CSV |
| **6. ADDNEWPOS** | current_qty | `hammer.get_positions()` | `PositionSnapshotAPI` |
| **6. ADDNEWPOS** | open_orders_qty | `hammer.get_orders()` | `OrderSnapshotAPI` |
| **7. Orders** | Open orders | `hammer.get_orders()` | `OrderSnapshotAPI` |

---

## 🎯 QUANT ENGINE'DE UYGULAMA

### Mevcut Durum

Quant Engine'de RUNALL yapısı **birebir** Janall ile eşleşiyor:

1. ✅ **Adım 1**: `_step_update_exposure()` → `PositionSnapshotAPI`
2. ✅ **Adım 2**: `DataFabric.get_fast_snapshot()` → Event-driven (Janall'dan daha iyi)
3. ✅ **Adım 3**: `ExposureCalculator.calculate_exposure()`
4. ✅ **Adım 4**: `_determine_exposure_mode()` → OFANSIF/DEFANSIF
5. ✅ **Adım 5**: `_step_run_karbotu()` veya `_step_run_reducemore()`
6. ✅ **Adım 6**: `_step_run_addnewpos()` → JFIN transformer
7. ✅ **Adım 7**: `OrderSnapshotAPI` (implicit)
8. ✅ **Adım 8**: `ExecutionEngine.cancel_all_orders()` (opsiyonel)
9. ✅ **Adım 9**: `_cycle_loop()` → 60 saniye interval

### Farklar ve İyileştirmeler

1. **Event-driven vs Polling**: Quant Engine event-driven (daha hızlı)
2. **Human-in-the-Loop**: Quant Engine proposal → intent → execution (daha güvenli)
3. **Multi-Account**: Quant Engine HAMMER + IBKR desteği (Janall sadece HAMMER)
4. **Async/Non-blocking**: Quant Engine async (UI donmaz)

---

## ✅ SONUÇ

Quant Engine'deki RUNALL yapısı **Janall ile birebir eşleşiyor**. Tüm veri kaynakları, koşullar ve karar mantığı aynı. Tek fark, Quant Engine'in daha modern bir mimari kullanması (event-driven, async, human-in-the-loop).





