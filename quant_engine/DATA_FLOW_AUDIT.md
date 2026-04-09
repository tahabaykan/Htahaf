# Redis Data Flow Audit — Complete Report (v2)
## Date: 2026-02-21 04:30

---

## 1. AGENT VERI ERİŞİM MATRİSİ

### Agent'ın Eriştiği Veri Kategorileri (11 Tool)

| # | Tool | Veri | Redis Key/Source | Durum |
|---|------|------|-----------------|-------|
| 1 | `get_symbol_detail` | Fiyat (bid/ask/last/spread), GORT, FINAL_THG, SHORT_FINAL, FBTOT, SFSTOT, SMA63chg, SMA246chg, ucuzluk/pahalılık, AVG_ADV, L1 data, truth tick | DataFabric + `tt:ticks:{sym}` + `market:l1:{sym}` | ✅ |
| 2 | `get_truth_tick_history` | Son N truth tick, volav (market microstructure state), temporal analysis | `truth_ticks:inspect:{sym}` → `tt:ticks:{sym}` fallback | ✅ FIXED |
| 3 | `get_group_analysis` | DOS grubundaki TÜM hisseler: fiyat, GORT, bench_chg, daily_chg, ucuzluk/pahalılık | DataFabric | ✅ |
| 4 | `get_positions` | Her hesaptaki pozisyonlar: symbol, qty, befday_qty, potential_qty, current_price | `psfalgo:unified_positions:{acct}` | ✅ (3 hesap) |
| 5 | `get_open_orders` | Açık emirler: symbol, action, qty, price, tag | `psfalgo:open_orders:{acct}` | ✅ (3 hesap) |
| 6 | `get_fills_today` | Bugünkü fill'ler: symbol, action, qty, price, time, tag, bench_chg | `psfalgo:todays_fills:{acct}` | ✅ (3 hesap) |
| 7 | `get_exposure_status` | Exposure durumu: pot_total, pot_max, exposure_pct, mode | `psfalgo:exposure:{acct}` → live calc fallback | ✅ FIXED |
| 8 | `get_etf_data` | ETF fiyatları: TLT, SPY, PFF, HYG, JNK, SJNK, VNQ, AGG | DataFabric | ✅ |
| 9 | `get_qebench_performance` | Benchmark vs portföy performansı | `psfalgo:{key}qebench:summary` | ✅ |
| 10 | `compare_symbols` | Birden fazla hisseyi yan yana karşılaştır | DataFabric | ✅ |
| 11 | `search_by_criteria` | Kriterlere göre hisse ara (GORT aralığı, ucuzluk, grup, spread) | DataFabric | ✅ |

### MetricsCollector Payload (Otomatik Scan)

| Veri | Kaynak | Durum |
|------|--------|-------|
| ~450 ticker basic metrics | DataFabric + `tt:ticks:*` | ✅ |
| Active ticker tt_history | `truth_ticks:inspect:{sym}` | ✅ |
| Exposure status | `psfalgo:exposure:{acct}` → live calc | ✅ FIXED |
| Positions | `psfalgo:positions:{acct}` | ✅ |
| Open orders | HammerOrderService | ✅ |
| Today's fills | DailyFillsStore | ✅ |
| DOS group summaries | DataFabric | ✅ |
| QeBench performance | `psfalgo:*qebench:summary` | ✅ |
| ETF strip | DataFabric | ✅ |
| System state | `psfalgo:dual_process:state`, `psfalgo:xnl:running` | ✅ |
| Anomaly score | Computed from payload | ✅ |

---

## 2. TÜM FIXLER (Bu Session + Önceki)

### Truth Tick Key Düzeltmeleri

| # | Component | Eski Key (YANLIŞ) | Yeni Key (DOĞRU) | Dosya |
|---|-----------|-------------------|-------------------|-------|
| 1 | MetricsCollector._batch_get_truth_ticks | `truthtick:latest:{sym}` | `tt:ticks:{sym}` | metrics_collector.py |
| 2 | Frontlama._get_latest_truth_tick | `truthtick:latest:{sym}` | `tt:ticks:{sym}` → fallback `truthtick:latest` | revnbookcheck.py |
| 3 | XNL Engine._get_truth_tick_data | `truthtick:latest:{sym}` | `tt:ticks:{sym}` → fallback `truthtick:latest` | xnl_engine.py |
| 4 | GemEngine._get_truth_price_raw | `truth_ticks:inspect:{sym}` only | `truth_ticks:inspect:{sym}` → fallback `tt:ticks:{sym}` | gem_engine.py |
| 5 | Agent._tool_symbol_detail | `truth_tick:{sym}` ❌ | `tt:ticks:{sym}` | qagentt_tools.py ★ |
| 6 | Agent._tool_truth_tick_history | `truth_tick:inspect:{sym}` ❌ | `truth_ticks:inspect:{sym}` → fallback `tt:ticks:{sym}` | qagentt_tools.py ★ |
| 7 | Agent._tool_truth_tick_history (latest) | `truth_tick:{sym}` ❌ | `tt:ticks:{sym}` | qagentt_tools.py ★ |

