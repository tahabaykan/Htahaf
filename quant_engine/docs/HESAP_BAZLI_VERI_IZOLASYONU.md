# Hesap Bazlı Veri İzolasyonu — Tasarım ve Uygulama

Bu doküman, **3 hesabın** (HAMPRO, IBKR_GUN, IBKR_PED) tam izolasyonunu ve “kullanıcının tıkladığı hesap = o anda aktif” mantığının her yere kodlanmasını tanımlar.

---

## 1) Özet: Ne İstiyoruz?

- **3 ayrı hesap:** HAMPRO, IBKR_GUN, IBKR_PED. Kullanıcı hangisine tıklarsa o **aktif**.
- **Aktif hesap** = o anda tüm emir/pozisyon/BEFDAY/exposure/XNL cycle işlemleri **sadece o hesaba** ait veri ile yapılır.
- **Market data (L1 bid/ask vb.)** = **hiç değişmez**. Hep **Hammer Pro** üzerinden gelir. Hesap değişince sadece **emirler ve pozisyonlar** değişir; fiyat/piyasa verisi aynı kalır.
- **BEFDAY, emirler, pozisyonlar, MAX_EXPOSURE, XNL cycle** = hesaba göre ayrı key/CSV ile takip edilir. Redis/CSV yazarken okurken **hesap adı** kullanılır.
- **Hesap değişince:** Eski hesabın XNL/cycle’ı durur; kullanıcı isterse **yeni hesabın** cycle’ını başlatır. Tüm yeni işlemler yeni hesaba göre yapılır.

---

## 2) Kritik Ayrım: Market Data vs Hesap Verisi

| Veri | Kaynak | Hesap değişince değişir mi? | Nerede saklanır / nasıl erişilir? |
|------|--------|-----------------------------|-----------------------------------|
| **L1 bid/ask/last, volume** | **Hammer Pro** (sabit) | **Hayır** | DataFabric, market_data_cache, Hammer feed. Hesap parametresi yok. |
| **Pozisyonlar (current)** | Broker (Hammer veya IBKR) | **Evet** | Hesap bazlı: IBKR_GUN → IBKR connector, HAMPRO → Hammer positions. Redis: `psfalgo:positions:{account_id}`. |
| **Potential (açık emirlerden)** | Aynı broker, o hesabın emirleri | **Evet** | Hesap bazlı. Pozisyon snapshot API `account_id` ile çağrılır. |
| **BEFDAY** | CSV (hesap başına dosya) | **Evet** | befham.csv (HAMPRO), befibgun.csv (IBKR_GUN), befibped.csv (IBKR_PED). Redis: `psfalgo:befday:positions:{account_id}`. |
| **Filled / Pending orders** | Broker (o hesap) | **Evet** | Hesap bazlı: `account_id` ile connector/API çağrısı. |
| **MAX_EXPOSURE / exposure** | Pozisyonlardan hesaplanan | **Evet** | Hesap bazlı. Redis: `psfalgo:exposure:{account_id}`. |
| **XNL cycle state** | Motor state | **Evet** | Hesap bazlı: hangi hesap aktifse o hesabın cycle’ı çalışır; hesap değişince önceki durur. |

Yani: **Market data tarafı hiç değişmez; hesap değişince sadece emirler ve pozisyonlarla ilgili her şey o hesaba göre olur.**

---

## 3) Redis Key Kuralları (Hesap Bazlı)

Aşağıdaki veriler **hesap bazlı** key kullanmalı. `{account_id}` = `HAMPRO` | `IBKR_GUN` | `IBKR_PED`.

| Veri | Redis key (hesap bazlı) | Okuma/yazma |
|------|--------------------------|-------------|
| Aktif hesap (tek kaynak) | `psfalgo:trading:account_mode` | Tüm yazma: UI/trading_context. Tüm okuma: context, RevnBookCheck, execution. |
| Pozisyonlar | `psfalgo:positions:{account_id}` | Yaz: pozisyon snapshot/connector güncellerken. Oku: position_snapshot_api, RevnBookCheck, exposure. |
| BEFDAY pozisyonları | `psfalgo:befday:positions:{account_id}` | Yaz: BEFDAY track sonrası (hesap bazlı). Oku: position_snapshot_api._load_befday_map(account_id), RevnBookCheck. |
| Exposure | `psfalgo:exposure:{account_id}` | Yaz: exposure calculator (o hesap için). Oku: UI, XNL, RUNALL, RevnBookCheck. |
| XNL cycle state (opsiyonel) | `psfalgo:xnl:state:{account_id}` | İleride XNL durumu hesap bazlı saklanırsa. |

