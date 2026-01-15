# PSFALGO Data Flow - Detaylı Analiz Raporu

## 📋 Executive Summary

Bu rapor, **Janall** ve **Quant Engine** uygulamalarındaki PSFALGO sistemlerinin (KARBOTU, REDUCEMORE, ADDNEWPOS) data flow'unu çok detaylı bir şekilde karşılaştırmaktadır. Her bir algoritmanın hangi data source'lara baktığı, nasıl analiz ettiği, hangi koşulları kontrol ettiği ve emir gönderim onay penceresine nasıl geldiği adım adım açıklanmaktadır.

---

## 🎯 Genel Mimari Karşılaştırma

### Janall (Desktop - Tkinter)

```
┌─────────────────────────────────────────────────────────────┐
│                    JANALL PSFALGO FLOW                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [User Click] → KARBOTU / REDUCEMORE / ADDNEWPOS Button    │
│      │                                                      │
│      ├─> Take Profit Panel (Longs/Shorts)                 │
│      │      │                                                │
│      │      └─> DataFrame (self.df)                        │
│      │              │                                        │
│      │              ├─> Static: prev_close, FINAL_THG       │
│      │              ├─> Live: hammer.get_market_data()       │
│      │              │      │                                  │
│      │              │      └─> bid, ask, last              │
│      │              │                                        │
│      │              └─> Calculated: Fbtot, Ask Sell Pahalılık│
│      │                      │                                │
│      │                      └─> calculate_scores()          │
│      │                              │                        │
│      │                              └─> DataFrame'e yaz     │
│      │                                      │                │
│      │                                      └─> Filter      │
│      │                                              │        │
│      │                                              └─> Confirm Window│
│      │                                                      │
│      └─> Direct Order Execution (Hammer Pro API)          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Data Sources:**
1. **DataFrame (self.df)**: CSV'den yüklenen statik data
2. **hammer.get_market_data()**: Live market data (bid/ask/last)
3. **calculate_scores()**: Skorlar DataFrame'e yazılır
4. **Take Profit Panel Tree**: UI'dan pozisyonlar okunur

### Quant Engine (Web - FastAPI + React)

```
┌─────────────────────────────────────────────────────────────┐
│                 QUANT ENGINE PSFALGO FLOW                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [RUNALL Cycle] → Step 1: Update Exposure                 │
│      │                                                      │
│      ├─> PositionSnapshotAPI.get_position_snapshot()      │
│      │      │                                                │
│      │      ├─> HAMMER: hammer_positions_service           │
│      │      │   OR                                          │
│      │      └─> IBKR: ibkr_connector.get_positions()     │
│      │              │                                        │
│      │              └─> Enrich: Market Data (HAMMER)       │
│      │                      │                                │
│      │                      └─> DataFabric.get_fast_snapshot│
│      │                              │                        │
│      ├─> Step 2: Check Data Readiness                      │
│      │      │                                                │
│      │      └─> DataReadinessChecker                        │
│      │              │                                        │
│      │              ├─> L1 prices (DataFabric)              │
│      │              ├─> prev_close (DataFabric)              │
│      │              └─> Fbtot (DataFabric)                  │
│      │                                                      │
│      ├─> Step 3: KARBOTU / REDUCEMORE                      │
│      │      │                                                │
│      │      ├─> _prepare_karbotu_request()                 │
│      │      │      │                                          │
│      │      │      ├─> PositionSnapshotAPI                  │
│      │      │      └─> MetricsSnapshotAPI                   │
│      │      │              │                                  │
│      │      │              └─> MarketSnapshotStore          │
│      │      │                      │                          │
│      │      │                      ├─> DataFabric           │
│      │      │                      ├─> StaticDataStore       │
│      │      │                      └─> PricingOverlayEngine │
│      │      │                              │                  │
│      │      │                              └─> FastScoreCalculator│
│      │      │                                                      │
│      │      └─> karbotu_decision_engine()                  │
│      │              │                                        │
│      │              └─> ProposalEngine → ProposalStore     │
│      │                      │                                │
│      │                      └─> ExecutionEngine → IntentStore│
│      │                              │                        │
│      │                              └─> UI (WebSocket)      │
│      │                                                      │
│      └─> Step 4: ADDNEWPOS                                 │
│              │                                                │
│              ├─> _prepare_addnewpos_request()             │
│              │      │                                          │
│              │      ├─> StaticDataStore.get_all_symbols()   │
│              │      └─> MetricsSnapshotAPI                  │
│              │              │                                  │
│              │              └─> (same as KARBOTU)           │
│              │                                                      │
│              └─> addnewpos_decision_engine()               │
│                      │                                        │
│                      └─> JFIN Engine → Proposals           │
│                              │                                │
│                              └─> UI (WebSocket)            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Data Sources:**
1. **DataFabric**: Single Source of Truth (L1 + Static + Derived)
2. **PositionSnapshotAPI**: Positions (HAMMER or IBKR)
3. **MetricsSnapshotAPI**: Aggregated metrics (MarketSnapshotStore)
4. **MarketSnapshotStore**: Validated snapshots
5. **StaticDataStore**: CSV static data
6. **PricingOverlayEngine**: Final scores (800 katsayısı)

---

## 🔴 1. KARBOTU (Take Profit) - Detaylı Data Flow

### Janall KARBOTU Flow

#### Data Sources

```python
# main_window.py - karbotu_step_2_fbtot_lt_110()
def karbotu_step_2_fbtot_lt_110(self):
    # 1. DATA SOURCE: Take Profit Longs Panel (UI Tree)
    for item in self.take_profit_longs_panel.tree.get_children():
        values = self.take_profit_longs_panel.tree.item(item)['values']
        
        # 2. DATA SOURCE: DataFrame (self.df) - Static + Calculated
        symbol = values[1]  # PREF IBKR
        fbtot_str = values[5]  # Fbtot kolonu (DataFrame'den)
        ask_sell_pahalilik_str = values[8]  # Ask Sell Pahalılık (DataFrame'den)
        qty = float(values[2])  # Quantity (Hammer positions)
        
        # 3. DATA SOURCE: Live Market Data (Hammer)
        # NOT directly used in filter, but used for order price
        market_data = self.hammer.get_market_data(symbol)
        bid = market_data.get('bid')
        ask = market_data.get('ask')
        last = market_data.get('last')
        
        # 4. FILTER CONDITIONS
        if fbtot < 1.10 and ask_sell_pahalilik > -0.10:
            # 5. LOT CALCULATION
            lot_percentage = 50  # Step 2: 50%
            calculated_lot = qty * (lot_percentage / 100)
            
            # 6. CONFIRMATION WINDOW
            self.karbotu_select_positions_and_confirm(
                filtered_positions, 
                "Ask Sell", 
                50, 
                "Adım 2"
            )
```

