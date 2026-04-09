# Yapıyı Bozabilecek Satırlar – İnceleme ve Düzeltmeler

Bu dokümanda Dual Process / XNL / hesap geçişleri / MinMax ile ilgili **yapıyı bozabilecek** satırlar tek tek ele alındı; yapılan düzeltmeler ve hâlâ dikkat edilmesi gereken noktalar listeleniyor.

---

## 1. Refresh cycle vs “toptan cancel”

**Durum:** “Refresh cycle’ı kaldırdık, yerine toptan cancel atıyoruz” ifadesi.

**Eski davranış:** XNL start edildiğinde hem **front cycle** hem **refresh cycle** task’ları oluşturuluyordu. Refresh cycle her N dakikada o kategorideki emirleri iptal edip yeniden hesaplayıp gönderiyordu.

**Şu an (düzeltme sonrası):**
- **Refresh cycle task’ları kaldırıldı.** XNL start’ta sadece `_front_cycle_loop(category)` task’ları oluşturuluyor; `_refresh_cycle_loop` artık hiç başlatılmıyor.
- “Toptan cancel” zaten Dual Process tarafında yapılıyor: Her hesaba geçerken `cancel_by_filter(account_id, "tum", False)` çağrılıyor. Manuel kullanımda da “c TUM” ile toptan iptal mümkün.
- **Sonuç:** Evet, şu an yapı “refresh cycle yok, toptan cancel var” şeklinde. Kod buna göre güncellendi.

**Dosya:** `quant_engine/app/xnl/xnl_engine.py` – `start()` içinde refresh task oluşturan blok kaldırıldı; yorumda “Refresh cycle KALDIRILDI” açıklaması eklendi.

---

## 2. MinMax “neden olmadi” – Tespit ve düzeltmeler

**Olası sebepler:**

### 2.1 CSV fallback hesap karışması

**Sorun:** `_send_orders_with_frontlama` içinde `get_all_rows(account_id)` sonrası cache boşsa `load_from_csv()` çağrılıyordu. CSV hesap-bağımsız tek dosya; son “MinMax Area” hangi hesap için çalıştırıldıysa onun verisi yazılıyor. Başka hesap için emir gönderilirken cache boş kalırsa CSV’den doldurulunca **yanlış hesabın** current_qty/befday_qty değerleri kullanılabiliyordu.

**Düzeltme:** XNL tarafında CSV fallback kaldırıldı. Sadece `get_all_rows(account_id)` kullanılıyor; cache boşsa boş kalıyor, `get_row(account_id, symbol)` tek sembol için `compute_for_account(account_id, symbols=[symbol])` ile Redis’ten o hesabın verisini alıyor.

**Dosya:** `quant_engine/app/xnl/xnl_engine.py` – `if not minmax_svc._cache: minmax_svc.load_from_csv()` satırı silindi.

### 2.2 Boş compute ve eski cache

**Sorun:** `compute_for_account(account_id)` sembol listesi boş veya veri yoksa `rows = []` dönüyordu; `_cache` ve `_cache_account` güncellenmediği için bir önceki hesabın cache’i kullanılabiliyordu.

**Düzeltme:** `compute_for_account` sonunda her durumda `_cache_account = account_id` atanıyor; `rows` boşsa `_cache = {}` yapılıyor. Böylece “bu hesap için veri yok” durumu net; eski hesabın cache’i kullanılmıyor.

**Dosya:** `quant_engine/app/psfalgo/minmax_area_service.py` – `compute_for_account` sonuna `if not rows: self._cache = {}` eklendi.

### 2.3 load_from_csv sonrası cache_account

**Sorun:** `load_from_csv()` cache’i dolduruyordu ama `_cache_account` set etmiyordu. CSV’den yüklenen veri başka yerden (ör. UI) kullanılsa bile, `get_row(account_id, symbol)` ile doğrulama yapılırken “cache hangi hesaba ait?” bilgisi yanlış kalabiliyordu.

**Düzeltme:** `load_from_csv()` sonunda `_cache_account = None` atanıyor. Böylece herhangi bir `get_row(account_id, symbol)` çağrısında `_cache_account != account_id` (None != account_id) olduğu için o hesap için yeniden `compute_for_account(account_id, symbols=[symbol])` çalışıyor; doğrulama her zaman ilgili hesabın Redis verisiyle yapılıyor.

**Dosya:** `quant_engine/app/psfalgo/minmax_area_service.py` – `load_from_csv` sonuna `self._cache_account = None` eklendi.

### 2.4 BEFDAY / pozisyon kaynağı

MinMax, `compute_for_account` içinde:
- `psfalgo:positions:{account_id}` (Redis) ile **current** ve varsa **befday** alıyor;
- BEFDAY yoksa `PositionSnapshotAPI._load_befday_map(account_id)` kullanılıyor.

