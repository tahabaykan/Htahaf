# XNL Döngüsü – Tam ve Detaylı Açıklama

Bu dokümanda XNL Engine’in nasıl çalıştığı, frontlama kontrolü, hangi terminalden yapıldığı, Redis ve veri akışları, döngü süreleri tek tek anlatılıyor.

---

## 1. XNL Engine Nedir?

**Dosya:** `quant_engine/app/xnl/xnl_engine.py`

XNL Engine, otomatik emir döngülerini yönetir:

1. **Başlangıç (Initial Cycle):** RUNALL ile aynı veri katmanını kullanarak LT_TRIM → KARBOTU/REDUCEMORE → ADDNEWPOS → MM fazlarını çalıştırır, emirleri **frontlama kontrolü ile** gönderir.
2. **FRONT CYCLE:** Açık emirleri periyodik olarak frontlama fırsatına göre **fiyat güncellemesi** (modify) yapar.
3. **REFRESH CYCLE:** Aynı kategorideki emirleri iptal edip yeniden hesaplayıp tekrar gönderir.

Hesap: `TradingAccountContext` (Pozisyonlar ekranındaki aktif hesap). Tüm emirler bu hesaba gider.

---

## 2. Döngü Süreleri (Dakika / Saniye)

Zamanlama **tag kategorisine** göre sabit:

| Kategori        | Açıklama                    | FRONT CYCLE (tekrarlama) | REFRESH CYCLE (tekrarlama) | Aktif? |
|-----------------|-----------------------------|---------------------------|-----------------------------|--------|
| **LT_INCREASE** | ADDNEWPOS (yeni LT pozisyon) | **3.5 dakika** (210 sn)   | **8 dakika** (480 sn)       | Evet   |
| **LT_DECREASE** | LT_TRIM, KARBOTU, REDUCEMORE | **2 dakika** (120 sn)      | **5 dakika** (300 sn)       | Evet   |
| **MM_INCREASE** | MM yeni pozisyon             | 2 dakika                   | 3 dakika                    | MM ayarına bağlı |
| **MM_DECREASE** | MM kar alma                  | 30 saniye                  | 1 dakika                    | Varsayılan kapalı |

- **FRONT:** “Bu kategorideki açık emirleri frontlama ile güncelle” döngüsü.
- **REFRESH:** “Bu kategorideki emirleri iptal et, yeniden hesapla, tekrar gönder” döngüsü.

Kod: `CYCLE_TIMINGS` ve `_front_cycle_loop` / `_refresh_cycle_loop` içinde `await asyncio.sleep(timing.front_cycle_seconds)` / `refresh_cycle_seconds` ile bekleniyor.

---

## 3. XNL Başlangıç Akışı (Start)

1. **POST /api/xnl/start** çağrılır.
2. Engine state `RUNNING` yapılır.
3. Her **aktif** kategori için iki asyncio task oluşturulur:
   - `_front_cycle_loop(category)` → her N dakikada bir `_execute_front_cycle` çalışır.
   - `_refresh_cycle_loop(category)` → her M dakikada bir `_execute_refresh_cycle` çalışır.
4. **Initial cycle** ayrı bir task’ta arka planda çalışır (`_run_initial_cycle`), böylece start API hemen döner.

### Initial cycle adımları

1. **Hesap:** `get_trading_context().trading_mode.value` → `account_id`.
2. **Ortak istek:** `get_runall_engine().prepare_cycle_request(account_id, correlation_id)` → pozisyonlar, metrikler, exposure, L1, Janall verisi (RUNALL ile aynı katman).
3. **Fazlar (sırayla):**
   - **Phase 1 – LT_TRIM:** `_run_lt_trim(account_id, request)` → LT trim intents → emir listesi.
   - **Phase 2 – KARBOTU/REDUCEMORE:** `_run_karbotu` (exposure OFANSIF ise) → kar botu emirleri.
   - **Phase 3 – ADDNEWPOS:** `_run_addnewpos` (ayarlar + JFIN %, pool BB/FB/SAS/SFS) → yeni pozisyon emirleri.
   - **Phase 4 – MM:** `_run_mm` (MM ayarları, Greatest MM engine) → MM emirleri.
4. **Birleştirme:** Aynı (symbol, yön) için öncelik: LT_TRIM > KARBOTU > ADDNEWPOS > MM; tek emir bırakılır.
5. **Proposal store:** Bu emirler `cycle_id=-1` ile proposal_store’a yazılır (UI’da XNL batch olarak görünür).
6. **Gönderim:** `_send_orders_with_frontlama(all_orders, account_id)` ile **her emir önce frontlama değerlendirmesinden geçirilip** fiyat (gerekirse fronted) belirlenir, sonra `_place_order` ile broker’a gider.
7. **Cycle zamanları:** Tüm kategoriler için `last_front_cycle` ve `last_refresh_cycle` şu anki zamana set edilir.