**Data Flow:**
```
1. Take Profit Panel Tree (UI)
   ↓
2. DataFrame (self.df) → Fbtot, Ask Sell Pahalılık
   ↓
3. Filter: fbtot < 1.10 AND ask_sell_pahalilik > -0.10
   ↓
4. Lot Calculation: qty * 50%
   ↓
5. Confirmation Window (karbotu_show_confirmation_window)
   ↓
6. User Approval → Direct Order (Hammer Pro API)
```

**Data Source Details:**

| Data Field | Source | Location | Update Frequency |
|------------|--------|----------|------------------|
| **Fbtot** | DataFrame (self.df) | `self.df.at[symbol, 'Fbtot']` | Polling (3s) - `update_scores_with_market_data()` |
| **Ask Sell Pahalılık** | DataFrame (self.df) | `self.df.at[symbol, 'Ask Sell Pahalılık']` | Polling (3s) - `calculate_scores()` |
| **Quantity** | Take Profit Panel Tree | `values[2]` | Real-time (Hammer positions) |
| **Bid/Ask/Last** | Hammer Pro | `hammer.get_market_data(symbol)` | Real-time (L1Update) |
| **prev_close** | DataFrame (self.df) | `self.df.at[symbol, 'prev_close']` | CSV (startup) |
| **FINAL_THG** | DataFrame (self.df) | `self.df.at[symbol, 'FINAL_THG']` | CSV (startup) |

**Filter Conditions (Step 2):**
- `fbtot < 1.10`
- `ask_sell_pahalilik > -0.10`
- `qty >= 100` (minimum lot filter)
- `fbtot != 0.0` (exclude N/A)

**Lot Calculation:**
- `calculated_lot = qty * 0.50` (50%)
- Rounded to nearest 100 (100, 200, 300, ...)

**Order Execution:**
- Order Type: `ASK_SELL`
- Price: `ask` (from `hammer.get_market_data()`)
- Direct execution via Hammer Pro API (no intermediate store)

---

### Quant Engine KARBOTU Flow

#### Data Sources

```python
# runall_engine.py - _step_run_karbotu()
async def _step_run_karbotu(self):
    # 1. PREPARE REQUEST
    request = await self._prepare_karbotu_request()
    #     ↓
    #     ├─> PositionSnapshotAPI.get_position_snapshot()
    #     │      │
    #     │      ├─> HAMMER: hammer_positions_service.get_positions()
    #     │      │   OR
    #     │      └─> IBKR: ibkr_connector.get_positions()
    #     │              │
    #     │              └─> Enrich: DataFabric.get_fast_snapshot()
    #     │                      │
    #     │                      ├─> _live_data (bid, ask, last)
    #     │                      ├─> _static_data (prev_close, FINAL_THG)
    #     │                      └─> _derived_data (Fbtot, Ask Sell Pahalılık)
    #     │
    #     └─> MetricsSnapshotAPI.get_metrics_snapshot()
    #             │
    #             └─> MarketSnapshotStore.get_current_snapshot()
    #                     │
    #                     ├─> DataFabric.get_fast_snapshot()
    #                     ├─> StaticDataStore.get_static_data()
    #                     └─> PricingOverlayEngine.get_overlay_scores()
    #                             │
    #                             └─> FastScoreCalculator.compute_fast_scores()
    
    # 2. RUN DECISION ENGINE
    result = await karbotu_decision_engine(request)
    #     ↓
    #     └─> karbotu_engine.py - karbotu_decision_engine()
    #             │
    #             ├─> GORT Filter (LONGS)
    #             │      │
    #             │      ├─> Check: metric.gort > -1
    #             │      └─> Check: metric.ask_sell_pahalilik > -0.05
    #             │
    #             ├─> Step 2-7 (LONGS)
    #             │      │
    #             │      ├─> Step 2: fbtot < 1.10, ask_sell > -0.10 → 50%
    #             │      ├─> Step 3: fbtot 1.11-1.45, ask_sell -0.05 to +0.04 → 25%
    #             │      ├─> Step 4: fbtot 1.11-1.45, ask_sell > +0.05 → 50%
    #             │      ├─> Step 5: fbtot 1.46-1.85, ask_sell +0.05 to +0.10 → 25%
    #             │      ├─> Step 6: fbtot 1.46-1.85, ask_sell > +0.10 → 50%
    #             │      └─> Step 7: fbtot 1.86-2.10, ask_sell > +0.20 → 25%
    #             │
    #             └─> Step 9-13 (SHORTS)
    #                     │
    #                     ├─> Step 9: sfstot > 1.70 → 50%
    #                     ├─> Step 10: sfstot 1.40-1.69, bid_buy +0.05 to -0.04 → 25%
    #                     ├─> Step 11: sfstot 1.40-1.69, bid_buy < -0.05 → 50%
    #                     ├─> Step 12: sfstot 1.10-1.39, bid_buy +0.05 to -0.04 → 25%
    #                     └─> Step 13: sfstot 1.10-1.39, bid_buy < -0.05 → 50%
    
    # 3. GENERATE PROPOSALS
    proposals = await proposal_engine.process_decision_response(result)
    #     ↓
    #     └─> ProposalStore.add_proposal()
    #             │
    #             └─> WebSocket Broadcast → UI
    #                     │
    #                     └─> User Approval → IntentStore → Execution
```

**Data Flow:**
```
1. RUNALL Cycle → _step_run_karbotu()
   ↓
2. _prepare_karbotu_request()
   ↓
   ├─> PositionSnapshotAPI.get_position_snapshot()
   │      │
   │      ├─> HAMMER/IBKR: Get positions
   │      └─> DataFabric.get_fast_snapshot(): Enrich with market data
   │
   └─> MetricsSnapshotAPI.get_metrics_snapshot()
          │
          └─> MarketSnapshotStore.get_current_snapshot()
                  │
                  ├─> DataFabric.get_fast_snapshot()
                  │      │
                  │      ├─> _live_data: bid, ask, last
                  │      ├─> _static_data: prev_close, FINAL_THG, MAXALW
                  │      └─> _derived_data: Fbtot, Ask Sell Pahalılık, GORT
                  │
                  └─> PricingOverlayEngine.get_overlay_scores()
                          │
                          └─> FastScoreCalculator.compute_fast_scores()
                                  │
                                  └─> Janall formulas (800 katsayısı)
   ↓
3. karbotu_decision_engine(request)
   ↓
   ├─> GORT Filter
   │      │
   │      ├─> metric.gort > -1 (from MetricsSnapshotAPI)
   │      └─> metric.ask_sell_pahalilik > -0.05 (from MetricsSnapshotAPI)
   │
   └─> Step Processing
          │
          ├─> Filter: fbtot < 1.10, ask_sell > -0.10
          ├─> Lot: qty * 0.50 (50%)
          └─> Decision: SELL, ASK_SELL, price=metric.ask
   ↓
4. ProposalEngine.process_decision_response()
   ↓
   └─> ProposalStore.add_proposal()
          │
          └─> WebSocket Broadcast → UI
                  │
                  └─> User Approval → IntentStore → ExecutionEngine
```