Hesap geçişinde Redis’in doğru güncellenmesi için: XNL initial cycle başlamadan önce `prepare_cycle_request(account_id)` çağrılıyor; bu da `get_position_snapshot(account_id)` ile broker’dan pozisyon çekip Redis’e yazıyor. Dual Process’te sıra: `set_trading_mode(account_a)` → `cancel_by_filter(...)` → `engine.start()` → `_run_initial_cycle()` → `prepare_cycle_request(account_id)` → pozisyonlar o hesap için güncelleniyor. Yani **doğru hesabın** BEFDAY/current verisi MinMax’e girmesi bu akışa bağlı; bu akış şu an doğru.

**Öneri:** BEFDAY/INTRADAY widget’ında gördüğün değerlerin, o anki `trading_mode` (aktif hesap) ile uyumlu olduğundan emin ol; hesap değiştirdikten sonra bir kez pozisyon yenileme (veya MinMax Area butonu) o hesap için Redis’i günceller.

---

## 3. Hesap aktif mod ve geçişler

### 3.1 Tek kaynak: Redis

- Aktif hesap: `psfalgo:trading:account_mode` (TradingAccountContext; set_trading_mode ile yazılıyor).
- Dual Process her hesaba geçerken `ctx.set_trading_mode(to_mode(account_a))` / `account_b` çağırıyor; tüm sonraki okumalar bu hesabı kullanıyor.

### 3.2 Pozisyon / emir verisi

- Pozisyonlar: `psfalgo:positions:{account_id}`.
- Açık emirler: `psfalgo:open_orders:{account_id}` + broker.
- `get_position_snapshot(account_id)`, `cancel_by_filter(account_id, ...)`, `_place_order(..., account_id)` hep parametre olarak **o anki** account_id kullanıyor; XNL içinde bu `ctx.trading_mode.value` ile dolduruluyor.

### 3.3 MinMax

- `get_all_rows(account_id)` / `get_row(account_id, symbol)` / `validate_order_against_minmax(account_id, ...)` hep account_id ile çağrılıyor; cache ve CSV düzeltmeleriyle hesap karışması engellendi.

### 3.4 Exposure / frontlama

- `calculate_exposure_for_account(account_id)` ve frontlama değerlendirmesi XNL’de `account_id` ile yapılıyor; hesap izolasyonu korunuyor.

**Potansiyel risk:** Başka bir modül (worker, terminal) `get_trading_context().trading_mode` yerine sabit bir hesap kullanıyorsa karışma olabilir. Böyle bir kullanım tespit edilmedi; ileride yeni kod eklenirken dikkat edilmeli.

---

## 4. Diğer kritik satırlar (kontrol edildi, sorun yok)

| Konu | Dosya / yer | Durum |
|------|-------------|--------|
| XNL stop RUNALL’ı durduruyor | xnl_engine.py `stop()` | Bilinçli: XNL koşarken RUNALL döngüsü aynı anda koşmasın diye. Dual Process’te XNL periyodik start/stop olduğu için RUNALL da durur; beklenen davranış. |
| Front/refresh task’lar hesap okuması | `_execute_front_cycle` / `_execute_refresh_cycle` | Her çağrıda `account_id = ctx.trading_mode.value`; hesap geçişinde doğru hesap kullanılır. |
| prepare_cycle_request | runall_engine.py | `account_id` parametreyle geliyor; pozisyon/metrik/exposure o hesaba göre. |
| cancel_by_filter | xnl_engine.py | `account_id` parametreyle broker + Redis’ten o hesabın emirleri alınıp iptal ediliyor. |
| _place_order | xnl_engine.py | HAMPRO vs IBKR branch’i `account_id` ile; doğru execution path. |

---

## 5. Özet

- **Refresh cycle:** Kaldırıldı; sadece front cycle çalışıyor. “Toptan cancel” Dual Process (ve manuel TUM) ile yapılıyor; mevcut yapı buna uygun.
- **MinMax:** CSV fallback XNL’den kaldırıldı; boş compute’da cache temizlenip hesaba kilitleme eklendi; `load_from_csv` sonrası `_cache_account = None` ile hesap-bağımsız cache işaretlendi. Böylece “neden olmadi” riski (yanlış hesap verisi) azaltıldı.
- **Hesap geçişleri:** Tüm ilgili yerlerde `account_id` / `trading_mode` tutarlı kullanılıyor; ek bir “yapıyı bozan” satır tespit edilmedi.

BEFDAY/INTRADAY widget’ında gördüğün değerlerin doğru hesaba ait olduğundan emin olmak için: o sayfada hangi hesabın aktif olduğunu kontrol et; gerekirse hesap seçip bir kez pozisyon yenile (veya MinMax Area’yı o hesap için çalıştır).
