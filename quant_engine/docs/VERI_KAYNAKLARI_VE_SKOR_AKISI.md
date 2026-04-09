# Veri Kaynakları, Güncellik ve Skor Akışı

Bu doküman: **Truth Tick**, **L1**, **VOLAV**, **daily_chg**, **bench_chg**, **ucuzluk/pahalılık** skorlarının nereden alındığını, ne sıklıkla güncellendiğini, Redis’e nasıl yazıldığını ve bileşenler arası nasıl aktarıldığını açıklar.

---

## 1. Truth Tick Verileri

### Nereden alınıyor?
- **Hammer Pro** trade print’leri (gerçek işlem tikleri).
- **GRPANTickFetcher** (Truth Ticks Worker içinde):
  - Hammer’a bağlanır, semboller için trade print’leri toplar.
  - **Polling**: 60 saniyede bir son tikleri çeker (`polling_interval=60`).
  - İlk yüklemede bootstrap ile son ~2500 tik alınır.
- **TradePrintRouter** → **GRPANEngine** normalizasyonu → **TruthTicksEngine.add_tick()**.
- Sadece **geçerli** tikler saklanır: `calculate_print_weight(size, exch)` > 0 (min lot, venue kuralları; örn. min size 15).

### Güncellik
- **Gerçek zamanlı (worker içinde)**: Hammer’dan gelen her trade print, `add_tick()` ile in-memory `tick_store`’a yazılır (worker process’i içinde).
- **Redis’e çıkan kısım**: Truth Ticks Worker **analiz döngüsü** (auto_analysis) **dakikada 1** çalışır; her sembol için `get_inspect_data()` ile path_dataset, volav_levels, temporal_analysis hesaplanır ve Redis’e yazılır.

### Redis’e nasıl kaydediliyor?
| Redis anahtarı | Yazıcı | TTL | İçerik |
|----------------|--------|-----|--------|
| `truth_ticks:inspect:{symbol}` | Truth Ticks Worker (`process_job` / auto_analysis) | 3600 s (1 saat) | `{ "success", "symbol", "data": { path_dataset, volav_levels, temporal_analysis (1h/4h/1d/3d hist_volav), state, ... } }` |
| `truth_ticks:auto_analysis` | Truth Ticks Worker (analysis scheduler) | 300 s (5 dk) | Tüm sembollerin özet sonuçları (UI için). |
| `truthtick:latest:{symbol}` | Truth Ticks Worker (inspect kaydı sırasında path_dataset'in son tick'ı) | “Truth Ticks Worker inspect kaydı sırasında path_dataset’in son geçerli tick’ı yazılmalı” | 300 s (5 dk) | `{ "price", "ts", "size", "venue"/"exch" }` (son geçerli truth tick). |

**Özet**: Truth tick verisi Hammer → Worker (in-memory) → dakikada 1 analiz ile `truth_ticks:inspect:{symbol}` olarak Redis’e yazılıyor. Aynı analizde path_dataset'in son elemanı `truthtick:latest:{symbol}` olarak da yazılır; RevnBookCheck/Frontlama bu anahtardan son truth tick'ı okur.

---

## 2. L1 Verileri (Bid / Ask / Last)

### Nereden alınıyor?
- **Hammer Pro**: `get_symbol_snapshot(symbol)` veya L1 subscription ile gelen **L1Update** mesajları (bid, ask, last; prev_close snapshot’ta ayrı gelir).

### Kim yazıyor, ne sıklıkla?
| Kaynak | Sıklık | Redis anahtarı | TTL |
|--------|--------|-----------------|-----|
| **L1 Feed Worker** (`workers/l1_feed_worker.py`) | 30 s | `market:l1:{symbol}` | 120 s (2 dk) |
| **L1 Feed Worker** | Her cycle sonrası | Pub/Sub: `market:live:updates` | - |
| **Truth Ticks Worker** (L1 Feed Loop) | 30 s | `market:l1:{symbol}` | 120 s |
| **SnapshotScheduler** (Truth Ticks Worker içinde) | 1 dk (interval_minutes=1) | `market_data:snapshot:{symbol}` + `market:l1:{symbol}` | snapshot: süresiz, L1: 600 s (10 dk) |

### Redis’e nasıl kaydediliyor?
- **market:l1:{symbol}**: JSON `{ "bid", "ask", "spread", "last", "ts" }`. L1 Feed Worker veya Truth Ticks Worker’ın L1 döngüsü `setex` ile yazar.
- **market_data:snapshot:{symbol}**: SnapshotScheduler tarafından tam snapshot (bid, ask, last, volume, prevClose, change, high, low, timestamp vb.).
- **market:live:updates** (Pub/Sub): L1 Feed Worker, her 30 s cycle’dan sonra tüm güncellenen sembollerin L1 verisini tek mesajda publish eder. Backend’deki **L1 Feed Listener** (`main.py` → `start_l1_feed_listener`) bu kanalı dinler ve **DataFabric.update_live_batch(updates)** çağırır → backend RAM’deki L1 cache güncellenir.