**Data Source Details:**

| Data Field | Source | Location | Update Frequency |
|------------|--------|----------|------------------|
| **Positions** | PositionSnapshotAPI | `hammer_positions_service` or `ibkr_connector` | Real-time (on request) |
| **bid/ask/last** | DataFabric._live_data | `DataFabric.get_fast_snapshot()` | Event-driven (L1Update) |
| **prev_close** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |
| **Fbtot** | DataFabric._derived_data | `FastScoreCalculator.compute_fast_scores()` | Event-driven (on L1Update) |
| **Ask Sell Pahalılık** | DataFabric._derived_data | `FastScoreCalculator.compute_fast_scores()` | Event-driven (on L1Update) |
| **GORT** | DataFabric._derived_data | `JanallMetricsEngine.compute_group_metrics()` | Event-driven (on L1Update) |
| **FINAL_THG** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |
| **MAXALW** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |

**Filter Conditions (Step 2 - Same as Janall):**
- `fbtot < 1.10` (from `metric.fbtot`)
- `ask_sell_pahalilik > -0.10` (from `metric.ask_sell_pahalilik`)
- `qty >= 100` (from `position.qty`)
- `fbtot != 0.0` (exclude N/A)
- Cooldown check (from `cooldown_manager`)

**Lot Calculation:**
- `calculated_lot = position.qty * 0.50` (50%)
- Rounded to nearest 100 (same as Janall)

**Order Execution:**
- Order Type: `ASK_SELL`
- Price: `metric.ask` (from MetricsSnapshotAPI)
- **Human-in-the-Loop**: Proposal → IntentStore → User Approval → ExecutionEngine

---

## 🔴 2. REDUCEMORE - Detaylı Data Flow

### Janall REDUCEMORE Flow

#### Data Sources

```python
# main_window.py - reduce_more_step_2_fbtot_lt_110()
def reduce_more_step_2_fbtot_lt_110(self):
    # 1. DATA SOURCE: Take Profit Longs Panel (REDUCEMORE version)
    for item in self.take_profit_longs_panel_reducemore.tree.get_children():
        values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
        
        # 2. DATA SOURCE: DataFrame (self.df) - Static + Calculated
        symbol = values[1]
        fbtot_str = values[5]  # Fbtot (DataFrame)
        ask_sell_pahalilik_str = values[8]  # Ask Sell Pahalılık (DataFrame)
        qty = float(values[2])  # Quantity (Hammer positions)
        
        # 3. FILTER CONDITIONS (DIFFERENT FROM KARBOTU)
        if fbtot < 1.10 and ask_sell_pahalilik > -0.20:  # -0.20 (not -0.10)
            # 4. LOT CALCULATION (DIFFERENT FROM KARBOTU)
            lot_percentage = 100  # Step 2: 100% (not 50%)
            calculated_lot = qty * (lot_percentage / 100)
            
            # 5. CONFIRMATION WINDOW
            self.reduce_more_select_positions_and_confirm(
                filtered_positions, 
                "Ask Sell", 
                100, 
                "Adım 2"
            )
```

**Data Flow:**
```
1. Take Profit Panel Tree (REDUCEMORE version)
   ↓
2. DataFrame (self.df) → Fbtot, Ask Sell Pahalılık
   ↓
3. Filter: fbtot < 1.10 AND ask_sell_pahalilik > -0.20
   ↓
4. Lot Calculation: qty * 100% (FULL POSITION)
   ↓
5. Confirmation Window
   ↓
6. User Approval → Direct Order (Hammer Pro API)
```

**Key Differences from KARBOTU:**
- **Filter Threshold**: `ask_sell_pahalilik > -0.20` (vs `-0.10` in KARBOTU)
- **Lot Percentage**: `100%` (vs `50%` in KARBOTU Step 2)
- **Purpose**: More aggressive position reduction

**Data Source Details (Same as KARBOTU):**

| Data Field | Source | Location | Update Frequency |
|------------|--------|----------|------------------|
| **Fbtot** | DataFrame (self.df) | `self.df.at[symbol, 'Fbtot']` | Polling (3s) |
| **Ask Sell Pahalılık** | DataFrame (self.df) | `self.df.at[symbol, 'Ask Sell Pahalılık']` | Polling (3s) |
| **Quantity** | Take Profit Panel Tree | `values[2]` | Real-time |
| **Bid/Ask/Last** | Hammer Pro | `hammer.get_market_data(symbol)` | Real-time |

---

### Quant Engine REDUCEMORE Flow

#### Data Sources

```python
# runall_engine.py - _step_run_reducemore()
async def _step_run_reducemore(self):
    # 1. PREPARE REQUEST (Same structure as KARBOTU)
    request = await self._prepare_reducemore_request()
    #     ↓
    #     ├─> PositionSnapshotAPI.get_position_snapshot()
    #     │      └─> ALL positions (longs + shorts)
    #     │
    #     └─> MetricsSnapshotAPI.get_metrics_snapshot()
    #             └─> (Same as KARBOTU)
    
    # 2. RUN DECISION ENGINE
    result = await reducemore_decision_engine(request)
    #     ↓
    #     └─> reducemore_engine.py - reducemore_decision_engine()
    #             │
    #             ├─> Step 2: fbtot < 1.10, ask_sell > -0.20 → 100%
    #             ├─> Step 3: fbtot 1.11-1.45, ask_sell -0.08 to +0.01 → 75%
    #             ├─> Step 4: fbtot 1.11-1.45, ask_sell > +0.01 → 100%
    #             ├─> Step 5: fbtot 1.46-1.85, ask_sell +0.05 to +0.10 → 75%
    #             ├─> Step 6: fbtot 1.46-1.85, ask_sell > +0.10 → 100%
    #             └─> Step 7: fbtot 1.86-2.10, ask_sell > +0.20 → 75%
```

**Data Flow:**
```
1. RUNALL Cycle → _step_run_reducemore()
   ↓
2. _prepare_reducemore_request()
   ↓
   ├─> PositionSnapshotAPI.get_position_snapshot()
   │      └─> ALL positions (longs + shorts)
   │
   └─> MetricsSnapshotAPI.get_metrics_snapshot()
          └─> (Same data sources as KARBOTU)
   ↓
3. reducemore_decision_engine(request)
   ↓
   ├─> Step 2: fbtot < 1.10, ask_sell > -0.20 → 100%
   └─> (Other steps with different thresholds)
   ↓
4. ProposalEngine → ProposalStore → UI
```

