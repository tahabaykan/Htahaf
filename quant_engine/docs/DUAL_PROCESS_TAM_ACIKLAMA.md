# DUAL PROCESS – Sıfırdan Tam Açıklama

Bu dokümanda “Dual Process Start” dediğinde ne olduğu, hangi kuralların/limitlerin/koşulların devreye girdiği, emirlerin nasıl üretilip nasıl gönderildiği, frontlama/REV/minmax gibi kontrollerin ne zaman ve nasıl yapıldığı **sayılar ve formüllerle** anlatılıyor. Hiçbir şey bilmeyen birine anlatır gibi, satır satır kod mantığına uygun yazıldı.

---

## 1. DUAL PROCESS NEDİR?

İki hesabı (örneğin **IBKR_PED** ve **HAMPRO**) sırayla kullanarak XNL döngüsünü çalıştıran bir “orchestrator”dur.

- **Hesap A**’ya geç → O hesaptaki **tüm açık emirleri iptal et (Cancel All / tum)** → **XNL’i başlat** → **3.5 dakika bekle** (en uzun front cycle) → **XNL’i durdur** (emirler olduğu gibi kalır).
- **Hesap B**’ye geç → Aynı adımlar (Cancel All → XNL Start → 3.5 dk bekle → XNL Stop).
- Bu döngü **“Stop Dual Process”**’e basılana kadar tekrarlanır.

Yani: Her hesapta sadece **bir kerelik tam XNL cycle + bir en uzun front cycle (3.5 dk)** çalışır; sonra diğer hesaba geçilir. Bağlantılar (Hammer / IBKR) mod değişince kapatılmaz; sadece **hangi hesabın verisi/emri kullanılacağı** (trading_mode) değişir.

---

## 2. BUTONA BASILINCA NE OLUYOR? (Adım adım)

### 2.1 Frontend

- **Scanner** veya **PSFALGO** sayfasında **“Dual Process”** butonuna basılır.
- Varsayılan hesaplar: `account_a = "IBKR_PED"`, `account_b = "HAMPRO"`.
- İstek: `POST /api/xnl/dual-process/start` body: `{ "account_a": "IBKR_PED", "account_b": "HAMPRO" }`.

### 2.2 API (xnl_routes.py)

- `start_dual_process(request)` → `get_dual_process_runner().start(request.account_a, request.account_b)` çağrılır.
- Runner `account_a` / `account_b` değerlerini büyük harf ve boşluksuz alır; geçerlilik: `HAMPRO`, `IBKR_PED`, `IBKR_GUN`; ikisi farklı olmalı.

### 2.3 Dual Process Runner (dual_process_runner.py)

- **State:** `DualProcessState.RUNNING`, `current_account = account_a`, `loop_count = 0`.
- Arka planda `_run_loop()` adlı bir **asyncio task** başlatılır; API hemen döner.

**`_run_loop()` içinde döngü (özet):**

1. **Hesap A (ör. IBKR_PED):**
   - `ctx.set_trading_mode(TradingAccountMode.IBKR_PED)` → Redis’e `psfalgo:trading:account_mode = "IBKR_PED"` yazılır; tüm sonraki veri/emir bu hesaba göre olur.
   - `engine.cancel_by_filter(account_a, "tum", False)` → Bu hesaptaki **tüm** açık emirler broker üzerinden iptal edilir (filter `tum` = hepsi; `rev_excluded=False` → REV’li emirler de iptal).
   - `engine.start()` → **XNL Engine** başlatılır (aşağıda detay).
   - `_sleep_longest_front_cycle()` → **210 saniye (3.5 dakika)** beklenir; her 5 saniyede `_stop_requested` kontrol edilir.
   - `engine.stop()` → XNL durdurulur; emirler **iptal edilmez**, sadece XNL’in front/refresh task’ları iptal edilir.

2. **Hesap B (ör. HAMPRO):**
   - `ctx.set_trading_mode(TradingAccountMode.HAMPRO)`.
   - `engine.cancel_by_filter(account_b, "tum", False)` → HAMPRO’daki tüm açık emirler iptal.
   - `engine.start()` → XNL tekrar başlar (bu sefer HAMPRO için).
   - 3.5 dk bekle → `engine.stop()`.

