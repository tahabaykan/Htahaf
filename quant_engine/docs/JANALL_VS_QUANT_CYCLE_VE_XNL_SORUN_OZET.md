# Janall vs Quant Engine: Cycle Mantığı, RUNALL vs XNL ve “XNL Olmuyor” Sorunu

Bu doküman üç konuyu netleştirir:
1. **Janall’da RUNALL cycle mantığı** nasıl çalışıyordu ve neden sorun çıkarmıyordu.
2. **quant_engine’de RUNALL** ile **XNL** arasındaki mantık farkları.
3. **PSFALGO sayfasında “Run All”** yapıldığında ikisinde ne oluyor; **XNL run ettigimde neden olmuyor** ve bu döngüyü kurmamızı ne engelliyor.

---

## 1) Janall’da RUNALL Cycle Mantığı (Referans)

### Akış (sıralı, bayraklı)

```
RUNALL Başlat
    → runall_loop_count++
    → Adım 1: Lot Bölücü (checkbox)
    → Adım 2: Controller ON (CSV: befibgun/befibped/befham)
    → Adım 3: Exposure (pot_total, pot_max) → Mode: OFANSIF / DEFANSIF / GECIS
    → Adım 4: Mode’a göre KARBOTU veya REDUCEMORE başlat (non‑blocking)
         runall_waiting_for_karbotu = True  veya  runall_waiting_for_reducemore = True
    → KARBOTU/REDUCEMORE BİTİNCE (callback):
         runall_check_karbotu_and_addnewpos() [500ms sonra]
         → Exposure kontrolü: pot_total < pot_max ise ADDNEWPOS tetikle
    → ADDNEWPOS bitince → Qpcal (Spread Kusu)
    → 2 dakika bekle → runall_cancel_orders_and_restart() → Yeni döngü
```

Özet:
- **Sıralı**: Önce KARBOTU veya REDUCEMORE biter, **sonra** ADDNEWPOS tetiklenir.
- **Bayraklar**: `runall_waiting_for_karbotu`, `runall_addnewpos_triggered` vb. ile “kim bitti, sırada ne var” takip edilir.
- **Exposure her adımda**: KARBOTU/ADD tetiklemeden önce exposure kontrolü var.
- **Tek döngü süresi**: Emir + 2 dk bekleme + iptal → kabaca 3–4 dakika.

Bu yapı “RUNALL = tek büyük cycle” gibi düşünülebilir; janall’da **RUNALL** ile “hepsini bir döngüde çalıştır” eşdeğerdi ve bu yüzden sorun çıkmıyordu.

---

## 2) Quant Engine’de RUNALL Mantığı

### Kaynak

- `quant_engine/app/psfalgo/runall_engine.py` → `RunallEngine`
- Tetikleme: PSFALGO API `POST /api/psfalgo/runall/start` → `RunallStateAPI.start_runall()` → `RunallEngine.start()` → `_cycle_loop()`

### Akış (tek döngü, paralel, tam veri hazırlığı)

```
_cycle_loop():
    while loop_running:
        run_single_cycle()
        await asyncio.sleep(cycle_interval_seconds)  # varsayılan 60 sn

run_single_cycle():
    1) Runtime kontrol (system_enabled, lt_trim_enabled, karbotu_enabled)
    2) Cancel‑all: LT bekleyen emirler iptal
    3) request = _prepare_request(account_id)   ← KRİTİK
    4) request is None ise çık
    5) (Opsiyonel) FastScoreCalculator.update_security_contexts()
    6) Paralel çalıştır:
       - KARBOTU  (get_karbotu_engine().run(request, rules))
       - REDUCEMORE
       - ADDNEWPOS (addnewpos_decision_engine(request))
       - MM (get_greatest_mm_decision_engine().run(request))
    7) LT_TRIM (get_lt_trim_engine().run(request, ...))
    8) Conflict resolution, Proposal engine/store’a yazım
    9) Cycle log / Redis diagnostic
```

**_prepare_request() ne yapıyor (RUNALL’ın “veri hazırlığı”):**