**Key Differences from KARBOTU:**
- **Filter Threshold**: `ask_sell_pahalilik > -0.20` (vs `-0.10` in KARBOTU)
- **Lot Percentage**: `100%` in Step 2 (vs `50%` in KARBOTU)
- **Positions**: ALL positions (longs + shorts) vs LONGS only in KARBOTU

**Data Source Details (Same as KARBOTU):**

| Data Field | Source | Location | Update Frequency |
|------------|--------|----------|------------------|
| **Positions** | PositionSnapshotAPI | `hammer_positions_service` or `ibkr_connector` | Real-time |
| **Fbtot** | DataFabric._derived_data | `FastScoreCalculator` | Event-driven |
| **Ask Sell Pahalılık** | DataFabric._derived_data | `FastScoreCalculator` | Event-driven |

---

## 🔴 3. ADDNEWPOS (Add New Position) - Detaylı Data Flow

### Janall ADDNEWPOS Flow

#### Data Sources

```python
# final_thg_lot_distributor.py - JFIN Transformer
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
                # - ...
                
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

**Data Flow:**
```
1. User Click → ADDNEWPOS Button
   ↓
2. FinalThgLotDistributor.distribute_lots()
   ↓
   ├─> DataFrame (self.df) → ALL symbols
   │      │
   │      ├─> Static: prev_close, FINAL_THG, MAXALW, GROUP, CGRUP
   │      ├─> Calculated: Final_BB, Final_FB, Fbtot, Bid Buy Ucuzluk
   │      └─> Live: hammer.get_market_data() → bid, ask, last
   │
   └─> Filter: bid_buy_ucuzluk < -0.06 AND fbtot > 1.10
          │
          └─> JFIN Selection
                  │
                  ├─> Group-based: Top X% by Final_FB_skor
                  ├─> Then: Top X% by Final_BB_skor
                  └─> Alpha-weighted lot distribution
          │
          └─> Portfolio Rules → Lot Calculation
          │
          └─> MAXALW Check
                  │
                  ├─> befday_qty (CSV: befham.csv or befibgun.csv)
                  ├─> current_qty (Hammer positions)
                  ├─> open_orders_qty (Hammer orders)
                  └─> max_change_limit = maxalw * 3 / 4
          │
          └─> Confirmation Window
                  │
                  └─> User Approval → Direct Order (Hammer Pro API)
```

**Data Source Details:**

| Data Field | Source | Location | Update Frequency |
|------------|--------|----------|------------------|
| **All Symbols** | DataFrame (self.df) | `self.df['PREF IBKR'].tolist()` | CSV (startup) |
| **bid/ask/last** | Hammer Pro | `hammer.get_market_data(symbol)` | Real-time (L1Update) |
| **Final_BB_skor** | DataFrame (self.df) | `self.df.at[symbol, 'Final BB']` | Polling (3s) - `calculate_scores()` |
| **Final_FB_skor** | DataFrame (self.df) | `self.df.at[symbol, 'Final FB']` | Polling (3s) - `calculate_scores()` |
| **Fbtot** | DataFrame (self.df) | `self.df.at[symbol, 'Fbtot']` | Polling (3s) - `update_scores_with_market_data()` |
| **Bid Buy Ucuzluk** | DataFrame (self.df) | `self.df.at[symbol, 'Bid Buy Ucuzluk']` | Polling (3s) - `calculate_scores()` |
| **SMA63 chg** | DataFrame (self.df) | `self.df.at[symbol, 'SMA63 chg']` | CSV (startup) |
| **GORT** | DataFrame (self.df) | `self.df.at[symbol, 'GORT']` | Polling (3s) - `update_scores_with_market_data()` |
| **MAXALW** | DataFrame (self.df) | `self.df.at[symbol, 'MAXALW']` | CSV (startup) |
| **GROUP** | DataFrame (self.df) | `self.df.at[symbol, 'GROUP']` | CSV (startup) |
| **CGRUP** | DataFrame (self.df) | `self.df.at[symbol, 'CGRUP']` | CSV (startup) |
| **befday_qty** | CSV | `befham.csv` or `befibgun.csv` | Daily (startup) |
| **current_qty** | Hammer Pro | `hammer.get_positions()` | Real-time |
| **open_orders_qty** | Hammer Pro | `hammer.get_orders()` | Real-time |

**Filter Conditions (AddLong):**
- `bid_buy_ucuzluk < -0.06` (stock is at least 6 cents cheaper than benchmark)
- `fbtot > 1.10` (ranked in top of group)
- `sma63_chg < threshold` (optional - underperforming)
- `gort < threshold` (optional - underperforming vs group)
- `spread < 0.25` (liquidity check)
- `AVG_ADV > 100.0` (liquidity check)

**JFIN Selection Logic:**
1. **Group Selection**: For each group:
   - Sort by `Final_FB_skor` (descending)
   - Take top X% (e.g., 50%)
   - Then sort by `Final_BB_skor` (descending)
   - Take top X% (e.g., 50%)
2. **Lot Distribution**: Alpha-weighted (Final_BB_skor based)
3. **MAXALW Limit**: `max_change_limit = maxalw * 3 / 4`

**Lot Calculation (Portfolio Rules):**
- `< 1%`: `min(MAXALW × 0.50, Portfolio × 5%)`
- `1-3%`: `min(MAXALW × 0.40, Portfolio × 4%)`
- `3-5%`: `min(MAXALW × 0.30, Portfolio × 3%)`
- `5-7%`: `min(MAXALW × 0.20, Portfolio × 2%)`
- `7-10%`: `min(MAXALW × 0.10, Portfolio × 1.5%)`
- `>= 10%`: `min(MAXALW × 0.05, Portfolio × 1%)`

**MAXALW Check:**
- `befday_qty`: Loaded from `befham.csv` (Hammer) or `befibgun.csv` (IBKR GUN) or `befibped.csv` (IBKR PED)
- `current_qty`: From `hammer.get_positions()`
- `open_orders_qty`: From `hammer.get_orders()`
- `potential_daily_change = abs((current_qty + open_orders_qty + lot) - befday_qty)`
- If `potential_daily_change > maxalw * 3 / 4`: **BLOCK ORDER**

---

### Quant Engine ADDNEWPOS Flow

#### Data Sources

```python
# runall_engine.py - _step_run_addnewpos()
async def _step_run_addnewpos(self):
    # 1. PREPARE REQUEST
    request = await self._prepare_addnewpos_request()
    #     ↓
    #     ├─> StaticDataStore.get_all_symbols()
    #     │      └─> ALL symbols from CSV (440 symbols)
    #     │
    #     ├─> PositionSnapshotAPI.get_position_snapshot()
    #     │      └─> Existing positions (for exclusion)
    #     │
    #     └─> MetricsSnapshotAPI.get_metrics_snapshot()
    #             └─> ALL symbols (same data sources as KARBOTU)
    
    # 2. RUN ADDNEWPOS BASIC FILTER
    result = await addnewpos_decision_engine(request)
    #     ↓
    #     └─> addnewpos_engine.py - addnewpos_decision_engine()
    #             │
    #             ├─> Filter: bid_buy_ucuzluk < -0.06, fbtot > 1.10
    #             ├─> Filter: sma63_chg < threshold (optional)
    #             ├─> Filter: gort < threshold (optional)
    #             ├─> Filter: spread < 0.25
    #             ├─> Filter: AVG_ADV > 100.0
    #             └─> Portfolio Rules → Lot Calculation
    
    # 3. RUN JFIN TRANSFORMER
    jfin_result = await jfin_engine.transform_candidates(result.decisions)
    #     ↓
    #     └─> jfin_engine.py - transform_candidates()
    #             │
    #             ├─> Group-based selection
    #             │      │
    #             │      ├─> Sort by Final_FB_skor (descending)
    #             │      ├─> Take top X% per group
    #             │      ├─> Sort by Final_BB_skor (descending)
    #             │      └─> Take top X% per group
    #             │
    #             ├─> Alpha-weighted lot distribution
    #             └─> MAXALW and BEFDAY limits
    
    # 4. GENERATE PROPOSALS
    proposals = await proposal_engine.process_jfin_intents(jfin_result)
    #     ↓
    #     └─> ProposalStore.add_proposal()
    #             │
    #             └─> WebSocket Broadcast → UI