3. `loop_count += 1` ve döngü tekrarlanır; `_stop_requested` True olana kadar.

**Sayılar:**

- `LONGEST_FRONT_CYCLE_SECONDS = CYCLE_TIMINGS[OrderTagCategory.LT_INCREASE].front_cycle_seconds` → **210.0** (3.5 × 60).
- `STOP_CHECK_INTERVAL_SECONDS = 5.0` → Stop’a basıldığında en fazla ~5 sn içinde döngü kırılır.

---

## 3. XNL ENGINE START – NE YAPIYOR?

### 3.1 start() (xnl_engine.py)

- State `RUNNING` yapılır; `_stop_event` temizlenir.
- **Her kategori için** (LT_INCREASE, LT_DECREASE, MM_INCREASE, MM_DECREASE) `CYCLE_TIMINGS` ve `active`/MM ayarına göre:
  - **Front cycle task:** `_front_cycle_loop(category)` → Her `front_cycle_seconds` saniyede bir `_execute_front_cycle(category)` çalışır.
  - **Refresh cycle task:** `_refresh_cycle_loop(category)` → Her `refresh_cycle_seconds` saniyede bir `_execute_refresh_cycle(category)` çalışır.
- **Initial cycle** ayrı bir task’ta çalışır: `_run_initial_then_log()` → `_run_initial_cycle()`.

Yani: Start’ta hem **ilk tur emir üretimi + gönderimi** (initial cycle) hem de **periyodik front/refresh** döngüleri başlar.

### 3.2 Cycle süreleri (sayılarla)

| Kategori     | Front cycle (sn) | Refresh cycle (sn) | Aktif |
|-------------|-------------------|--------------------|--------|
| LT_INCREASE | **210** (3.5 dk) | 480 (8 dk)         | Evet   |
| LT_DECREASE | 120 (2 dk)       | 300 (5 dk)         | Evet   |
| MM_INCREASE | 120 (2 dk)       | 180 (3 dk)         | MM açıksa |
| MM_DECREASE | 30               | 60                 | Hayır (varsayılan) |

Dual Process’te “en uzun front cycle” = **LT_INCREASE = 210 sn** baz alınıyor; bu süre dolunca o hesapta XNL işi bitmiş sayılıyor.

---

## 4. İNİTİAL CYCLE – EMİRLER NASIL ÜRETİLİYOR?

`_run_initial_cycle()` şu sırayla çalışır:

1. **Hesap:** `account_id = get_trading_context().trading_mode.value` (Dual Process tarafından zaten A veya B yapılmış).
2. **Ortak request:** `request = await get_runall_engine().prepare_cycle_request(account_id, correlation_id)`.
   - Bu request: pozisyonlar, metrikler, exposure, L1 verisi, Janall/JFIN adayları vs. içerir; RUNALL ile aynı veri katmanı kullanılır.
3. **Faz 1 – LT_TRIM:** `lt_trim_orders = await _run_lt_trim(account_id, request)`.
4. **Faz 2 – KARBOTU/REDUCEMORE:** `karbotu_orders = await _run_karbotu(account_id, request)`.
5. **Faz 3 – ADDNEWPOS:** `addnewpos_orders = await _run_addnewpos(account_id, request)`.
6. **Faz 4 – MM:** `mm_orders = await _run_mm(account_id, request)`.
7. **Birleştir / dedupe:** Aynı (symbol, action) için öncelik: LT_TRIM > KARBOTU > ADDNEWPOS > MM; sadece ilk gelen tutulur.
8. **Gönderim:** `await _send_orders_with_frontlama(all_orders, account_id)`.
9. **Cycle state:** Tüm kategoriler için `last_front_cycle` ve `last_refresh_cycle` şu anki zamana set edilir.

Aşağıda her faz ve “gönderim” kısmı kısaca özetleniyor; kurallar ve sayılar belirtiliyor.

---

## 5. prepare_cycle_request – ORTAK VERİ KAYNAĞI

RUNALL’ın `_prepare_request` (veya `prepare_cycle_request`) şunları yapar:

- **Pozisyonlar:** `PositionSnapshotAPI.get_position_snapshot(account_id)` (Redis/broker; hesap izole).
- **Metrikler:** `MetricsSnapshotAPI` + Janall batch metrikleri (GORT, FBtot, SFStot vb.); DataFabric / market_data_cache ile.
- **Exposure:** `ExposureCalculator` (pot_total, pot_max).
- **L1:** DataFabric / Hammer L1 (bid, ask, last).
- **JFIN adayları:** StaticDataStore’dan sembol listesi; metrikler bu semboller için de hesaplanır.

XNL, bu request’i **değiştirmez**; sadece tüketir. Yani emirler **o anki hesaba (account_id)** ve **o anki piyasa/pozisyon verisine** göre üretilir.

---

## 6. FAZ 1 – LT_TRIM

- **Motor:** `get_lt_trim_engine().run(request, ..., controls, account_id)`.
- **Girdi:** request (positions, metrics, exposure, L1), runtime controls (lt_trim_enabled vb.).
- **Çıktı:** Intent listesi (symbol, action, qty, price, classification/tag).

XNL tarafında her intent için:

- L1 yoksa sembol atlanır.
- `action` (BUY/SELL), `qty`, `price`, `tag` (örn. LT_LONG_DEC) alınır; `category = OrderTagCategory.LT_DECREASE`.
- Emir listesine eklenir.

LT_TRIM pozisyon **azaltma** (trim) kararları üretir; tag’ler LT_*_DEC tarafındadır.

---

## 7. FAZ 2 – KARBOTU / REDUCEMORE

- **Reducemore:** `get_reducemore_engine_v2().run(request)` → exposure modu (OFANSIF vb.) çıkar.
- **Sadece OFANSIF ise** KARBOTU çalışır: `get_karbotu_engine_v2().run(request)` → `decisions` (symbol, action, qty, tag).
- Her decision için L1 kontrolü; yoksa atlanır. Tag’ler yine LT_*_DEC; `category = LT_DECREASE`.

KARBOTU da azaltma (kar alma / risk azaltma) emirleri üretir.

---

## 8. FAZ 3 – ADDNEWPOS

- **Ayar:** `get_addnewpos_settings_store().get_settings()`; `enabled` kapalıysa boş döner.
- **Motor:** `get_addnewpos_engine().addnewpos_decision_engine(request)`.
- **Filtreler:**
  - `mode`: `both` / `addlong_only` / `addshort_only`; buna göre BUY/SELL elenir.
  - **Pool:** order_type’tan BB/FB/SAS/SFS; pool’a göre `tab_settings[pool].jfin_pct` (örn. %50) uygulanır.
  - **Lot:** `final_lot = int(original_lot * (jfin_pct / 100.0))`; 0 ise atlanır.
- **L1** yoksa sembol atlanır.
- Tag: LT_LONG_INC / LT_SHORT_INC tarafı; `category = OrderTagCategory.LT_INCREASE`.

**Formül:** `final_lot = floor(calculated_lot * jfin_pct / 100)`; jfin_pct 0 ise o pool devre dışı.

---

## 9. FAZ 4 – MM (GREATEST MM)

- **Ayar:** `get_mm_settings_store().get_settings()`; `enabled` kapalıysa boş döner.
- **Motor:** `get_greatest_mm_decision_engine().run(request)`.
- **Stok sayısı:** `est_cur_ratio` (varsayılan 44), `min_stock_count`, `max_stock_count`, `lot_per_stock` (varsayılan 200).
  - `adjusted_count = clamp(default_count * (est_cur_ratio / 44), min_stock_count, max_stock_count)`; long ve short için ayrı ayrı en yüksek skorlu N hisse seçilir.
- **Fiyat (long):** `price_hint` yoksa `bid + spread * 0.15`.
- **Fiyat (short):** `price_hint` yoksa `ask - spread * 0.15`.
- **Miktar:** Her MM emri `lot_per_stock` (200) lot.
- Tag: MM_LONG_INCREASE / MM_SHORT_INCREASE; `category = OrderTagCategory.MM_INCREASE`.

---

## 10. GÖNDERİM – _send_orders_with_frontlama

Tüm emirler **gönderilmeden önce** sırayla şu kontrollerden geçer:

### 10.1 L1

- `_get_l1_data(symbol)` (DataFabric / Hammer); yoksa emir atlanır.

