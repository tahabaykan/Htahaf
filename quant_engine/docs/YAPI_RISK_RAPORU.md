# Yapıyı Bozabilecek Satırlar – İnceleme Raporu

Bu rapor Dual Process, XNL, hesap geçişleri ve MinMax ile ilgili kritik satırları tek tek inceleyerek olası riskleri özetler.

---

## 1. Refresh Cycle vs Toptan Cancel (XNL)

**Durum:** Refresh cycle kaldırıldı; toptan cancel şu an bu şekilde kullanılıyor.

- **`xnl_engine.py` `start()`:** Sadece `_front_cycle_loop` task'ları oluşturuluyor; `_refresh_cycle_loop` hiç başlatılmıyor (satır ~179–194). Yani kategori bazlı periyodik refresh yok.
- **Toptan cancel:** Dual Process her hesap geçişinde `engine.cancel_by_filter(account, "tum", False)` çağırıyor (`dual_process_runner.py` 159, 178). XNL içinde ek bir refresh cycle yok; refresh tek kaynak: Dual Process (veya manuel Cancel All).
- **Ölü kod:** `_refresh_cycle_loop` ve `_execute_refresh_cycle` hâlâ tanımlı ama hiç çağrılmıyor. Yapıyı bozmaz; ileride tamamen kaldırılabilir.

**Sonuç:** Evet, şu an sadece toptan cancel (XNL içinde refresh cycle yok).

---

## 2. Hesap Aktif Mod ve Hesap Geçişleri

### 2.1 Dual Process → Context

- **`dual_process_runner.py` 164–165, 182–183:** `ctx.set_trading_mode(to_mode(account_a/b))` ile geçiş yapılıyor. Kaynak: `TradingAccountContext` (HAMPRO, IBKR_PED, IBKR_GUN).
- **XNL/RUNALL/MinMax:** Hepsi `account_id = get_trading_context().trading_mode.value` kullanıyor. Yani tek kaynak: TradingAccountContext. Dual Process context’i set ettikten sonra XNL başladığı için doğru hesap kullanılıyor.

### 2.2 TradingAccountContext – Redis vs Bellek

- **`trading_account_context.py` 56–67:** `trading_mode` property Redis’ten okuyor; `set_trading_mode` hem `_trading_mode` hem Redis’i güncelliyor.
- **`get_status()` (126–133):** Sadece `self._trading_mode` döndürüyor (Redis okumuyor). Tek process’te Dual Process ile aynı process çalışıyorsa tutarlı. Çoklu process’te biri Redis’i değiştirirse `get_status()` eski değeri gösterebilir; şu an tek backend kullanıldığı için risk düşük.

### 2.3 AccountMode (HAMMER_PRO) vs TradingAccountMode (HAMPRO)

- **`account_mode.py`:** `AccountMode.HAMMER_PRO`, `IBKR_GUN`, `IBKR_PED` (UI/account selector, connect-disconnect).
- **`trading_account_context.py`:** `TradingAccountMode.HAMPRO`, `IBKR_GUN`, `IBKR_PED` (emir/pozisyon verisi).
- Dual Process sadece `TradingAccountContext.set_trading_mode()` çağırıyor; `AccountModeManager` set edilmiyor. Yani:
  - Emir/pozisyon/minmax tarafı doğru hesabı kullanıyor (TradingAccountContext).
  - UI’da “hesap seçici” AccountModeManager’dan besleniyorsa, Dual Process çalışırken “seçili hesap” ile Dual Process’in “current_account”u farklı görünebilir. Bu tasarım tercihi; Dual Process state’teki `current_account` gerçek aktif hesap.

**Sonuç:** Hesap geçişleri ve aktif mod, emir/pozisyon tarafında doğru; UI’da tek kaynak olarak Dual Process state kullanılırsa tutarlı olur.

---

## 3. MinMax – Hesap İzolasyonu ve “Neden Olmadı” Riski

### 3.1 Yapılan Düzeltmeler (Özet)

- **`minmax_area_service.py`:**
  - `compute_for_account` sonunda `self._cache_account = account_id` set ediliyor; boş `rows` durumunda `_cache` temizleniyor (219–223). Böylece eski hesabın cache’i yeni hesaba taşınmıyor.
  - `load_from_csv` sonunda `self._cache_account = None` (305). Sonraki `get_row(account_id, sym)` Redis’ten o hesap için yeniden hesaplatır; CSV hesap-bağımsız kalsa bile doğru hesap verisi kullanılır.
- **`xnl_engine.py`:** MinMax için CSV fallback kaldırıldı; sadece `minmax_svc.get_row(account_id, symbol)` / `get_all_rows(account_id)` kullanılıyor (Redis + compute).