```

**Data Flow:**
```
1. RUNALL Cycle → _step_run_addnewpos()
   ↓
2. _prepare_addnewpos_request()
   ↓
   ├─> StaticDataStore.get_all_symbols()
   │      └─> ALL symbols from CSV (440)
   │
   ├─> PositionSnapshotAPI.get_position_snapshot()
   │      └─> Existing positions (for exclusion)
   │
   └─> MetricsSnapshotAPI.get_metrics_snapshot()
          └─> ALL symbols
                  │
                  └─> MarketSnapshotStore.get_current_snapshot()
                          │
                          ├─> DataFabric.get_fast_snapshot()
                          │      │
                          │      ├─> _live_data: bid, ask, last
                          │      ├─> _static_data: prev_close, FINAL_THG, MAXALW, GROUP, CGRUP
                          │      └─> _derived_data: Fbtot, Bid Buy Ucuzluk, Final_BB_skor, Final_FB_skor
                          │
                          └─> PricingOverlayEngine.get_overlay_scores()
                                  │
                                  └─> FastScoreCalculator.compute_fast_scores()
                                          │
                                          └─> Janall formulas (800 katsayısı)
   ↓
3. addnewpos_decision_engine(request)
   ↓
   ├─> Filter: bid_buy_ucuzluk < -0.06, fbtot > 1.10
   ├─> Filter: sma63_chg < threshold (optional)
   ├─> Filter: gort < threshold (optional)
   ├─> Filter: spread < 0.25
   ├─> Filter: AVG_ADV > 100.0
   └─> Portfolio Rules → Lot Calculation
   ↓
4. JFIN Engine.transform_candidates()
   ↓
   ├─> Group-based selection
   │      │
   │      ├─> Sort by Final_FB_skor (descending)
   │      ├─> Take top X% per group
   │      ├─> Sort by Final_BB_skor (descending)
   │      └─> Take top X% per group
   │
   ├─> Alpha-weighted lot distribution
   └─> MAXALW Check
          │
          ├─> befday_qty (ShadowPositionStore or CSV)
          ├─> current_qty (PositionSnapshotAPI)
          ├─> open_orders_qty (OrderSnapshotAPI)
          └─> max_change_limit = maxalw * 3 / 4
   ↓
5. ProposalEngine → ProposalStore → UI
```

**Data Source Details:**

| Data Field | Source | Location | Update Frequency |
|------------|--------|----------|------------------|
| **All Symbols** | StaticDataStore | `static_store.get_all_symbols()` | Startup (CSV) |
| **bid/ask/last** | DataFabric._live_data | `DataFabric.get_fast_snapshot()` | Event-driven (L1Update) |
| **Final_BB_skor** | DataFabric._derived_data | `FastScoreCalculator.compute_fast_scores()` | Event-driven (on L1Update) |
| **Final_FB_skor** | DataFabric._derived_data | `FastScoreCalculator.compute_fast_scores()` | Event-driven (on L1Update) |
| **Fbtot** | DataFabric._derived_data | `FastScoreCalculator.compute_fast_scores()` | Event-driven (on L1Update) |
| **Bid Buy Ucuzluk** | DataFabric._derived_data | `FastScoreCalculator.compute_fast_scores()` | Event-driven (on L1Update) |
| **SMA63 chg** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |
| **GORT** | DataFabric._derived_data | `JanallMetricsEngine.compute_group_metrics()` | Event-driven (on L1Update) |
| **MAXALW** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |
| **GROUP** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |
| **CGRUP** | DataFabric._static_data | `DataFabric.get_fast_snapshot()` | Startup (CSV) |
| **befday_qty** | ShadowPositionStore or CSV | `shadow_store.get_befday_qty()` or CSV | Daily (startup) |
| **current_qty** | PositionSnapshotAPI | `position_api.get_position_snapshot()` | Real-time |
| **open_orders_qty** | OrderSnapshotAPI | `order_api.get_order_snapshot()` | Real-time |

**Filter Conditions (AddLong - Same as Janall):**
- `bid_buy_ucuzluk < -0.06`
- `fbtot > 1.10`
- `sma63_chg < threshold` (optional)
- `gort < threshold` (optional)
- `spread < 0.25`
- `AVG_ADV > 100.0`
- `existing_qty < max_lot_per_symbol`

**JFIN Selection Logic (Same as Janall):**
1. **Group Selection**: For each group:
   - Sort by `Final_FB_skor` (descending)
   - Take top X% (configurable, default 50%)
   - Then sort by `Final_BB_skor` (descending)
   - Take top X% (configurable, default 50%)
2. **Lot Distribution**: Alpha-weighted (Final_BB_skor based)
3. **MAXALW Limit**: `max_change_limit = maxalw * 3 / 4`

**Lot Calculation (Portfolio Rules - Same as Janall):**
- `< 1%`: `min(MAXALW × 0.50, Portfolio × 5%)`
- `1-3%`: `min(MAXALW × 0.40, Portfolio × 4%)`
- `3-5%`: `min(MAXALW × 0.30, Portfolio × 3%)`
- `5-7%`: `min(MAXALW × 0.20, Portfolio × 2%)`
- `7-10%`: `min(MAXALW × 0.10, Portfolio × 1.5%)`
- `>= 10%`: `min(MAXALW × 0.05, Portfolio × 1%)`

**MAXALW Check (Same as Janall):**
- `befday_qty`: From `ShadowPositionStore` (updated from CSV on startup) or CSV directly
- `current_qty`: From `PositionSnapshotAPI`
- `open_orders_qty`: From `OrderSnapshotAPI`
- `potential_daily_change = abs((current_qty + open_orders_qty + lot) - befday_qty)`
- If `potential_daily_change > maxalw * 3 / 4`: **BLOCK ORDER** (rejected intent)

---

## 📊 Data Source Karşılaştırması

### Janall Data Sources

| Data Type | Source | Location | Update Method |
|-----------|--------|----------|---------------|
| **Static Data** | CSV (janalldata.csv) | `self.df` (DataFrame) | Startup (pd.read_csv) |
| **Live Market Data** | Hammer Pro | `hammer.get_market_data(symbol)` | Real-time (L1Update) |
| **Calculated Scores** | DataFrame | `self.df.at[symbol, 'Fbtot']` | Polling (3s) - `calculate_scores()` |
| **Positions** | Hammer Pro | `hammer.get_positions()` | Real-time |
| **Orders** | Hammer Pro | `hammer.get_orders()` | Real-time |
| **befday_qty** | CSV | `befham.csv` or `befibgun.csv` | Daily (startup) |
| **Group Info** | CSV | `ssfinek*.csv` files | Startup |

### Quant Engine Data Sources

| Data Type | Source | Location | Update Method |
|-----------|--------|----------|---------------|
| **Static Data** | CSV (janalldata.csv) | `DataFabric._static_data` | Startup (load_static_data) |
| **Live Market Data** | Hammer Pro → DataFabric | `DataFabric._live_data` | Event-driven (L1Update) |
| **Calculated Scores** | DataFabric | `DataFabric._derived_data` | Event-driven (on L1Update) |
| **Positions** | HAMMER or IBKR | `PositionSnapshotAPI` | Real-time (on request) |
| **Orders** | HAMMER or IBKR | `OrderSnapshotAPI` | Real-time (on request) |
| **befday_qty** | ShadowPositionStore or CSV | `shadow_store.get_befday_qty()` | Daily (startup) |
| **Group Info** | CSV → DataFabric | `DataFabric._static_data['GROUP']` | Startup |

---

## 🔄 Execution Flow Karşılaştırması

### Janall Execution Flow

```
1. User Click → Algorithm Button
   ↓
