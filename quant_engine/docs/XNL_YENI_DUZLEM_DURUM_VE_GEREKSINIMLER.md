# XNL — Yeni Düzlemde Durum, Gereksinimler ve “Çalışır mı?”

Bu doküman, 3-hesap düzleminde **XNL’in şu anki durumunu**, **çalıştırmak için nelerin gerekli olduğunu** ve **“Şu an çalışır mı, çalışırsa/çalışmazsa ne olur?”** sorularını net yanıtlar.

---

## 1) Bu yeni düzlemde sorunumuz var mı?

**Hesap tarafı:** Hayır. XNL zaten aktif hesaba göre çalışıyor:

- `_run_initial_cycle()` içinde `account_id = get_trading_context().trading_mode.value` alınıyor.
- LT_TRIM, KARBOTU, ADDNEWPOS, MM hepsi bu `account_id` ile:
  - `get_position_snapshot(account_id=account_id)` kullanıyor,
  - emirler `_send_orders_with_frontlama(..., account_id)` ile gönderiliyor.
- Yani **hangi hesap açıksa, XNL o hesabın pozisyonlarına/emirlerine bakıyor** — burada yeni düzlemle uyumsuzluk yok.

**Asıl sorun:** Hesap değil, **veri hazırlığı**. XNL motorlara (LT_TRIM, KARBOTU, ADDNEWPOS, MM) **boş metrics ve exposure** veriyor. Kurallar bu verilere göre karar verdiği için XNL “düzgün çalışmıyor” gibi görünüyor.

---

## 2) Şu an XNL çalışır mı?

**Teknik olarak çalışır:** Start XNL deyince motorlar çalışır, pozisyonlar okunur, bazı emirler üretilip gönderilebilir. Yani process hata verip durmaz.

**Anlamlı sonuç vermez:** Çünkü:

- **metrics={}** → GORT, Fbtot, SFStot, pahalılık/ucuzluk yok.
- **exposure=None** → OFANSIF/DEFANSIF/geçiş kararı exposure’a göre; exposure olmayınca KARBOTU vs REDUCEMORE seçimi ve “ne kadar açılacak” mantığı boş kalır.
- Motorlar bu yüzden ya hiç karar üretmez ya da kurallara uymayan/rastgele hissi veren çıktı üretir.

Özet: **“Çalışır” ama “doğru/anlamlı çalışmaz**.**

---

## 3) Çalışırsa ne olur? (Mevcut davranış)

Şu anki kodla “Start XNL” dediğinde olanlar:

1. **İlk cycle (`_run_initial_cycle`):**
   - `account_id = get_trading_context().trading_mode.value` → Doğru hesap seçilir.
   - Her phase (LT_TRIM, KARBOTU, ADDNEWPOS, MM) kendi `DecisionRequest(positions=snapshots, metrics={}, exposure=None)` ile çalışır.
   - Pozisyonlar **aktif hesaba** göre gelir (doğru).
   - Metrics ve exposure boş olduğu için motorlar ya az karar üretir ya da “exposure mode” vb. yanlış/eksik çıkar.
   - Üretilen emirler `_send_orders_with_frontlama(all_orders, account_id)` ile **aktif hesaba** gider (doğru).

2. **Sonrasında:**
   - FRONT cycle / REFRESH cycle task’ları çalışır; bunlar mevcut emirleri frontlama/refresh eder.
   - Yine hesap `account_id` üzerinden doğru kullanılır.

3. **UI tarafı:**
   - XNL, proposal_store’a yazmıyor; öneriler doğrudan emir olarak gönderiliyor.
   - Bu yüzden PSFALGO’da “öneri listesi” XNL’den dolmaz; RUNALL’da dolar, XNL’de boş kalır.
   - Kullanıcı “XNL çalıştı ama ekranda bir şey yok” diye algılayabilir.

Yani: **Hesap ve emir yönü doğru;** fakat **karar kalitesi düşük (metrics/exposure yok)** ve **öneri ekranı XNL’den beslenmiyor.**

---

## 4) Çalışmazsa sebebi nedir?

“Çalışmaz” derken kastettiğin:

- **“Anlamlı emir üretmiyor / kurallara uygun davranmıyor”**  
  → Sebep: **Veri hazırlığı yok.** XNL, RUNALL’daki gibi `_prepare_request` kullanmıyor; metrics (GORT, Fbtot, SFStot, pahalılık/ucuzluk) ve exposure hesaplanmıyor. Motorlar bu olmadan doğru karar veremez.

- **“Proposal / öneri ekranında bir şey göremiyorum”**  
  → Sebep: **Proposal store’a yazılmıyor.** XNL öneri üretip store’a yazmıyor; doğrudan emir gönderiyor. UI sadece proposal_store’u gösterdiği için XNL’den gelenleri görmezsin.

- **“OFF/ON veya OFANSIF/DEFANSIF yanlış”**  
  → Sebep: **exposure=None.** REDUCEMORE/KARBOTU exposure’a göre mod seçiyor; exposure üretilmediği için bu mantık devre dışı kalıyor.

Kısa cevap: **Asıl sebep, XNL’in RUNALL’daki “dolu request hazırlığı”nı (metrics + exposure + Janall/cache sync) kullanmaması.**

---

## 5) XNL’i bu düzlemde düzgün çalıştırmak için neler lazım?

### 5.1) Veri hazırlığını RUNALL ile ortaklaştırmak (şart)

- XNL’in ilk cycle’ı (ve mümkünse front/refresh cycle’ları) **RUNALL’daki `_prepare_request(account_id)` ile aynı veriyi** kullanmalı.
- Yani:
  - `position_snapshot(account_id)` (zaten var),
  - DataFabric / market_data_cache senkronu,
  - Janall metrics (GORT, Fbtot, SFStot),
  - MarketSnapshotStore güncellemesi,
  - `get_metrics_snapshot(all_symbols)` + Janall enrich,
  - `exposure_calculator.calculate_exposure(positions)` (veya account’lı variant),
  - `DecisionRequest(positions, metrics, l1_data, exposure, available_symbols)`.

Pratik yol:

- `RunallEngine._prepare_request(account_id, correlation_id)` dışarıdan çağrılabilir hale getirilir **veya** aynı işi yapan paylaşılan bir fonksiyon (örn. `prepare_cycle_request(account_id)`) yazılır.
- XNL, `_run_initial_cycle` başında **tek seferde** bu preparer’dan `request` alır; `_run_lt_trim`, `_run_karbotu`, `_run_addnewpos`, `_run_mm` artık kendi içinde boş request üretmez, hepsi bu `request` ile çalışır.

Bunu yapınca “metrics/exposure boş” sebebi ortadan kalkar.

### 5.2) İsteğe bağlı: Proposal / UI

- XNL’in ürettiği kararlar (intent/decision) **proposal_engine + proposal_store**’a yazılırsa, PSFALGO’daki öneri sekmeleri XNL’den de dolar; “çalıştı ama ekranda bir şey yok” hissi kalkar.
- Bu, özellikle “önce öneri göster, sonra onayla gönder” akışını XNL’de de kullanmak istersen gerekli.

### 5.3) Zaten uyumlu olanlar

- **Hesap:** `get_trading_context().trading_mode.value` kullanılıyor; yeni 3-hesap düzlemiyle uyumlu.
- **Pozisyonlar:** `get_position_snapshot(account_id=account_id)` ile aktif hesaba göre.
- **Emir gönderimi:** `_send_orders_with_frontlama(..., account_id)` ile aktif hesaba gidiyor.
- **RevnBookCheck:** Hesabı `psfalgo:trading:account_mode` (veya senkron bir key) ile okuyorsa, XNL’in gönderdiği emirler yine doğru hesapta takip edilir.

Yani **“XNL’i bu yeni düzlemde çalıştırmak için”** ekstra hesap/pozisyon tarafı iş yok; asıl eksiği **ortak, dolu request hazırlığı** tamamlamak.

---

## 6) Kısa cevap tablosu