★ = Bu session'da düzeltildi

### Exposure Düzeltmeleri

| # | Component | Sorun | Fix | Dosya |
|---|-----------|-------|-----|-------|
| 8 | ExposureCalculator | Hesap yapıyor ama Redis'e YAZMIYOR | Her çağrıda `psfalgo:exposure:{acct}` yaz (5min TTL) | exposure_calculator.py |
| 9 | Frontlama._get_current_exposure_pct | Sadece Redis, yoksa 65% default | Redis → live calc → 65% default | revnbookcheck.py |
| 10 | MetricsCollector._collect_exposure | Sadece Redis, yoksa None | Redis → live calc → None | metrics_collector.py |
| 11 | MetricsCollector._collect_exposure_status | Kendi regime hesaplıyor | Redis'ten `mode` direkt oku | metrics_collector.py |
| 12 | Agent._tool_exposure_status | Sadece HAMPRO/IBKR_PED | 3 hesap + live calc fallback | qagentt_tools.py |

### Hesap Kapsamı Düzeltmeleri

| # | Component | Eski | Yeni |
|---|-----------|------|------|
| 13 | Agent._tool_positions | HAMPRO, IBKR_PED | + IBKR_GUN |
| 14 | Agent._tool_open_orders | HAMPRO, IBKR_PED | + IBKR_GUN |
| 15 | Agent._tool_fills_today | HAMPRO, IBKR_PED | + IBKR_GUN |
| 16 | Agent._tool_exposure_status | HAMPRO, IBKR_PED | + IBKR_GUN |

---

## 3. VERİ AKIŞ DİYAGRAMI