2. Filter Positions (DataFrame + Hammer)
   ↓
3. Calculate Lot (Percentage-based)
   ↓
4. Show Confirmation Window
   ↓
5. User Approval
   ↓
6. Direct Order Execution (Hammer Pro API)
   ↓
7. Log Activity
```

**Characteristics:**
- **Synchronous**: UI thread'de çalışır
- **Direct Execution**: Onay sonrası direkt emir gönderilir
- **No Intermediate Store**: Proposal/Intent store yok
- **Blocking**: UI donabilir (büyük işlemlerde)

### Quant Engine Execution Flow

```
1. RUNALL Cycle → Algorithm Step
   ↓
2. Prepare Request (PositionSnapshotAPI + MetricsSnapshotAPI)
   ↓
3. Decision Engine (Filter + Lot Calculation)
   ↓
4. ProposalEngine → ProposalStore
   ↓
5. WebSocket Broadcast → UI
   ↓
6. User Approval (UI)
   ↓
7. IntentStore.add_intent()
   ↓
8. ExecutionEngine.process_intent()
   ↓
9. Order Execution (HAMMER or IBKR)
   ↓
10. Log Activity
```

**Characteristics:**
- **Asynchronous**: Async/await ile non-blocking
- **Human-in-the-Loop**: Proposal → Intent → Execution
- **Intermediate Stores**: ProposalStore, IntentStore
- **Non-Blocking**: UI asla donmaz

---

## 🎯 Kritik Farklar ve Önemli Noktalar

### 1. Data Source Birliği

**Janall:**
- Tek kaynak: `self.df` (DataFrame)
- Live data: `hammer.get_market_data()` (cache'den okur)
- Skorlar: DataFrame'e yazılır, oradan okunur

**Quant Engine:**
- Tek kaynak: `DataFabric.get_fast_snapshot()`
- Live data: `DataFabric._live_data` (event-driven)
- Skorlar: `DataFabric._derived_data` (event-driven)

### 2. Update Frequency

**Janall:**
- Polling: 3 saniyede bir tüm tablo güncellenir
- Skorlar: Her 3 saniyede yeniden hesaplanır

**Quant Engine:**
- Event-driven: L1Update geldiğinde anında güncellenir
- Skorlar: Sadece değişen symbol'ler için hesaplanır

### 3. Position Source

**Janall:**
- Sadece HAMMER: `hammer.get_positions()`

**Quant Engine:**
- HAMMER veya IBKR: `PositionSnapshotAPI` (account mode'a göre)
- Market data: Her zaman HAMMER'dan (DataFabric)

### 4. Execution Model

**Janall:**
- Direct: Onay sonrası direkt emir gönderilir
- No intermediate store

**Quant Engine:**
- Human-in-the-Loop: Proposal → Intent → Execution
- ProposalStore, IntentStore intermediate stores

### 5. MAXALW Check

**Janall:**
- `befday_qty`: CSV'den okunur (`befham.csv` veya `befibgun.csv`)
- `current_qty`: `hammer.get_positions()`
- `open_orders_qty`: `hammer.get_orders()`

**Quant Engine:**
- `befday_qty`: `ShadowPositionStore` veya CSV
- `current_qty`: `PositionSnapshotAPI`
- `open_orders_qty`: `OrderSnapshotAPI`

---

## 📝 Özet: Data Source Mapping

### KARBOTU Data Sources

| Data Field | Janall Source | Quant Engine Source |
|------------|---------------|---------------------|
| **Positions** | Take Profit Panel Tree | PositionSnapshotAPI |
| **Fbtot** | DataFrame (self.df) | DataFabric._derived_data |
| **Ask Sell Pahalılık** | DataFrame (self.df) | DataFabric._derived_data |
| **GORT** | DataFrame (self.df) | DataFabric._derived_data |
| **bid/ask/last** | hammer.get_market_data() | DataFabric._live_data |
| **prev_close** | DataFrame (self.df) | DataFabric._static_data |
| **FINAL_THG** | DataFrame (self.df) | DataFabric._static_data |

### REDUCEMORE Data Sources

| Data Field | Janall Source | Quant Engine Source |
|------------|---------------|---------------------|
| **Positions** | Take Profit Panel Tree (REDUCEMORE) | PositionSnapshotAPI (ALL) |
| **Fbtot** | DataFrame (self.df) | DataFabric._derived_data |
| **Ask Sell Pahalılık** | DataFrame (self.df) | DataFabric._derived_data |
| **bid/ask/last** | hammer.get_market_data() | DataFabric._live_data |

### ADDNEWPOS Data Sources

| Data Field | Janall Source | Quant Engine Source |
|------------|---------------|---------------------|
| **All Symbols** | DataFrame (self.df) | StaticDataStore.get_all_symbols() |
| **Final_BB_skor** | DataFrame (self.df) | DataFabric._derived_data |
| **Final_FB_skor** | DataFrame (self.df) | DataFabric._derived_data |
| **Fbtot** | DataFrame (self.df) | DataFabric._derived_data |
| **Bid Buy Ucuzluk** | DataFrame (self.df) | DataFabric._derived_data |
| **SMA63 chg** | DataFrame (self.df) | DataFabric._static_data |
| **GORT** | DataFrame (self.df) | DataFabric._derived_data |
| **MAXALW** | DataFrame (self.df) | DataFabric._static_data |
| **GROUP** | DataFrame (self.df) | DataFabric._static_data |
| **CGRUP** | DataFrame (self.df) | DataFabric._static_data |
| **befday_qty** | CSV (befham.csv) | ShadowPositionStore or CSV |
| **current_qty** | hammer.get_positions() | PositionSnapshotAPI |
| **open_orders_qty** | hammer.get_orders() | OrderSnapshotAPI |
| **bid/ask/last** | hammer.get_market_data() | DataFabric._live_data |

---

## 🔍 Detaylı Data Flow Diyagramları

### KARBOTU Step 2 - Janall

```
┌─────────────────────────────────────────────────────────────┐
│              JANALL KARBOTU STEP 2 DATA FLOW                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Take Profit Longs Panel Tree                           │
│     │                                                        │
│     └─> values[1] = symbol (PREF IBKR)                     │
│     └─> values[2] = qty (from Hammer positions)           │
│     └─> values[5] = fbtot (from DataFrame)                │
│     └─> values[8] = ask_sell_pahalilik (from DataFrame)  │
│                                                             │
│  2. DataFrame (self.df)                                     │
│     │                                                        │
│     ├─> Static: prev_close, FINAL_THG                     │
│     │      Source: CSV (janalldata.csv)                    │
│     │      Update: Startup only                            │
│     │                                                        │
│     └─> Calculated: Fbtot, Ask Sell Pahalılık            │
│            Source: calculate_scores()                      │
│            Update: Polling (3s) - update_scores_with_market_data()│
│            │                                                  │
│            └─> Inputs:                                      │
│                  ├─> bid, ask, last (from hammer.get_market_data())│
│                  ├─> prev_close (from DataFrame)           │
│                  └─> benchmark_chg (from ETF data)         │
│                                                             │
│  3. Filter Conditions                                       │
│     │                                                        │
│     ├─> fbtot < 1.10 (from DataFrame)                      │
│     ├─> ask_sell_pahalilik > -0.10 (from DataFrame)       │
│     ├─> qty >= 100 (from Panel Tree)                      │
│     └─> fbtot != 0.0 (exclude N/A)                         │
│                                                             │
│  4. Lot Calculation                                          │
│     │                                                        │
│     └─> calculated_lot = qty * 0.50 (50%)                  │
│            │                                                  │
│            └─> Rounded to nearest 100                      │
│                                                             │
│  5. Confirmation Window                                     │
│     │                                                        │
│     └─> karbotu_show_confirmation_window()                 │
│            │                                                  │
│            └─> User Approval                                │
│                    │                                          │
│                    └─> Direct Order (Hammer Pro API)       │
│                            │                                  │
│                            └─> hammer.place_order()        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### KARBOTU Step 2 - Quant Engine