| Soru | Cevap |
|------|--------|
| Bu yeni düzlemde XNL tarafında hesap/pozisyon sorunu var mı? | Hayır. XNL zaten aktif hesaba (`trading_mode`) göre pozisyon alıyor ve emir gönderiyor. |
| XNL şu an “çalışır” mı? | Process çalışır; motorlar ve emir gönderimi çalışır. Anlamlı/doğru karar vermez. |
| Çalışırsa ne olur? | Aktif hesaba göre pozisyon alınır, az/yanlış karar üretilir, emirler yine o hesaba gider; proposal listesi dolmaz. |
| Çalışmazsa / anlamsızsa sebebi? | Metrics ve exposure verilmiyor; XNL RUNALL’daki `_prepare_request` benzeri hazırlığı kullanmıyor. |
| XNL’i düzgün çalıştırmak için neler lazım? | (1) İlk (ve mümkünse sonraki) cycle’da RUNALL ile aynı veri hazırlığını kullanmak. (2) İstenirse proposal_store’a yazmak. |

---

## 7) Son cümle

**Yeni 3-hesap düzleminde XNL’in hesaba duyarlılığı tamam.** Eksik olan, motorları **dolu metrics ve exposure** ile besleyen ortak hazırlık. Bunu RUNALL’daki `_prepare_request` (veya eşdeğer bir `prepare_cycle_request`) ile XNL’e bağladığında, XNL de “hangi hesap açıksa ona göre” hem doğru veriyle hem de anlamlı şekilde çalışır.

Bu doküman, `JANALL_VS_QUANT_CYCLE_VE_XNL_SORUN_OZET.md` ve `XNL_EMIR_ONERISI_AKIS_TASARIMI.md` ile uyumludur.

---

## 8) Yapılan Uygulama (5.1 tamamlandı)

- **RunallEngine.prepare_cycle_request(account_id, correlation_id=None):** Eklendi. RUNALL’daki `_prepare_request` ile aynı veriyi üretir; XNL ve diğer çağıranlar bu public method’u kullanır.
- **XNL _run_initial_cycle:** Başta `get_runall_engine().prepare_cycle_request(account_id, correlation_id)` ile request alıyor. None ise cycle atlanıyor. Aynı request LT_TRIM, KARBOTU, ADDNEWPOS, MM phase’lerine geçiriliyor.
- **XNL _run_lt_trim(account_id, request):** Kendi positions/metrics/exposure üretmiyor; gelen `request` kullanılıyor.
- **XNL _run_karbotu(account_id, request):** Aynı şekilde paylaşılan `request` kullanılıyor.
- **XNL _run_addnewpos(account_id, request):** Aynı şekilde paylaşılan `request` kullanılıyor.
- **XNL _run_mm(account_id, request):** Pozisyon/metrics/L1/exposure/available_symbols artık RUNALL preparer’dan gelen `request` ile besleniyor; MM engine doğrudan bu request ile çalışıyor.

Böylece XNL ilk cycle’da RUNALL ile aynı veri katmanını (metrics, exposure, Janall, market cache) kullanıyor; motorlar dolu metrics ve exposure ile çalışıyor.

---

## 9) XNL → proposal_store yazımı (5.2) — karışmaz, tekrar olmaz

- **Cycle ayırımı:** XNL proposal’ları `cycle_id = -1` ile yazılıyor. RUNALL her zaman pozitif `loop_count` kullanıyor; ortak alan karışmıyor.
- **Tekrarları engelleme:** XNL yeni batch yazmadan önce `proposal_store.clear_pending_proposals_with_cycle_id(-1)` çağrılıyor. Böylece sadece **önceki XNL batch’i** silinir; RUNALL’ın proposal’ları hiç silinmez. Her XNL initial cycle, kendi eski batch’ini replacement yapar, aynı emirler üst üste binmez.
- **Store tarafı:** `ProposalStore.clear_pending_proposals_with_cycle_id(cycle_id)` eklendi; sadece `cycle_id`’si eşleşen PENDING proposal’lar silinir.
- **Engine isimleri:** XNL, RUNALL ile aynı `decision_source` kullanıyor (LT_TRIM, KARBOTU, ADDNEWPOS_ENGINE, GREATEST_MM); sekmeler birebir aynı, ekstra karışıklık yok. Aynı (symbol, side, engine, qty, price) için `_remove_existing_similar_proposal` zaten tekil kayıt garantisi veriyor.
- **Özet:** Öneri sekmelerinde aynı emirler birebir tekrar tekrar çıkmaz; XNL kendi batch’ini her seferinde replace eder, RUNALL batch’i ayrı kalır.