**Eski / yanlış:**  
- `psfalgo:befday:positions` (hesapsız) → **Kaldırılacak / kullanılmayacak.** Yerine `psfalgo:befday:positions:{account_id}`.  
- `psfalgo:account_mode` (JSON) → **Tek kaynak** `psfalgo:trading:account_mode` olacak; RevnBookCheck ve diğerleri bu key’i okuyacak.

---

## 4) CSV Kuralları (Hesap Bazlı)

| Hesap | BEFDAY CSV | Açıklama |
|-------|------------|----------|
| HAMPRO | befham.csv | Hammer Pro pozisyonları |
| IBKR_GUN | befibgun.csv | IBKR GUN pozisyonları |
| IBKR_PED | befibped.csv | IBKR PED pozisyonları |

BEFDAY tracker zaten `mode` (`hampro` / `ibkr_gun` / `ibkr_ped`) ile doğru dosyayı kullanıyor. Tüm BEFDAY okuyan yerler (position_snapshot_api, RevnBookCheck, vb.) **hangi hesabın aktif olduğuna** göre doğru CSV’yi (veya Redis’teki hesap-bazlı key’i) kullanmalı.

---

## 5) “Aktif Hesap” Akışı

1. **Tek kaynak:** `TradingAccountContext.trading_mode` (Redis: `psfalgo:trading:account_mode`). UI’da kullanıcı HAMPRO / IBKR_GUN / IBKR_PED seçer → bu değer yazılır.
2. **Tüm hesap gerektiren işlemler:** Pozisyon, emir, BEFDAY, exposure, XNL, RUNALL, RevnBookCheck → **her zaman** `get_trading_context().trading_mode.value` (veya Redis’ten bu değer) ile `account_id` alır; API/Redis/CSV erişiminde bu `account_id` kullanılır.
3. **Hesap değiştiğinde:**
   - Önceki hesabın XNL/cycle’ı **durur** (tek orchestrator varsa loop “active account” değişince o hesabın cycle’ını bırakır).
   - Yeni hesap aktif olur; bir sonraki “positions / orders / BEFDAY / exposure” isteği **yeni** `account_id` ile yapılır.
   - Kullanıcı isterse **yeni hesabın** XNL/cycle’ını başlatır.

---

## 6) Nerede Hesap Bazlı Olmalı? (Kontrol Listesi)

- **Position snapshot API:** `get_position_snapshot(account_id=...)` → zaten var. Çağıran her yerde `account_id = get_trading_context().trading_mode.value` kullanılmalı.
- **BEFDAY yükleme:** `_load_befday_map(account_id)` → CSV hesap bazlı. Redis key `psfalgo:befday:positions:{account_id}` olmalı (şu an `psfalgo:befday:positions` kullanılıyor → düzeltilecek).
- **Exposure:** Zaten `account_id` ile hesaplanıyorsa tamam. Redis’e yazarken `psfalgo:exposure:{account_id}` kullanılmalı (RevnBookCheck’te öyle).
- **Emirler (get_open_orders, place_order, cancel):** Hep ilgili broker/connector’a `account_id` ile gidilmeli; connector seçimi `account_id`’den çıkar (HAMPRO → Hammer, IBKR_* → ilgili IBKR connector).
- **RevnBookCheck:** `_get_account_mode()` → `psfalgo:trading:account_mode` (veya get_trading_context) kullanmalı. Pozisyon/BEFDAY/exposure okurken `self.account_mode` (yani aktif hesap) ile hesap-bazlı key kullanmalı; BEFDAY için `psfalgo:befday:positions:{self.account_mode}`.
- **XNL / RUNALL:** Cycle başında ve emir/pozisyon/exposure her çağrıda `account_id = get_trading_context().trading_mode.value` kullanmalı.
- **UI:** Pozisyon, emir, BEFDAY, exposure, öneri listesi isterken backend’e **aktif hesap** gönderilmeli (veya backend zaten `psfalgo:trading:account_mode` okuyorsa tek kaynaktan alır).

---

## 7) Uygulama Sırası (Kod Değişiklikleri)

### Adım 1: Redis BEFDAY key’ini hesap bazlı yap

- **position_snapshot_api._load_befday_map(account_id):**  
  Redis key: `psfalgo:befday:positions` → `psfalgo:befday:positions:{account_id}`.  
  Oku: `redis.get("psfalgo:befday:positions:" + account_id)` (veya f-string). Böylece her hesabın BEFDAY’i ayrı key’de.