```
┌─────────────────────────────────────────────────────────────┐
│           QUANT ENGINE KARBOTU STEP 2 DATA FLOW             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. RUNALL Cycle → _step_run_karbotu()                     │
│     │                                                        │
│     └─> _prepare_karbotu_request()                        │
│            │                                                  │
│            ├─> PositionSnapshotAPI.get_position_snapshot() │
│            │      │                                          │
│            │      ├─> HAMMER: hammer_positions_service     │
│            │      │   OR                                      │
│            │      └─> IBKR: ibkr_connector.get_positions() │
│            │              │                                  │
│            │              └─> Enrich: DataFabric.get_fast_snapshot()│
│            │                      │                          │
│            │                      ├─> _live_data: bid, ask, last│
│            │                      ├─> _static_data: prev_close, FINAL_THG│
│            │                      └─> _derived_data: Fbtot, Ask Sell Pahalılık│
│            │                                                          │
│            └─> MetricsSnapshotAPI.get_metrics_snapshot()   │
│                    │                                          │
│                    └─> MarketSnapshotStore.get_current_snapshot()│
│                            │                                  │
│                            ├─> DataFabric.get_fast_snapshot()│
│                            └─> PricingOverlayEngine.get_overlay_scores()│
│                                    │                          │
│                                    └─> FastScoreCalculator.compute_fast_scores()│
│                                            │                  │
│                                            └─> Janall formulas│
│                                                             │
│  2. karbotu_decision_engine(request)                        │
│     │                                                        │
│     ├─> GORT Filter                                         │
│     │      │                                                  │
│     │      ├─> metric.gort > -1 (from MetricsSnapshotAPI) │
│     │      └─> metric.ask_sell_pahalilik > -0.05          │
│     │                                                          │
│     └─> Step 2 Processing                                   │
│            │                                                  │
│            ├─> Filter: fbtot < 1.10, ask_sell > -0.10     │
│            ├─> Lot: qty * 0.50 (50%)                       │
│            └─> Decision: SELL, ASK_SELL, price=metric.ask │
│                                                             │
│  3. ProposalEngine.process_decision_response()             │
│     │                                                        │
│     └─> ProposalStore.add_proposal()                       │
│            │                                                  │
│            └─> WebSocket Broadcast → UI                   │
│                    │                                          │
│                    └─> User Approval → IntentStore → ExecutionEngine│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### ADDNEWPOS - Janall

```
┌─────────────────────────────────────────────────────────────┐
│              JANALL ADDNEWPOS DATA FLOW                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. User Click → ADDNEWPOS Button                          │
│     │                                                        │
│     └─> FinalThgLotDistributor.distribute_lots()          │
│            │                                                  │
│            └─> DataFrame (self.df) → ALL symbols           │
│                    │                                          │
│                    ├─> Static: prev_close, FINAL_THG, MAXALW, GROUP, CGRUP│
│                    │      Source: CSV (janalldata.csv)    │
│                    │      Update: Startup only            │
│                    │                                          │
│                    ├─> Calculated: Final_BB, Final_FB, Fbtot, Bid Buy Ucuzluk│
│                    │      Source: calculate_scores()       │
│                    │      Update: Polling (3s)            │
│                    │                                          │
│                    └─> Live: bid, ask, last                 │
│                            Source: hammer.get_market_data() │
│                            Update: Real-time (L1Update)    │
│                                                             │
│  2. Filter Conditions                                       │
│     │                                                        │
│     ├─> bid_buy_ucuzluk < -0.06 (from DataFrame)          │
│     ├─> fbtot > 1.10 (from DataFrame)                     │
│     ├─> sma63_chg < threshold (optional, from DataFrame) │
│     ├─> gort < threshold (optional, from DataFrame)       │
│     ├─> spread < 0.25 (from hammer.get_market_data())     │
│     └─> AVG_ADV > 100.0 (from DataFrame)                 │
│                                                             │
│  3. JFIN Selection                                          │
│     │                                                        │
│     ├─> Group-based Selection                              │
│     │      │                                                  │
│     │      ├─> Sort by Final_FB_skor (descending)         │
│     │      ├─> Take top X% per group                       │
│     │      ├─> Sort by Final_BB_skor (descending)        │
│     │      └─> Take top X% per group                       │
│     │                                                          │
│     └─> Alpha-weighted Lot Distribution                    │
│                                                             │
│  4. Portfolio Rules → Lot Calculation                      │
│     │                                                        │
│     └─> Based on current position %:                      │
│            ├─> < 1%: MAXALW × 0.50, Portfolio × 5%        │
│            ├─> 1-3%: MAXALW × 0.40, Portfolio × 4%        │
│            └─> ...                                          │
│                                                             │
│  5. MAXALW Check                                            │
│     │                                                        │
│     ├─> befday_qty (from CSV: befham.csv)                 │
│     ├─> current_qty (from hammer.get_positions())          │
│     ├─> open_orders_qty (from hammer.get_orders())         │
│     └─> max_change_limit = maxalw * 3 / 4                  │
│            │                                                  │
│            └─> If potential_daily_change > max_change_limit: BLOCK│
│                                                             │
│  6. Confirmation Window                                     │
│     │                                                        │
│     └─> show_order_confirmation_window()                   │
│            │                                                  │
│            └─> User Approval → Direct Order (Hammer Pro API)│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### ADDNEWPOS - Quant Engine