### 10.2 Base price (XNL tarafında)

- BUY: `base_price = bid + (spread * 0.15)`
- SELL: `base_price = ask - (spread * 0.15)`
- `spread = ask - bid` (veya en az 0.01).

### 10.3 Frontlama değerlendirmesi

- **Frontlama motoru:** `get_frontlama_engine().evaluate_order_for_frontlama(order_dict, l1_dict, truth_last, ..., exposure_pct)`.
- **Truth tick:** L1’deki `last` (veya ayrı truth tick kaynağı); frontlama için “son anlamlı işlem” fiyatı.
- **Çıktı:** `FrontlamaDecision`: `allowed`, `front_price`, `base_price`, `sacrificed_cents`, `sacrifice_ratio`, `reason`, `tag`.

**Frontlama kuralları (frontlama_engine.py):**

1. **Spread:** `spread >= 0.04` olmalı; değilse frontlama **yasak** (SPREAD_TOO_TIGHT).
2. **Truth tick:** Geçerli olmalı (venue/size kuralları: FNRA 100/200, diğer venue size ≥ 15).
3. **Front fiyat (1 tick):**
   - SELL: `front_price = truth_last - 0.01`
   - BUY:  `front_price = truth_last + 0.01`
4. **Fedakârlık (her zaman base’e göre):**
   - `sacrificed_cents = |base_price - front_price|`
   - `sacrifice_ratio = sacrificed_cents / spread`
5. **Tag’e göre limitler (BASE_LIMITS):**

   | Tag tipi   | max_cent_limit | max_ratio_limit |
   |------------|----------------|-----------------|
   | MM_*_DEC  | 0.60 $         | 50%             |
   | LT_*_DEC  | 0.35 $         | 25%             |
   | LT_*_INC  | 0.10 $         | 10%             |
   | MM_*_INC  | 0.07 $         | 7%              |

   Hem `sacrificed_cents <= max_cent_limit` hem `sacrifice_ratio <= max_ratio_limit` sağlanmalı.
6. **Exposure:** Yüksek exposure’da INCREASE tag’leri bloklanabilir (`_get_adjusted_limits`).
7. **İyileştirme:** Front fiyat, mevcut emir fiyatına göre “daha iyi” olmalı (daha erken dolma ihtimali).

Sonuçta:

- `allowed` ve `front_price` varsa → **final_price = front_price** (round 2 ondalık).
- Değilse → **final_price = base_price**.

### 10.4 MinMax Area kontrolü

- **Servis:** `get_minmax_area_service()`; satırlar `get_row(account_id, symbol)` veya CSV’den.
- **Fonksiyon:** `validate_order_against_minmax(account_id, symbol, action, quantity, current_qty, minmax_row, minmax_service)`.

**Mantık:**

- `potential_qty = current_qty + signed_change` (BUY → +qty, SELL → -qty).
- **Band:** `todays_min_qty <= potential_qty <= todays_max_qty` (BEFDAY + MAXALW + portfolio limitlerinden hesaplanan günlük min/max).
- Band dışına taşıyorsa **qty kırpılır** (trim); kırpılmış miktar 0 veya “artış” yönünde 200’den küçükse emir **bloklanır**.
- **Minimum artış lotu:** Pozisyon artırma emirleri (long ekleme veya short ekleme) en az **MIN_LOT_INCREASE = 200** lot olmalı; trim sonrası 200’ün altına düşerse emir gönderilmez.

Dönüş: `(allowed, adjusted_qty, reason)`; allowed False ise emir atlanır; True ve adjusted_qty != quantity ise emir adjusted_qty ile gönderilir.

### 10.5 Emri broker’a gönderme

- **Hammer (HAMPRO):** `get_hammer_execution_service().place_order(symbol, side, quantity, price, order_style='LIMIT', hidden=True, strategy_tag=tag)`.
- **IBKR (IBKR_PED/IBKR_GUN):** `get_ibkr_connector(account_type=account_id).place_order(contract_details, order_details)` (LMT, strategy_tag).
- Gönderim sonrası **rate limit:** `await asyncio.sleep(0.035)` (~saniyede ~28 emir üst sınırı).

---

## 11. FRONT CYCLE (Periyodik frontlama)

