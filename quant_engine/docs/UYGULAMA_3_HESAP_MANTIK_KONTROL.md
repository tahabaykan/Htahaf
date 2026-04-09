# Uygulama 3-Hesap Mantığı — Doğrulama ve Kontrol

Bu doküman, **tüm uygulamanın** şu mantıkla çalıştığını tanımlar ve kontrol listesini içerir:

- **3 hesap modu:** HAMPRO, IBKR_GUN, IBKR_PED → 3 ayrı emir ve pozisyon bilgi akışı.
- **Market data:** Tek kaynak = **Hammer Pro**. Truth tick, volav, bid, ask, L1, DataFabric, fiyat/skor hesapları hesap değişince **değişmez**.
- **Pozisyon ve emir:** Hesap modu değişince **değişir**. BEFDAY, current/potential pozisyon, filled/pending orders, exposure, Redis key’leri, CSV’ler hep **aktif hesaba** göre.

---

## 1) Kural Özeti

| Veri / Akış | Kaynak / Kural | Hesap değişince |
|-------------|----------------|------------------|
| **L1 bid/ask/last, volume** | Hammer Pro (tek kaynak) | Değişmez |
| **Truth tick, volav, GRPAN, fiyat overlay** | Hammer Pro | Değişmez |
| **DataFabric, market_data_cache, get_fast_snapshot** | Hammer Pro | Değişmez |
| **Janall metrics (GORT, Fbtot, SFStot), skorlar** | Market data + static → Hammer kaynaklı | Değişmez |
| **Pozisyonlar (current, potential)** | Broker: Hammer veya IBKR — hangi hesap aktifse | Değişir |
| **Emirler (filled, pending)** | Aynı broker, o hesap | Değişir |
| **BEFDAY** | befham / befibgun / befibped, Redis `psfalgo:befday:positions:{account_id}` | Değişir |
| **Exposure, MAX_EXPOSURE** | Pozisyonlardan, o hesap | Değişir |
| **Redis:** positions, exposure, befday | `{account_id}` ile key | Değişir |
| **XNL/RUNALL cycle, proposal, execution** | Aktif hesap (`trading_mode`) | Değişir |

---

## 2) Doğrulanan / Düzeltilen Yerler

### 2.1) Market data = tek kaynak (hesap yok)

- **DataFabric** (`app/core/data_fabric.py`): account_id / trading_mode kullanmıyor. L1, skor, get_fast_snapshot hep sembol bazlı. ✅
- **Truth ticks worker:** account/trading_mode referansı yok. ✅
- **L1 feed, Hammer feed/client:** Piyasa verisi; hesap parametresi yok. ✅
- **market_data_routes:** Bid/ask/last, janall metrics, fast_snapshot çağrıları market verisi; batch positions/orders kısmı account_type ile ayrılıyor (doğru). ✅

### 2.2) Pozisyon / emir = hesap bazlı

- **position_snapshot_api.get_position_snapshot(account_id=...):** Zaten hesap bazlı. Çağıranların account_id kullanması gerekiyor. ✅
- **JFIN state endpoint (`/jfin/state`):** `get_position_snapshot()` hesapsız çağrılıyordu → **düzeltildi:** `account_id = get_trading_context().trading_mode.value` ile çağrılıyor. ✅
- **Take-profit longs/shorts:** Pozisyonlar `position_api.get_position_snapshot()` ile alınıyordu, hesap yoktu → **düzeltildi:** `get_long_positions_async(account_id)`, `get_short_positions_async(account_id)` eklendi; route’lar `get_trading_context().trading_mode.value` ile çağırıyor. ✅
- **Exposure calculator:** `calculate_exposure_for_account(account_id)` ve `get_position_snapshot(account_id=account_id)` kullanıyor. ✅
- **RUNALL, XNL, execution_service, RevnBookCheck, trading_routes, qebench:** position_snapshot veya exposure çağrılarında account_id kullanılıyor. ✅

### 2.3) Redis / hesap key’leri

- **BEFDAY:** `psfalgo:befday:positions` → `psfalgo:befday:positions:{account_id}` (position_snapshot_api, RevnBookCheck). ✅
- **Aktif hesap:** `psfalgo:trading:account_mode` tek kaynak; RevnBookCheck bu key’i okuyor. ✅
- **Pozisyonlar / exposure:** RevnBookCheck `psfalgo:positions:{self.account_mode}`, `psfalgo:exposure:{self.account_mode}` kullanıyor. ✅

---