```
┌─────────────────────────────────────────────────────────────┐
│           QUANT ENGINE ADDNEWPOS DATA FLOW                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. RUNALL Cycle → _step_run_addnewpos()                   │
│     │                                                        │
│     └─> _prepare_addnewpos_request()                       │
│            │                                                  │
│            ├─> StaticDataStore.get_all_symbols()            │
│            │      └─> ALL symbols from CSV (440)           │
│            │                                                  │
│            ├─> PositionSnapshotAPI.get_position_snapshot() │
│            │      └─> Existing positions (for exclusion)   │
│            │                                                  │
│            └─> MetricsSnapshotAPI.get_metrics_snapshot()   │
│                    └─> ALL symbols                          │
│                            │                                  │
│                            └─> MarketSnapshotStore.get_current_snapshot()│
│                                    │                          │
│                                    ├─> DataFabric.get_fast_snapshot()│
│                                    │      │                      │
│                                    │      ├─> _live_data: bid, ask, last│
│                                    │      ├─> _static_data: prev_close, FINAL_THG, MAXALW, GROUP, CGRUP│
│                                    │      └─> _derived_data: Fbtot, Bid Buy Ucuzluk, Final_BB_skor, Final_FB_skor│
│                                    │                              │
│                                    └─> PricingOverlayEngine.get_overlay_scores()│
│                                            │                  │
│                                            └─> FastScoreCalculator.compute_fast_scores()│
│                                                    │          │
│                                                    └─> Janall formulas│
│                                                             │
│  2. addnewpos_decision_engine(request)                      │
│     │                                                        │
│     ├─> Filter: bid_buy_ucuzluk < -0.06, fbtot > 1.10     │
│     ├─> Filter: sma63_chg < threshold (optional)          │
│     ├─> Filter: gort < threshold (optional)              │
│     ├─> Filter: spread < 0.25                             │
│     ├─> Filter: AVG_ADV > 100.0                           │
│     └─> Portfolio Rules → Lot Calculation                 │
│                                                             │
│  3. JFIN Engine.transform_candidates()                     │
│     │                                                        │
│     ├─> Group-based Selection                              │
│     │      │                                                  │
│     │      ├─> Sort by Final_FB_skor (descending)         │
│     │      ├─> Take top X% per group                       │
│     │      ├─> Sort by Final_BB_skor (descending)         │
│     │      └─> Take top X% per group                       │
│     │                                                          │
│     ├─> Alpha-weighted Lot Distribution                    │
│     └─> MAXALW Check                                       │
│            │                                                  │
│            ├─> befday_qty (ShadowPositionStore or CSV)     │
│            ├─> current_qty (PositionSnapshotAPI)           │
│            ├─> open_orders_qty (OrderSnapshotAPI)          │
│            └─> max_change_limit = maxalw * 3 / 4            │
│                    │                                          │
│                    └─> If potential_daily_change > max_change_limit: REJECT│
│                                                             │
│  4. ProposalEngine → ProposalStore → UI                    │
│     │                                                        │
│     └─> User Approval → IntentStore → ExecutionEngine     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Sonuç ve Öneriler

### Ana Bulgular

1. **Data Source Birliği**: Quant Engine'de tüm data `DataFabric.get_fast_snapshot()` üzerinden geliyor (Single Source of Truth). Janall'da DataFrame + Hammer cache karışık.

2. **Update Frequency**: Quant Engine event-driven (anında), Janall polling (3s gecikme).

3. **Execution Model**: Quant Engine Human-in-the-Loop (Proposal → Intent → Execution), Janall direkt execution.

4. **Position Source**: Quant Engine HAMMER veya IBKR (account mode'a göre), Janall sadece HAMMER.

5. **Formül Tutarlılığı**: Her iki sistemde de aynı formüller kullanılıyor (800 katsayısı, Janall formulas).

### Öneriler

1. **DataFabric Kullanımı**: Tüm PSFALGO algoritmaları `DataFabric.get_fast_snapshot()` kullanmalı (zaten kullanıyor ✅).

2. **MetricsSnapshotAPI**: Tüm decision engine'ler `MetricsSnapshotAPI` üzerinden metrics almalı (zaten alıyor ✅).

3. **PositionSnapshotAPI**: Tüm decision engine'ler `PositionSnapshotAPI` üzerinden positions almalı (zaten alıyor ✅).

4. **Event-Driven Updates**: Skorlar event-driven güncellenmeli (zaten güncelleniyor ✅).

5. **Human-in-the-Loop**: Proposal → Intent → Execution zinciri korunmalı (zaten korunuyor ✅).

---

*Rapor Tarihi: 2025-01-17*
*Versiyon: 1.0*