```
╔════════════════════════════════════════════════════════════════╗
║                    VERI KAYNAKLARI                              ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Hammer Pro API ──► TruthTicksEngine                           ║
║       │                    │                                   ║
║       │               persist_to_redis()                       ║
║       │                    │                                   ║
║       ▼                    ▼                                   ║
║  market_data_routes    tt:ticks:{sym}  [12d TTL] ★ CANONICAL   ║
║       │                                                        ║
║       ▼                                                        ║
║  live:{sym}  [HASH]    TruthTicksWorker (when running)         ║
║  market:l1:{sym}           │                                   ║
║                            ├─► truth_ticks:inspect:{sym} [1h]  ║
║                            └─► truthtick:latest:{sym}   [10m]  ║
║                                                                ║
║  PositionSnapshotAPI ──► psfalgo:positions:{acct}              ║
║  ExposureCalculator  ──► psfalgo:exposure:{acct}  [5m TTL] ★   ║
║  BEFDAYTracker       ──► psfalgo:befday:positions:{acct}       ║
║  HammerOrdersService ──► psfalgo:open_orders:{acct}            ║
║  DailyFillsStore     ──► psfalgo:todays_fills:{acct}           ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                     TÜKETİCİLER (CONSUMERS)                    ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  ┌─────────────── QAGENTT (Agent) ──────────────────┐          ║
║  │                                                   │          ║
║  │  MetricsCollector (otomatik her 5dk)               │          ║
║  │  ├─ ~450 ticker metrics ← DataFabric + tt:ticks   │          ║
║  │  ├─ Active tickers inspect ← truth_ticks:inspect  │          ║
║  │  ├─ Exposure ← psfalgo:exposure + live calc       │          ║
║  │  ├─ Positions ← psfalgo:positions                 │          ║
║  │  ├─ Orders ← HammerOrdersService                 │          ║
║  │  ├─ Fills ← DailyFillsStore                      │          ║
║  │  ├─ Groups ← DataFabric                          │          ║
║  │  ├─ QeBench ← psfalgo:*qebench:summary           │          ║
║  │  ├─ ETF ← DataFabric                             │          ║
║  │  └─ Anomaly Score → triggers Deep Analysis        │          ║
║  │                                                   │          ║
║  │  11 Interactive Tools (on-demand by Agent)         │          ║
║  │  ├─ get_symbol_detail (fiyat+metrik+tt)           │          ║
║  │  ├─ get_truth_tick_history (tt geçmişi+volav)     │          ║
║  │  ├─ get_group_analysis (DOS grup analiz)          │          ║
║  │  ├─ get_positions (3 hesap)                       │          ║
║  │  ├─ get_open_orders (3 hesap)                     │          ║
║  │  ├─ get_fills_today (3 hesap)                     │          ║
║  │  ├─ get_exposure_status (3 hesap + live calc)     │          ║
║  │  ├─ get_etf_data (TLT/SPY/PFF/HYG...)            │          ║
║  │  ├─ get_qebench_performance                       │          ║
║  │  ├─ compare_symbols (yan yana karşılaştır)        │          ║
║  │  └─ search_by_criteria (filtreli arama)           │          ║
║  └───────────────────────────────────────────────────┘          ║
║                                                                ║
║  Frontlama ← tt:ticks + exposure + positions + L1              ║
║  XNL Engine ← tt:ticks + exposure + positions                  ║
║  GemEngine ← truth_ticks:inspect → tt:ticks fallback           ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

---

## 4. VERİ BÜTÜNLÜK KONTROLÜ

| Veri Kategorisi | Yazıcı | Redis Key | TTL | Consumer'lar | Durum |
|----------------|--------|-----------|-----|-------------|-------|
| Truth Ticks (canonical) | TruthTicksEngine | `tt:ticks:{sym}` | 12d | Agent, Frontlama, XNL, GemEngine, MetricsCollector | ✅ |
| Truth Ticks (rich) | TruthTicksWorker | `truth_ticks:inspect:{sym}` | 1h | Agent (tool+scan), GemEngine | ⚠️ Ephemeral |
| Truth Ticks (legacy) | TruthTicksWorker | `truthtick:latest:{sym}` | 10m | Frontlama/XNL fallback only | ⚠️ Ephemeral |
| L1 Market Data | TruthTicksWorker/Snapshots | `market:l1:{sym}` | 2m | Agent symbol_detail | ✅ |
| Live Market Data | market_data_routes | `live:{sym}` | 60m | DataFabric → Agent | ✅ |
| Positions | PositionSnapshotAPI | `psfalgo:positions:{acct}` | 1h | Agent, Frontlama, XNL | ✅ |
| Unified Positions | PositionSnapshotAPI | `psfalgo:unified_positions:{acct}` | 1h | Agent tool | ✅ |
| BEFDAY Positions | BEFDAYTracker | `psfalgo:befday:positions:{acct}` | 24h | ExposureWorker | ✅ |
| Open Orders | Backend | `psfalgo:open_orders:{acct}` | varies | Agent tool | ✅ |
| Today's Fills | DailyFillsStore | In-memory | session | Agent MetricsCollector | ✅ |
| **Exposure** | **ExposureCalculator** | **`psfalgo:exposure:{acct}`** | **5m** | **Agent, Frontlama, MetricsCollector** | **✅ FIXED** |
| Dual Process State | DualProcessRunner | `psfalgo:dual_process:state` | 1h | MetricsCollector | ✅ |
| XNL Running | XNL Engine | `psfalgo:xnl:running` | none | MetricsCollector | ✅ |
| QeBench Summary | QeBench | `psfalgo:*qebench:summary` | varies | Agent tool + MetricsCollector | ✅ |
| ETF Data | DataFabric | In-memory | live | Agent tool + MetricsCollector | ✅ |
| DOS Group Data | DataFabric/CSV | In-memory | static | Agent tool + MetricsCollector | ✅ |

---

## 5. SONUÇ

**Tüm kritik veri akışları düzeltildi.** Agent artık şunlara erişebilir:

✅ Her iki hesaptaki (HAMPRO + IBKR_PED + IBKR_GUN) pozisyonlar, emirler, fill'ler
✅ Gerçek exposure verisi (artık 65% default değil, gerçek pot_total/pot_max)
✅ Truth tick verileri doğru key'lerden (tt:ticks canonical, inspect fallback)
✅ ETF verileri (TLT, SPY, PFF, HYG, JNK, SJNK, VNQ, AGG)
✅ DOS grup analizleri ve metrikler (GORT, FBTOT, SFSTOT, FINAL_THG, SHORT_FINAL)
✅ L1 bid/ask verileri
✅ QeBench benchmark performansı
✅ System state (XNL çalışıyor mu, hangi hesap aktif, dual process durumu)
✅ Anomaly scoring (otomatik deep analysis tetikleme)

**Eski `truth_tick:` ve `truth_tick:inspect:` key pattern'leri tamamen temizlendi.**
**Tüm dosyalar syntax kontrolünden geçti.**