**Özet**: Tüm hisselerin L1’i Hammer’dan 30 s (veya Truth Ticks tarafında da 30 s + Snapshot 1 dk) ile alınıp `market:l1:{symbol}` ve isteğe göre `market_data:snapshot:{symbol}` olarak Redis’e yazılıyor; L1 Feed Worker ayrıca `market:live:updates` ile backend DataFabric’i güncelliyor.

---

## 3. VOLAV Verileri

### Nereden alınıyor?
- **Truth Ticks Engine** içinde hesaplanır; ham veri **truth tick’lar** (trade print’ler).
- `compute_volav_levels(truth_ticks, top_n, avg_adv)`: Hacim ağırlıklı fiyat kümeleri (Volav seviyeleri).
- `compute_volav_timeline()`: Zaman pencerelerinde volav evrimi (volav1_start, volav1_end, displacement, yön).
- `get_inspect_data(symbol, avg_adv)`: path_dataset, volav_levels, temporal_analysis (1h, 4h, 1d, 3d için `hist_volav` vb.) üretir.

### Güncellik
- Truth Ticks Worker’ın **auto_analysis** döngüsü **dakikada 1** çalışır; her atanmış sembol için `get_inspect_data()` çağrılır, sonuç Redis’e yazılır. Yani VOLAV ve truth tick tabanlı tüm metrikler **dakikada 1** güncellenir.

### Redis’e nasıl kaydediliyor?
- VOLAV, ayrı bir Redis anahtarında tutulmaz; **truth_ticks:inspect:{symbol}** içindeki `data` objesinde gelir:
  - `volav_levels`, `volav_timeline`, `volav1_start`, `volav1_end`, `volav1_displacement`, `volav_shift_dir`, `temporal_analysis.{1h,4h,1d,3d}.hist_volav` vb.

**Özet**: VOLAV, truth tick’lardan Truth Ticks Engine’de türetilir ve dakikada 1 `truth_ticks:inspect:{symbol}` ile Redis’e yazılır.

---

## 4. Daily Change (daily_chg)

### Nasıl hesaplanıyor?
- **Formül**: `daily_chg = last - prev_close` (cent cinsinden; yüzde değil).
- **JanallMetricsEngine.compute_symbol_metrics()**: `live_row` (L1: last, prev_close) ve static row kullanır.
- **FastScoreCalculator.compute_fast_scores()**: DataFabric’ten `get_live(symbol)` ve `get_static(symbol)` ile aynı formül.

### Güncellik
- L1 güncellendiği anda (DataFabric’te live veri değişince) skor hesapları tetiklenir:
  - Backend: `market:live:updates` → `update_live_batch` → RAM’deki live veri güncellenir; API’den `get_fast_snapshot` / janall batch çağrıldığında daily_chg yeniden hesaplanır.
  - Runall / proposal tarafı: DataFabric veya Redis’ten L1 + static okuyup Janall/FastScore ile hesaplar.
- **Sıklık**: L1 verisi 30 s’de bir güncellendiği için, daily_chg da pratikte **en az 30 s** aralıklı taze veriyle üretilir (API/runall ne sıklıkla okursa o kadar).

**Özet**: daily_chg = last - prev_close; L1 + static ile anlık hesaplanır, güncelliği L1 güncelliğine (30 s) bağlıdır.

---

## 5. Benchmark Change (bench_chg)

### Nasıl hesaplanıyor?
- **bench_chg** = Sembolün ait olduğu **grubun (DOSGRUP / CGRUP)** günlük değişim ortalaması.
- **JanallMetricsEngine.compute_group_metrics()**: Grup içindeki tüm sembollerin `daily_chg` değerleri toplanır (aşırı uçlar hariç, örn. |daily_chg| < 5.0), `group_avg_daily_chg` hesaplanır.
- **apply_group_overlays()**: Her sembol için `symbol_metrics['bench_chg'] = group_avg_daily_chg` atanır; kaynak açıklaması `bench_source` (örn. "Group: heldkuponlu:c575 (n=12)").

### Güncellik
- Grup metrikleri, Janall’ın **batch** çalıştığı zaman (tüm sembollerin metrics’i toplanıp group_stats hesaplandığında) güncellenir. Bu batch, L1/static verisi ve API veya runall’ın metrics talebi ile tetiklenir. Yani bench_chg, **daily_chg ile aynı veri döngüsünde** ve aynı L1 güncelliğine bağlıdır.

**Özet**: bench_chg = gruptaki sembollerin daily_chg ortalaması; Janall batch ile hesaplanır, güncelliği L1/janall batch sıklığına bağlıdır.

---

## 6. Ucuzluk / Pahalılık Skorları

### Nasıl hesaplanıyor?
- **Referans**: Grup benchmark’ı (`bench_chg`).
- **Formüller** (Janall):
  - **bid_buy_ucuzluk** = (pf_bid_buy - prev_close) - bench_chg  
  - **ask_sell_pahalilik** = (pf_ask_sell - prev_close) - bench_chg  
  - **front_buy_ucuzluk** = (pf_front_buy - prev_close) - bench_chg  
  - **front_sell_pahalilik** = (pf_front_sell - prev_close) - bench_chg  
  - (pf_*: passive fill fiyatları, örn. pf_bid_buy = bid + spread*0.15, pf_ask_sell = ask - spread*0.15.)