- `position_snapshot_api.get_position_snapshot(account_id)`
- `static_store` + JFIN aday semboller
- **DataFabric → market_data_cache** senkronizasyonu (LIFELESS/LIVE)
- **Janall metrics**: `compute_batch_metrics` → GORT, Fbtot, SFStot
- **MarketSnapshotStore** güncellemesi
- `metrics_snapshot_api.get_metrics_snapshot(all_symbols)`
- **Janall cache’ten enrich**: ask_sell_pahalilik, bid_buy_ucuzluk vb.
- **Exposure**: `exposure_calculator.calculate_exposure(positions)`
- `DecisionRequest(positions, metrics, l1_data, exposure, available_symbols)`

Yani RUNALL, motorlara **dolu metrics, exposure ve JFIN adayları** ile istek gönderir.

Farklar (Janall’a göre):

- **Sıra**: Janall’da KARBOTU biter → ADD; quant’ta aynı cycle içinde KARBOTU / REDUCEMORE / ADDNEWPOS **paralel**.
- **Süre**: Janall ~3–4 dk; quant `cycle_interval_seconds` (örn. 60 sn) ile periyodik.
- **Veri**: Quant’ta cycle başında tüm “Janall tarzı” hazırlık (GORT/Fbtot/SFStot, exposure) **tek yerden** `_prepare_request()` ile yapılıyor.

---

## 3) Quant Engine’de XNL Mantığı ve “RUNALL = XNL” Karşılığı

### Kavram eşlemesi

- Janall’da **RUNALL** ≈ “hepsini bir döngüde çalıştır”.
- Quant’ta buna en yakın kullanım:
  - **RUNALL** = sürekli dönen cycle (RunallEngine).
  - **XNL** = ayrı bir “cycle manager”; tasarım olarak RUNALL’a benzer “hepsini çalıştır” amacına sahip ama **ayrı kod yolu**.

Yani “RUNALL = XNL” derken: janall’daki “run all” davranışını quant’ta **ya RUNALL ya XNL** ile vermeye çalışıyoruz; şu an ikisi farklı borular.

### XNL tetikleme

- **API**: `POST /api/xnl/start` → `xnl_routes.start_xnl_engine()` → `XNLEngine.start()`
- **UI**: PSFALGO sayfasındaki “Start XNL” → `handleStartXnl()` → `/api/xnl/start`

### XNL akışı

```
start():
    1) _run_initial_cycle()   ← İlk ve tek “tam tur”
    2) Sonra sadece _front_cycle_loop / _refresh_cycle_loop task’ları (kategori bazlı)

_run_initial_cycle():
    Phase 1: _run_lt_trim(account_id)
    Phase 2: _run_karbotu(account_id)
    Phase 3: _run_addnewpos(account_id)
    Phase 4: _run_mm(account_id)
    → all_orders birleştir → _send_orders_with_frontlama(all_orders, account_id)
```

Her phase’te kullanılan istek:

- `_run_lt_trim`:  
  `DecisionRequest(positions=snapshots, metrics={}, exposure=None, correlation_id=...)`
- `_run_karbotu`:  
  Aynı şekilde `metrics={}`, `exposure=None`
- `_run_addnewpos`:  
  Yine `positions` var ama **metrics/exposure dolu değil**

Yani XNL’in “ilk tur”unda motorlara giden **metrics ve exposure boş**.

Ek farklar:

- **Motor sürümleri**: RUNALL `get_karbotu_engine()` / `get_reducemore_engine()` kullanıyor; XNL **karbotu_engine_v2** ve **reducemore_engine_v2** kullanıyor.
- **Proposal tarafı**: RUNALL, proposal_engine + proposal_store ile önerileri yazıyor; XNL öneri üretmeden doğrudan `_send_orders_with_frontlama` ile emir göndermeye gidiyor. Arayüzde “proposal” görüntüleyen kısım RUNALL cycle’ına bağlı olduğu için XNL tarafında “bir şey çıkmıyor” hissedilebilir.
- **Veri hazırlığı**: XNL, RUNALL’daki `_prepare_request()` benzeri bir adım **hiç kullanmıyor**. Ne Janall metrics, ne market cache sync, ne exposure hesaplaması, ne `get_metrics_snapshot()` initial cycle’da yok.