Her kategori için `_front_cycle_loop(category)`:

- `await asyncio.sleep(timing.front_cycle_seconds)` (LT_INCREASE için 210 sn, LT_DECREASE için 120 sn, vb.).
- Sonra `_execute_front_cycle(category)`:
  - **Hesap:** `get_trading_context().trading_mode.value`.
  - **Açık emirler:** `_get_open_orders_by_category(category, account_id)` (broker’dan alınan emirler; tag/category eşleşmesi).
  - Her emir için L1 + frontlama değerlendirmesi; `allowed` ve `front_price` varsa ve mevcut fiyattan en az 0.01 fark varsa → **iptal + aynı sembol/yön/miktar ile front_price’ta yeniden place** (cancel-replace).
- Böylece açık emirler periyodik olarak “truth’a 1 tick yakın” fiyata çekilir; limitler yine aynı tag kurallarıyla (cent + ratio) uygulanır.

Dual Process’te 3.5 dk bekleme, bu front cycle’ların en az bir kez (özellikle LT_INCREASE için) dönmesi için yeterli süre olarak kullanılıyor.

---

## 12. REFRESH CYCLE

`_execute_refresh_cycle(category)`:

- O kategorideki **açık emirler** broker’dan alınır; hepsi iptal edilir.
- Yeni request: `prepare_cycle_request(account_id, ...)`.
- O kategoriye ait yeni emirler üretilir (LT_TRIM / KARBOTU / ADDNEWPOS / MM’den ilgili olanlar); tekrar `_send_orders_with_frontlama` ile gönderilir.

Dual Process 3.5 dk’da refresh cycle’ı beklemek zorunda değil; sadece “en uzun front cycle” (210 sn) dolunca o hesabı bitirip diğerine geçiyor.

---

## 13. CANCEL BY FILTER (tum)

Dual Process her hesaba geçerken **Cancel All** yapar:

- `cancel_by_filter(account_id, "tum", False)`.
- **Kaynak:** `_get_broker_open_orders(account_id)` (Hammer veya IBKR + Redis open_orders).
- **Filter “tum”:** Tüm emirler seçilir (`matches_filter(..., "tum")` → True).
- **rev_excluded=False:** REV’li emirler de iptal edilir.
- Her emir için `_cancel_order(order_id, account_id)`; başarılı iptaller sayılır; IBKR tarafında Redis open_orders listesi güncellenir (iptal edilen ID’ler çıkarılır).

---

## 14. REV ORDER, FRONTLAMA ÖZET

- **REV:** Emir tag’inde “REV” geçen (recovery vb.) emirler; `rev_excluded=True` ile cancel’da hariç tutulabilir. Dual Process’te `rev_excluded=False` kullanıldığı için REV’li emirler de “tum” ile iptal edilir.
- **Frontlama:** Yukarıda anlatıldığı gibi; base price (spread × 0.15), truth ± 0.01, tag’e göre cent/ratio limitleri ve exposure ile kontrol edilir; hem ilk gönderimde hem front cycle’da uygulanır.

---

## 15. YAPIYI BOZABİLECEK SATIRLAR / KONTROL LİSTESİ

Kod taramasında dikkat edilmesi gereken noktalar:

1. **Hesap bağımlılığı:**  
   Tüm `account_id` / `ctx.trading_mode.value` kullanımları Dual Process’in set ettiği hesaba bağlı. `prepare_cycle_request`, `get_position_snapshot`, `get_open_orders`, `cancel_by_filter`, `_place_order`, `calculate_exposure_for_account`, MinMax `get_row(account_id, symbol)` hep **o anki hesabı** kullanmalı. Redis key’lerinde `account_id` kullanılıyor (örn. `psfalgo:positions:{account_id}`, `psfalgo:open_orders:{account_id}`); karışma olmamalı.

2. **XNL stop() RUNALL’ı durduruyor:**  
   `xnl_engine.stop()` içinde `get_runall_engine().stop()` çağrısı var. Dual Process, XNL’i periyodik start/stop ettiği için, aynı anda **manuel RUNALL** çalıştırıyorsanız, XNL stop olduğunda RUNALL da duracaktır. İstenen davranış: XNL çalışırken RUNALL döngüsünün aynı anda koşmaması; buna göre kullanım yapılmalı.