### 3.2 Hâlâ Dikkat Edilmesi Gereken Satırlar

- **`minmax_area_service.py` 218:** `self._cache.update({r.symbol: r for r in rows})` – Sadece `compute_for_account` içinde; önceki satırlarda `account_id` ile Redis/pos_api kullanıldığı için doğru hesabın verisi yazılıyor. Hesap değişince bir sonraki `get_row(other_account, sym)` 236. satırdaki `_cache_account != account_id` ile yeniden compute tetikliyor. Sorun yok.
- **`minmax_area_service.py` 232–234:** `get_row` içinde `account_id != _cache_account` veya `symbol not in _cache` ise `compute_for_account(account_id, symbols=[symbol])` çağrılıyor. Hesap geçişinde ilk istekte mutlaka recompute olur; karışma riski yok.
- **`minmax_area_service.py` 152:** Redis key `psfalgo:positions:{account_id}` – Hesap bazlı; izolasyon doğru.

**“Neden olmadı” senaryosu:** Eski davranışta boş cache veya CSV fallback ile başka hesabın limitleri kullanılabiliyordu. Şu an:
1. CSV fallback XNL’de yok.
2. Cache hesap kilidi var (`_cache_account`).
3. Boş sonuçta cache temizleniyor.

Bu üçü birlikte “minmax neden olmadı” tipi hataları engellemek için yeterli.

---

## 4. Dual Process Runner – Kritik Satırlar

- **159, 178:** `await engine.cancel_by_filter(account_a/b, "tum", False)` – Hesap açıkça veriliyor; sadece o hesabın emirleri iptal ediliyor. Sorun yok.
- **164, 182:** `ctx.set_trading_mode(to_mode(account_a/b))` – Context önce set ediliyor, sonra cancel ve XNL start. Sıra doğru.
- **166, 184:** `await engine.start()` – Start, context zaten doğru hesaba geçmiş durumda. XNL içinde `account_id = ctx.trading_mode.value` kullanıldığı için doğru hesap kullanılır.
- **205–211:** `_sleep_longest_front_cycle` içinde `_stop_requested` her 5 saniyada kontrol ediliyor; stop isteği gecikmeden işlenir.

**Potansiyel risk (düşük):** 132–134. satırlarda `stop()` içinde `await asyncio.wait_for(self._task, timeout=2.0)` – Task 2 saniyede bitmezse timeout olur ama `_stop_requested = True` zaten set edildiği için loop en geç bir sonraki 5 saniyalık uyanmada çıkar. Yapıyı bozmaz.

---

## 5. XNL – cancel_by_filter ve Redis

- **`xnl_engine.py` 1295:** `all_orders = await self._get_broker_open_orders(account_id)` – Hesaba göre broker emirleri alınıyor.
- **1347:** `await self._cancel_order(str(order_id), account_id)` – İptal hesaba özel.
- **1362–1376:** Redis temizliği `psfalgo:open_orders:{account_id}` ile yapılıyor; hesap izolasyonu doğru.

---

## 6. Özet Tablo

| Konu | Durum | Not |
|------|--------|-----|
| Refresh cycle | Kaldırıldı | Sadece front cycle; toptan cancel Dual Process/manuel |
| Hesap geçişi (context) | Doğru | Dual Process context set ediyor; XNL/RUNALL/MinMax aynı context’i kullanıyor |
| MinMax hesap karışması | Düzeltildi | Cache account lock + CSV fallback kaldırıldı |
| cancel_by_filter hesap | Doğru | account_id parametreyle; Redis key hesap bazlı |
| BEFDAY/positions Redis | Hesap bazlı | `psfalgo:positions:{account_id}`, `psfalgo:befday:positions:{account_id}` |
| TradingAccountContext get_status | Düşük risk | Tek process’te tutarlı; çoklu process’te Redis ile teorik sapma |

---

## 7. Öneriler

1. **XNL docstring:** “Refresh cycle kaldırıldı, toptan cancel kullanılıyor” ifadesi eklendi (xnl_engine.py dosya başı).
2. **Ölü kod:** İleride `_refresh_cycle_loop` ve `_execute_refresh_cycle` kaldırılabilir; şu an yapıyı bozmaz.
3. **UI:** Dual Process çalışırken “aktif hesap” bilgisi için sadece Dual Process state (`current_account`, `loop_count`) kullanılsın; böylece AccountModeManager ile çakışma olmaz.
4. **MinMax:** Ek bir değişiklik gerekmiyor; mevcut cache ve CSV davranışı hesap izolasyonunu sağlıyor.

Bu rapor, yapıyı bozabilecek satırların tek tek incelenmesiyle oluşturulmuştur; mevcut kod bu haliyle hesap geçişleri ve MinMax için tutarlı çalışacak şekilde görünmektedir.