- **RevnBookCheck _get_befday_data / BEFDAY okuma:**  
  `psfalgo:befday:positions` → `psfalgo:befday:positions:{self.account_mode}`.
- **BEFDAY yazan yerler (varsa):**  
  Hesap bilgisi ile yazıyorsa key’i `psfalgo:befday:positions:{account_id}` yapın.

### Adım 2: Tek hesap kaynağı — RevnBookCheck

- **RevnBookCheck _get_account_mode():**  
  `psfalgo:account_mode` (JSON) yerine `psfalgo:trading:account_mode` oku (string). Değerleri aynı tut: HAMPRO, IBKR_GUN, IBKR_PED.  
  Böylece UI/ExecutionRouter ile aynı kaynak kullanılır.
- **Periyodik güncelleme:**  
  Döngü içinde periyodik olarak `_get_account_mode()` çağırıp `self.account_mode` güncellensin; hesap değişince bir sonraki okumada doğru hesaba geçilsin.

### Adım 3: Tüm “account_id” kullanımlarında aktif hesap

- **XNL, RUNALL, execution, proposal, exposure:**  
  `account_id` nereden geliyorsa, tek kaynak `get_trading_context().trading_mode.value` olsun. Çağıran yer parametreyi buradan geçirsin.
- **UI’dan gelen istekler:**  
  Örneğin “pozisyonlar”, “emirler”, “exposure” isteğinde backend, `psfalgo:trading:account_mode` (veya TradingAccountContext) ile aktif hesabı alsın; tüm cevaplar o hesaba göre üretilsin.

### Adım 4: Hesap değişince XNL/cycle durdurma

- **RUNALL / XNL cycle loop:**  
  Her cycle başında (veya belirli aralıklarla) `current = get_trading_context().trading_mode.value` alınsın. Başlangıçta `_active_account_at_start = current` tutulur.  
  Loop içinde `current != _active_account_at_start` ise döngü **break** veya “pause” edilir (bu cycle’ı atla, dur). Böylece kullanıcı hesap değiştirdiğinde o hesabın cycle’ı durur.
- **Yeni hesap cycle’ı:**  
  Kullanıcı “Start XNL” / “Start RUNALL” dediğinde, o anda aktif olan hesap için cycle başlar (zaten `account_id = get_trading_context().trading_mode.value` kullanılıyorsa doğru hesap kullanılır).

### Adım 5: UI — “Aktif hesap” seçici

- PSFALGO veya ana layout’ta **HAMPRO / IBKR_GUN / IBKR_PED** seçeni olsun. Seçim → `POST /api/psfalgo/account/mode` veya TradingAccountContext’i güncelleyen endpoint ile `psfalgo:trading:account_mode` Redis’e yazılsın.
- Tüm “pozisyon / emir / BEFDAY / exposure / öneri” istekleri bu aktif hesaba göre yapılsın (backend tek kaynaktan okursa ek parametre gerekmez; istersen query param `?account_id=...` ile override da tanımlanabilir, varsayılan = Redis’teki aktif hesap).

---

## 8) Özet: “Bu Mantık Her Yerde” Ne Demek?

- **3 hesap:** HAMPRO, IBKR_GUN, IBKR_PED. Biri “aktif”.
- **Market data:** Hep Hammer; hesap değişmez, L1 bid/ask vs. hep aynı.
- **Hesap verisi:** Pozisyon, emir, BEFDAY, exposure, XNL cycle → hesap bazlı key/CSV ve `account_id` ile API.
- **Redis:**  
  - `psfalgo:trading:account_mode` = aktif hesap (tek kaynak).  
  - `psfalgo:positions:{account_id}`, `psfalgo:befday:positions:{account_id}`, `psfalgo:exposure:{account_id}`.
- **CSV:** befham.csv, befibgun.csv, befibped.csv → hesap bazlı.
- **Hesap değişince:** Eski hesabın XNL/cycle’ı durur; yeni işlemler yeni hesaba göre; kullanıcı isterse yeni hesabın cycle’ını başlatır.

Bu kurallar **heryere kodlanmalı**: position_snapshot_api, BEFDAY okuyan/yazan yerler, exposure, emir/pozisyon API’leri, XNL, RUNALL, RevnBookCheck ve UI’daki hesap seçici.

Bu doküman, mevcut kod yapısı (position_snapshot_api, befday_tracker, RevnBookCheck, trading_context, runtime_controls) ile uyumlu olacak şekilde yazıldı. İlk somut değişiklik: Redis BEFDAY key’inin hesap bazlı kullanılması (position_snapshot_api ve RevnBookCheck).