3. **Front/refresh task’lar hesap değişince:**  
   XNL start edildiğinde front/refresh task’ları o anki `account_id`’yi kullanmıyor; her cycle’da `get_trading_context().trading_mode.value` okuyorlar. Dual Process hesap değiştirdiğinde zaten context (Redis) güncellendiği için, bir sonraki XNL start’ı **yeni hesapta** çalışır. Eski hesapta XNL stop edildiği için eski hesaba ait task kalmaz; yapı bozulmaz.

4. **MinMax Area cache:**  
   MinMax satırları `account_id` ile cache’leniyor; `get_row(account_id, symbol)` doğru hesabı döner. CSV tek dosya ise, Dual Process’te hesap A ve B için ayrı ayrı MinMax hesaplatılıp aynı CSV’ye yazılıyorsa, son yazan hesap “üzerine” yazar. Kodda `save_to_csv` account_id ile prefix’lenmiş key veya ayrı dosya kullanmıyorsa, iki hesap aynı CSV’yi paylaşıyor olabilir; bu durumda MinMax’in hangi hesaba göre güncel olduğu kullanım senaryosuna bağlı. Hesap izolasyonu için ileride CSV’yi account_id’ye göre ayırmak (veya cache key’ini account_id ile zenginleştirmek) faydalı olabilir.

5. **Hammer/IBKR bağlantıları:**  
   Mod değişince Hammer veya IBKR bağlantısı koparılmıyor; sadece `trading_mode` değişiyor. IBKR PED/GUN arasında geçişte diğer IBKR hesabı disconnect ediliyor; Dual Process dokümandaki “iki kanal açık” kuralıyla uyumlu.

6. **Dual Process task iptali:**  
   Stop’ta `_stop_requested = True` ve `_run_loop()` döngüden çıkıyor; `engine.stop()` çağrılıyor. XNL stop sırasında tüm front/refresh task’ları cancel ediliyor; bekleyen `asyncio.sleep`’ler 5 sn’lik parçalarla kontrol edildiği için geç kapanma olmaz.

Bu liste, “bu yapıyı bozacak bir satır var mı?” sorusuna yanıt vermek için kullanılabilir; özellikle hesap/context ve RUNALL/XNL yaşam döngüsüne dikkat edilmesi yeterli.

---

## 16. ÖZET TABLO

| Aşama | Ne yapılıyor | Sayı / formül |
|--------|--------------|----------------|
| Dual Process loop | Hesap A → Cancel All → XNL Start → 3.5 dk bekle → XNL Stop; sonra Hesap B aynı | 210 sn bekleme, 5 sn stop kontrolü |
| XNL initial cycle | LT_TRIM → KARBOTU → ADDNEWPOS → MM; dedupe (symbol, action); frontlama + minmax ile gönderim | Öncelik: LT > KARBOTU > ADDNEWPOS > MM |
| Base price | BUY: bid + 0.15×spread; SELL: ask - 0.15×spread | spread = max(ask-bid, 0.01) |
| Front price | BUY: truth_last + 0.01; SELL: truth_last - 0.01 | 1 tick |
| Frontlama spread | spread ≥ 0.04 | Yoksa frontlama yasak |
| Frontlama limitler | LT_INC: 0.10$, 10%; MM_INC: 0.07$, 7%; LT_DEC: 0.35$, 25%; MM_DEC: 0.60$, 50% | Cent ve ratio ikisi de sağlanmalı |
| MinMax | potential_qty ∈ [todays_min_qty, todays_max_qty]; trim gerekirse; artış emirleri ≥ 200 lot | MIN_LOT_INCREASE = 200 |
| ADDNEWPOS lot | final_lot = floor(calculated_lot × jfin_pct / 100) | jfin_pct pool’a göre (BB/FB/SAS/SFS) |
| MM lot | Her emir lot_per_stock (200) | est_cur_ratio ile stok sayısı ayarı |
| Cancel filter tum | Tüm açık emirler; rev_excluded=False → REV’liler de iptal | Broker + Redis open_orders |

Bu doküman, Dual Process’e “sıfırdan” giren biri için tüm akışı, kuralları ve sayıları tek yerde toplar; kodla uyumlu tutulmuştur.