---

## 4. Frontlama Kontrolü – Nerede ve Nasıl Yapılıyor?

### 4.1 İki yer kullanıyor

1. **XNL Engine (aynı process – Backend)**  
   - **Emir gönderirken:** `_send_orders_with_frontlama` içinde, her emir **gönderilmeden önce** `FrontlamaEngine.evaluate_order_for_frontlama` ile değerlendirilir; `allowed` ve `front_price` varsa o fiyatla gönderilir.  
   - **FRONT cycle’da:** `_execute_front_cycle` içinde, o kategorideki **açık emirler** tek tek frontlama ile değerlendirilir; uygunsa emir **modify** (iptal + aynı fiyatla yeniden place) edilir.

2. **RevnBookCheck Terminal (ayrı process)**  
   - **Frontlama döngüsü:** 60 saniyede bir `_run_frontlama_cycle` çalışır.  
   - Açık emirleri Redis’ten alır, her biri için L1 + truth tick + exposure ile `FrontlamaEngine.evaluate_order_for_frontlama` çağırır; onaylanırsa **fiyat güncellemesi** (modify API veya cancel+place) yapar.

Yani frontlama hem XNL içinde (emir atarken + periyodik FRONT cycle), hem de RevnBookCheck terminalinde (60 sn’lik ayrı döngü) kullanılıyor.

### 4.2 Hangi terminalden frontlama yapılıyor?

- **RevnBookCheck Terminal** ayrı bir process.  
- Başlatma: **baslat.py** menüsünde **12** veya **’r’** ile “RevnBookCheck Terminal” seçilir → `terminals/revnbookcheck_terminal.py` çalışır, içinde `RevnBookCheckTerminal()` oluşturulup `start()` edilir.  
- Bu terminal sadece frontlama değil; fill izleme, REV üretimi, recovery, hesap senkronu (15 sn) da yapar. Frontlama bu terminalin **60 saniyelik** döngüsünde yapılıyor.

### 4.3 Frontlama motoru (FrontlamaEngine)

**Dosya:** `quant_engine/app/terminals/frontlama_engine.py`

- **Girdi:** Emir (symbol, action, price, tag), L1 (bid, ask, spread), truth tick (price, venue, size), exposure_pct.
- **Çıktı:** `FrontlamaDecision`: allowed / red, base_price, front_price, sacrificed_cents, sacrifice_ratio, reason, tag, exposure_pct.
- **Kurallar:** Tag’e göre (LT_*_DEC, MM_*_DEC, LT_*_INC, MM_*_INC) max cent ve max ratio limitleri var; spread &lt; 0.04$ ise frontlama yasak. Fedakârlık **her zaman base price’a göre** ölçülür (mevcut emir fiyatına göre kademeli açılma yok).

---

## 5. Redis ve Veri Akışları

### 5.1 XNL Engine (Backend process) – Redis kullanımı

- XNL **doğrudan Redis’e yazmaz/okumaz**.  
- **L1:** `DataFabric.get_fast_snapshot(symbol)` kullanır. DataFabric backend’de in-memory (L1Cache); L1 verisi L1 Feed Worker veya SnapshotScheduler’ın Redis’e yazdığı `market:l1:{symbol}` ve/veya `market:live:updates` ile güncellenir.  
- **Açık emirler:** `OrderController.get_active_orders(account_id)` – backend’de in-memory (bu process’te atılan/iptal edilen emirler burada tutulur).  
- **Exposure:** `calculate_exposure_for_account(account_id)` – exposure hesaplanır; gerekirse Redis’teki `psfalgo:exposure:{account_id}` ile beslenen bir katmandan okunabilir.

### 5.2 RevnBookCheck Terminal – Redis kullanımı

Terminal ayrı process olduğu için tüm veriyi Redis (ve gerektiğinde HTTP) üzerinden alır:

| Veri            | Redis anahtarı (veya kaynak)        | Yazan / Açıklama |
|-----------------|--------------------------------------|-------------------|
| Aktif hesap     | `psfalgo:recovery:account_open` / `psfalgo:account_mode` | UI connect / account mode |
| Pozisyonlar     | `psfalgo:positions:{account}`        | position_snapshot_api / Position Redis Worker |
| Açık emirler    | `psfalgo:open_orders:{account}`      | position_snapshot_api (snapshot alırken yazar) |
| L1              | `market:l1:{symbol}`                 | L1 Feed Worker, SnapshotScheduler, Truth Ticks Worker |
| Truth tick      | `truthtick:latest:{symbol}`          | Truth Ticks Worker (inspect ile dakikada 1) |
| Exposure        | `psfalgo:exposure:{account}`         | Exposure calculator / backend |
| Fill stream     | `psfalgo:execution:ledger` (stream)   | Execution / fill handler |
| REV emir kuyruğu | `psfalgo:orders:pending` (list)     | RevnBookCheck push; OrderQueueWorker tüketir |

RevnBookCheck:

- Açık emirleri **Redis** `psfalgo:open_orders:{account}` üzerinden okur (backend snapshot yazıyor).  
- L1 için `market:l1:{symbol}`, yoksa `market_data:snapshot:{symbol}` kullanır.  
- Truth tick için `truthtick:latest:{symbol}` (max 5 dk eski kabul edilir).  
- REV emirlerini **Redis kuyruğu** `psfalgo:orders:pending`’e push eder; backend’de **OrderQueueWorker** bu kuyruğu işleyip broker’a gönderir.

### 5.3 Özet veri akışı

- **L1:** Hammer → L1 Feed Worker / SnapshotScheduler / Truth Ticks → Redis `market:l1:{symbol}` (+ isteğe bağlı pub/sub ile DataFabric).  
- **Truth tick:** Hammer → Truth Ticks Worker (inspect) → Redis `truthtick:latest:{symbol}`.  
- **Pozisyon / açık emir:** Broker (IBKR/Hammer) → Backend position_snapshot_api / snapshot → Redis `psfalgo:positions:{account}`, `psfalgo:open_orders:{account}`.  
- **Exposure:** Backend’de hesaplanır → Redis `psfalgo:exposure:{account}`.  
- **XNL:** Aynı backend process’te DataFabric + OrderController kullanır; Redis’e doğrudan bağlı değil.  
- **RevnBookCheck:** Hep Redis (ve gerektiğinde HTTP fallback) kullanır; frontlama 60 sn’de bir bu verilerle çalışır.

---

## 6. Döngülerin Çalışma Sırası (Zaman çizelgesi)

- **t = 0 (XNL Start):**  
  - Initial cycle başlar (LT_TRIM → KARBOTU → ADDNEWPOS → MM → birleştir → frontlama ile gönder).  
  - Aynı anda her kategori için `_front_cycle_loop` ve `_refresh_cycle_loop` task’ları **sleep** içinde beklemeye başlar.

- **FRONT loop (ör. LT_DECREASE, 2 dk):**  
  - 2 dakika uyur → uyanır → `_execute_front_cycle(LT_DECREASE)` → bu kategorideki açık emirleri OrderController’dan alır → her biri için frontlama değerlendir → uygunsa modify (cancel+replace).

- **REFRESH loop (ör. LT_DECREASE, 5 dk):**  
  - 5 dakika uyur → uyanır → `_execute_refresh_cycle(LT_DECREASE)` → bu kategorideki emirleri iptal et → `_run_lt_trim` + `_run_karbotu` ile yeniden hesapla → `_send_orders_with_frontlama` ile tekrar gönder.

- **RevnBookCheck (ayrı process):**  
  - 60 sn’de bir `_run_frontlama_cycle` → Redis’ten açık emirler + L1 + truth tick + exposure → tüm emirler için frontlama değerlendir → uygunsa modify (HTTP API veya cancel+place).

---

## 7. Özet Tablo

| Konu | XNL Engine (Backend) | RevnBookCheck Terminal |
|------|----------------------|-------------------------|
| **Process** | Ana backend (FastAPI) | Ayrı process (baslat 12 / 'r') |
| **Frontlama** | Emir gönderirken + FRONT cycle (kategori bazlı 2–3.5 dk) | 60 sn’de bir tüm açık emirler |
| **L1** | DataFabric (in-memory) | Redis `market:l1:{symbol}` |
| **Açık emirler** | OrderController (in-memory) | Redis `psfalgo:open_orders:{account}` |
| **Döngü süreleri** | FRONT: 2–3.5 dk, REFRESH: 1–8 dk (kategoriye göre) | Frontlama: 60 sn |
| **Emir gönderimi** | `_place_order` (IBKR/Hammer) | REV → Redis queue → OrderQueueWorker |

Bu yapı ile XNL döngüsü, frontlama kontrolü, hangi terminalden nasıl yapıldığı ve Redis/veri akışları tek bir dokümanda toplanmış oluyor.