## 3) Kontrol Listesi (Tüm Uygulama)

Aşağıdaki yerlerde mantık şöyle olmalı:

### 3.1) Redis / terminal / veri aktarma

- [ ] **Tüm Redis key’leri:** Pozisyon, emir, BEFDAY, exposure ile ilgili olanlar `{account_id}` içerir. Market data (bid/ask, truth, volav) için hesap key’i **yok**.
- [ ] **RevnBookCheck:** Hesap = `psfalgo:trading:account_mode`; pozisyon/BEFDAY/exposure okurken `self.account_mode` ile hesap bazlı key.
- [ ] **BEFDAY yazan yerler:** Key = `psfalgo:befday:positions:{account_id}` (veya ilgili hesap CSV: befham/befibgun/befibped).

### 3.2) Veri okuma / analiz

- [ ] **Pozisyon okuma:** Her zaman `get_position_snapshot(account_id=...)` veya `account_id = get_trading_context().trading_mode.value` sonra bu değerle çağrı.
- [ ] **Emir okuma:** İlgili broker/connector’a `account_id` ile gidilir (HAMPRO / IBKR_GUN / IBKR_PED).
- [ ] **Market data okuma (bid, ask, truth, volav, skor):** Hesap parametresi yok; DataFabric / Hammer / market_data_routes tek kaynak.

### 3.3) API / route’lar

- [ ] **Pozisyon/emir/exposure/JFIN/take-profit döndüren route’lar:** Aktif hesap = `get_trading_context().trading_mode.value` (veya query’den `account_id` override); backend tüm pozisyon/emir/exposure cevaplarını bu hesaba göre üretir.
- [ ] **Sadece market data döndüren route’lar:** Hesap parametresi kullanılmaz.

### 3.4) MarketSnapshotStore / account_type

- **MarketSnapshotStore** şu an `account_type` ile snapshot tutuyor. İçerik (GORT, Fbtot, SFStot) market verisinden türetildiği için teoride hesapsız da olabilir. Mevcut kullanım yerleri (hangi hesabın “view”ı olduğu) korunacaksa `account_type` bırakılabilir; önemli olan **pozisyon/emir** ile karışmaması. İleride sadeleştirme yapılabilir.

---

## 4) Yapılan Kod Değişiklikleri (Özet)

1. **`app/api/psfalgo_routes.py` — JFIN state:**  
   Position snapshot için `account_id = get_trading_context().trading_mode.value` eklendi; `get_position_snapshot(account_id=account_id)` ile çağrılıyor.

2. **`app/api/psfalgo_routes.py` — Take-profit longs/shorts:**  
   `get_trading_context().trading_mode.value` ile `account_id` alınıyor; `engine.get_long_positions_async(account_id)` / `engine.get_short_positions_async(account_id)` kullanılıyor.

3. **`app/psfalgo/take_profit_engine.py`:**  
   - `get_long_positions_async(account_id)`, `get_short_positions_async(account_id)` eklendi; içeride `await position_api.get_position_snapshot(account_id=account_id)`.  
   - Snapshot dönen liste üzerinden `for pos in snapshot` ile dolaşılıyor (`.positions` kaldırıldı).  
   - Sync `get_long_positions` / `get_short_positions` isteğe bağlı `account_id` alıyor; yoksa `get_trading_context().trading_mode.value` kullanılıyor.

4. **`app/psfalgo/position_snapshot_api.py`:**  
   BEFDAY Redis key’i `psfalgo:befday:positions:{account_id}` olacak şekilde güncellendi (zaten önceki değişiklikte yapıldı).

5. **`app/terminals/revnbookcheck.py`:**  
   BEFDAY key’i `psfalgo:befday:positions:{self.account_mode}`; `_get_account_mode()` önce `psfalgo:trading:account_mode` okuyor (zaten önceki değişiklikte yapıldı).

---

## 5) Unutulmaması Gereken Mantık

- **Tüm market data kaynakları = Hammer Pro.** Truth tick, volav, bid, ask, L1, cache, skorlar hesap modundan bağımsız.
- **Sadece pozisyon ve emir bilgisi (ve bunlardan türeyen BEFDAY, exposure, Redis, CSV, XNL cycle, proposal/execution) hesap moduna göre değişir.**

Bu mantık Redis, terminal, bilgi akışları, veri aktarma, veri analizi ve veri okuma katmanlarında **tüm uygulama** için geçerlidir. Yeni özellik veya refaktörde bu ayrım korunmalıdır.