- **JanallMetricsEngine**: `compute_symbol_metrics` içinde benchmark_chg ile bu skorlar hesaplanır; `apply_group_overlays` içinde bench_chg grup ortalamasına göre (ve istenirse fill-based) tekrar ayarlanabilir.
- **FastScoreCalculator**: DataFabric’ten L1 + static alıp aynı mantıkla bid_buy_ucuzluk, ask_sell_pahalilik, Final_BB, Final_FB, Final_SAS, Final_SFS vb. üretir.

### Güncellik
- L1 ve bench_chg güncellendiği anda (Janall batch veya FastScore çağrıldığında) yeniden hesaplanır. Yani **L1 güncelleme sıklığı (30 s)** ve **API/runall’ın metrics/snapshot çağrı sıklığı** ile belirlenir.

**Özet**: Ucuzluk/pahalılık = (pasif fiyat - prev_close) - bench_chg; Janall/FastScore ile L1 + CSV + bench_chg kullanılarak hesaplanır, güncelliği L1 ve batch sıklığına bağlıdır.

---

## 7. Verilerin Birbirine Aktarımı (Akış Özeti)

```
Hammer Pro
    │
    ├─ Trade prints ──► GRPANTickFetcher (60s poll) ──► TradePrintRouter ──► TruthTicksEngine (in-memory)
    │                                                                              │
    │                                                                              ▼
    │                                                                   get_inspect_data() [dakikada 1]
    │                                                                              │
    │                                                                              ▼
    │                                                                   Redis: truth_ticks:inspect:{symbol}
    │                                                                   (path_dataset, volav_levels, temporal_analysis)
    │
    ├─ L1 / Snapshot ──► L1 Feed Worker (30s) ──────────► Redis: market:l1:{symbol}
    │       │                    │
    │       │                    └─────────────────────► Pub/Sub: market:live:updates
    │       │                                                          │
    │       │                                                          ▼
    │       │                                               Backend: start_l1_feed_listener
    │       │                                                          │
    │       │                                                          ▼
    │       │                                               DataFabric.update_live_batch()  [RAM L1]
    │       │
    │       └─ SnapshotScheduler (Truth Ticks Worker, 1m) ──► Redis: market_data:snapshot:{symbol}, market:l1:{symbol}
    │
    ▼
DataFabric (RAM): _live_data, _static_data
    │
    ├─ get_fast_snapshot / get_live ──► FastScoreCalculator ──► daily_chg, ucuzluk/pahalılık, Final_*
    │
    └─ Janall batch (compute_symbol_metrics + compute_group_metrics + apply_group_overlays)
           │
           └─► daily_chg, bench_chg, bid_buy_ucuzluk, ask_sell_pahalilik, final_bb, final_fb, ...
                    │
                    └─► metrics_snapshot_api / market_data_routes ──► API / UI
                    └─► runall_engine (symbol_metrics) ──► decision.bench_chg, decision.ask_sell_pahalilik
```

- **RevnBookCheck / RevRecovery**: L1 için `market:l1:{symbol}` (fallback: `market_data:snapshot:{symbol}`), truth tick için `truthtick:latest:{symbol}` okur (Truth Ticks Worker dakikada 1 inspect ile bu anahtarı doldurur).
- **GemEngine / GenObs / GreatestMM**: Truth/Volav için `truth_ticks:inspect:{symbol}` okur.

---

## 8. Özet Tablo

| Veri | Kaynak | Redis anahtarı | Güncelleme sıklığı |
|------|--------|-----------------|---------------------|
| Truth Tick (ham) | Hammer trade prints | - (in-memory worker) | Sürekli (worker içinde) |
| Truth Tick (inspect) | Truth Ticks Engine | truth_ticks:inspect:{symbol} | 1 dk |
| Truth Tick (son tik) | Truth Ticks Worker (inspect ile birlikte) | truthtick:latest:{symbol} | 1 dk (inspect ile) |
| L1 | Hammer snapshot / L1Update | market:l1:{symbol} | 30 s |
| Snapshot | Hammer snapshot | market_data:snapshot:{symbol} | 1 dk (SnapshotScheduler) |
| VOLAV | Truth Ticks Engine | truth_ticks:inspect:{symbol} içinde | 1 dk |
| daily_chg | last - prev_close | DataFabric / API yanıtı | L1 ile (30 s) |
| bench_chg | Grup daily_chg ort. | DataFabric / API yanıtı | Janall batch ile |
| Ucuzluk/Pahalılık | L1 + CSV + bench_chg | DataFabric / API yanıtı | L1 + batch ile |

Bu doküman, kod incelemelerine (truth_ticks_worker, l1_feed_worker, snapshot_scheduler, data_fabric, janall_metrics_engine, fast_score_calculator, revnbookcheck, main.py L1 listener) dayanmaktadır.