---

## 4) “XNL Run Ettigimde Olmuyor” — Nedenleri

### 4.1) Metrics ve exposure boş (ana sebep)

- LT_TRIM / KARBOTU / ADDNEWPOS kuralları **Fbtot, GORT, SFStot, pahalılık/ucuzluk, exposure** üzerinden çalışıyor.
- XNL ilk cycle’da `metrics={}`, `exposure=None` veriyor.
- Sonuç: motorlar ya hiç karar üretmiyor ya da anlamsız/boş çıktı veriyor → “olmuyor” hissi.

### 4.2) Veri hazırlığı eksik

- RUNALL’da olanlar:
  - DataFabric → market_data_cache sync
  - Janall metrics (GORT/Fbtot/SFStot)
  - MarketSnapshotStore güncellemesi
  - metrics_snapshot + Janall enrich
  - exposure
- XNL’de bunlar **initial cycle** için yok. (XNL’in front/refresh loop’larında `get_metrics_snapshot` kullanılan yerler var ama ilk “run” dediğin anda çalışan `_run_initial_cycle` bu hazırlıktan yararlanmıyor.)

### 4.3) Proposal / UI yolu

- RUNALL: intents → proposal_engine → proposal_store → UI’da “öneriler” görünür.
- XNL: Proposal store’a yazmıyor; doğrudan emir gönderimine gidiyor. Bu yüzden “XNL çalıştı” desen bile PSFALGO tarafında proposal listesi dolmuyor; kullanıcı “hiçbir şey olmuyor” diyebilir.

### 4.4) Motor sürümleri (v1 vs v2)

- RUNALL: karbotu_engine, reducemore_engine (v1).
- XNL: karbotu_engine_v2, reducemore_engine_v2.
- Arayüz ve kontrat farkları (intent vs decision, run imzası) ek uyumsuzluk kaynağı olabilir; asıl kırıcı olan yine boş metrics/exposure.

### 4.5) Cycle mantığı farkı (döngü kurmak)

- Janall: Tek RUNALL döngüsü, sıralı adımlar, bayraklarla “KARBOTU bitti → ADDNEWPOS”.
- Quant RUNALL: Her N saniyede bir “tek cycle” içinde her şey paralel; “KARBOTU bitti sonra ADD” sırası yok ama en azından **tek bir veri hazırlığı + tek bir cycle** var.
- Quant XNL: “Initial cycle” bir kere çalışıyor, sonra front/refresh task’ları **aynı hazırlıkla** beslenmiyor; ilk cycle da hazırlıksız. Yani “RUNALL benzeri güvenilir bir döngü” XNL tarafında tam kurulmamış.

Özetle “bu tarz bir döngü kurmamız engelleniyor” derken:
- XNL’de **RUNALL’daki gibi ortak, dolu bir request hazırlığı** yok.
- İlk cycle metrics/exposure olmadan çalıştığı için motorlar anlamlı çıktı üretmiyor.
- Proposal/UI yolu RUNALL’a bağlı; XNL ayrı bir kanal ve orada “görünen” bir çıktı yok.

---

## 5) PSFALGO Sayfasında “Run All” Yapıldığında İkisinde Ne Oluyor?

### RUNALL (Start RUNALL)

1. `POST /api/psfalgo/runall/start` çağrılır.
2. `RunallStateAPI.start_runall()` → `RunallEngine.start()` → `_cycle_loop()` başlar.
3. Her `cycle_interval_seconds`’da bir `run_single_cycle()`:
   - `_prepare_request()` ile dolu request (positions, metrics, exposure, JFIN adayları),
   - KARBOTU / REDUCEMORE / ADDNEWPOS / MM paralel, sonra LT_TRIM,
   - Proposal’lar store’a yazılır, UI güncellenir.

### XNL (Start XNL)

1. `POST /api/xnl/start` çağrılır.
2. `XNLEngine.start()` → `_run_initial_cycle()`:
   - Her phase **boş metrics, exposure=None** ile çalışır.
   - Motorlar anlamlı karar üretmez.
   - Varsa birkaç emir `_send_orders_with_frontlama` ile gider; proposal tarafı dolmaz.
3. Sonrasında front/refresh loop’ları çalışır ama ilk “run” zaten veri açısından zayıf.

Yani “run all” denince:
- **RUNALL** ile: Tam veri hazırlığı + proposal’lar + UI’da görünen cycle.
- **XNL** ile: Eksik veri + proposal’sız + UI’da belirgin bir şey olmaması → “olmuyor”.

---

## 6) Düzene Sokmak İçin Ne Yapılabilir?

### Seçenek A: XNL’i RUNALL’ın veri katmanına bağlamak (önerilen)

- XNL’in `_run_initial_cycle()` (ve mümkünse front/refresh cycle’ları) **tek bir “hazırlık” fonksiyonundan** beslenmeli.
- Bu hazırlık, RUNALL’daki `_prepare_request()` ile aynı işi yapmalı:
  - position_snapshot
  - DataFabric / market_data_cache sync
  - Janall metrics + MarketSnapshotStore
  - metrics_snapshot + enrich
  - exposure
  - `DecisionRequest(positions, metrics, l1_data, exposure, available_symbols)`.

Pratik yol:

- `RunallEngine._prepare_request()` çağrılabilir ve yeniden kullanılabilir hale getirilir (örn. modül seviyesinde veya paylaşılan bir “cycle request preparer”).
- XNL, `_run_lt_trim` / `_run_karbotu` / `_run_addnewpos` / `_run_mm` öncesi **tek seferde** bu preparer’dan `request` alır; phase’lere `request.positions`, `request.metrics`, `request.exposure` geçer.
- Böylece “XNL run” = RUNALL ile aynı kalitede veriyle çalışan bir cycle.

### Seçenek B: Motor ve proposal tutarlılığı

- XNL’de RUNALL ile aynı motor seti kullanılabilir (v1 karbotu/reducemore) ya da v2 kullanılacaksa request/response formatı RUNALL ile uyumlu hale getirilir.
- İstenirse XNL ürettiği intents/decisions’ı RUNALL’daki gibi proposal_engine + proposal_store’a da yazabilir; böylece “Start XNL” denince de UI’da öneriler görünür.

### Seçenek C: “RUNALL = XNL” tek buton

- Psflagoda tek “Run All” butonu:
  - Ya sadece RUNALL’ı başlatır (mevcut davranış),
  - Ya da “XNL modu” varsa XNL’i başlatır ama XNL artık A+B ile RUNALL ile aynı veri ve aynı proposal yolunu kullanır.

Bu sayede janall’daki “RUNALL = hepsini çalıştır” davranışı, quant’ta hem RUNALL hem XNL ile tutarlı ve sorun çıkarmayan bir döngüye dönüştürülebilir.

---

## 7) Kısa Özet Tablo

| Konu | Janall RUNALL | Quant RUNALL | Quant XNL |
|------|----------------|-------------|-----------|
| Tetikleme | RUNALL butonu / döngü | `POST /api/psfalgo/runall/start` | `POST /api/xnl/start` |
| Sıra | KARBOTU bitir → ADDNEWPOS | Aynı cycle’da paralel | Initial: sıralı phase’ler, sonra front/refresh |
| Veri hazırlığı | UI/thread/callback ile veri akar | _prepare_request: positions, metrics, exposure, Janall, cache | Yok (metrics={}, exposure=None) |
| Metrics / exposure | Var | Dolu | İlk cycle boş |
| Proposal / UI | Onay penceresi, emirler | proposal_store → UI | Yok, doğrudan emir yolu |
| Motor | KARBOTU / REDUCEMORE worker | karbotu_engine, reducemore_engine | karbotu_v2, reducemore_v2 |
| “Olmuyor” sebebi | — | — | Boş metrics/exposure + hazırlık yok + proposal yok |

Bu doküman, mevcut kod (runall_engine.py, xnl_engine.py, janall RUNALL açıklamaları ve JANALL_VS_QUANT_MAPPING_REPORT) ile uyumlu olacak şekilde yazıldı. İstersen bir sonraki adımda XNL’e “RUNALL _prepare_request kullan” patch’i için somut fonksiyon/çağrı yerleri de çıkarılabilir.
