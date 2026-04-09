# RevnBookCheck Terminal – Log ve Davranış Özeti

## Logda Gördüğün Hatalar ve Düzeltmeler

### 1. `[IBKR] Error getting open orders: This event loop is already running`
- **Ne oluyordu:** Open orders IBKR’den alınırken, `_run_on_ib_thread` “farklı loop” dalında `func()` ana thread’de `call_soon_threadsafe` ile çalıştırılıyordu. `reqAllOpenOrders` / `openTrades` ib_insync içinde çalışan event loop’a dokununca “This event loop is already running” hatası oluşuyordu.
- **Yapılan:** “Different loop” dalında artık `func`, ana loop’un **executor**’ında çalıştırılıyor (thread pool, o thread’de loop yok). Böylece ib_insync ana loop’u çalışır sanmıyor, open orders alınabiliyor.

### 2. `[RevnBookCheck] Redis save error: 'RedisClient' object has no attribute 'setex'`
- **Ne oluyordu:** REV emri Redis’e yazılırken `redis_client.setex(key, 86400, value)` kullanılıyordu. Projedeki `RedisClient` sarmalayıcısında sadece `set(key, value, ex=ttl)` var, `setex` yok.
- **Yapılan:** `setex(key, 86400, value)` → `set(key, value, ex=86400)` olarak değiştirildi. REV kayıtları artık Redis’e yazılıyor.

---

## Terminal Tam Olarak Ne Yapıyor? (Adım Adım)

1. **Başlangıç**
   - Redis’e bağlanır.
   - Static data (janalldata.csv) ve group dosyalarını yükler.
   - Redis’ten aktif hesabı okur (IBKR_PED / IBKR_GUN / HAMPRO).
   - IBKR’ye bağlanır (seçili hesap IBKR ise).

2. **Startup recovery**
   - Pozisyonları Redis’ten alır (`psfalgo:positions:{account}`).
   - BEFDAY’i Redis’ten alır (`psfalgo:befday:positions:{account}`).
   - Open orders’ı alır: IBKR hesabıysa **doğrudan IBKR connector**’dan, Hammer ise backend HTTP’den.
   - Sonra **hemen bir kez** health check çalıştırır (RevRecoveryService).

3. **Health check (BEFDAY / CURRENT / POTENTIAL)**
   - Snapshot kaynağı: önce backend HTTP; boş/hatalıysa PositionSnapshotAPI (Redis + IBKR).
   - Her pozisyon için:
     - `gap = BEFDAY - POTENTIAL`
     - Sağlıklı sayılma: `|gap| < 200` veya `BEFDAY == CURRENT` veya `BEFDAY == POTENTIAL`.
   - Sağlıksız (health broken) olanlar:
     - BEFDAY=0 ise long/short **CURRENT**’a göre (gün içi pozisyon).
     - Değilse long/short BEFDAY’e göre.
     - REV senaryosu: INCREASE → kar al (0.04 $ min), DECREASE → reload/save (0.06 $ min).
   - Fill fiyatı: önce Redis execution ledger’dan bugünkü fill; yoksa snapshot `current_price`.
   - L1 (bid/ask) Redis’ten; emir fiyatı “maks bölge” / spread offset ile hesaplanır.
   - REV emri: placement_callback veya HTTP fallback ile gönderilir; ardından Redis’e yazılır (artık `set(..., ex=86400)` ile).

4. **Fill stream**
   - Redis stream `psfalgo:execution:ledger`’dan **sadece yeni** mesajlar okunur (`last_id='$'`).
   - Fill sadece **açık hesabın (positions ∪ BEFDAY) evrenindeki** semboller için işlenir; AAPL vb. atlanır.

5. **Periyodik**
   - Her **120 saniyede** bir health check tekrarlanır (eksik REV’ler için).
   - Frontlama 60 saniyede bir, account sync 15 saniyede bir çalışır.

---

## Logda Gördüğün “Health Broken” ve “Recovery REV placed”

- **Health Broken:** BEFDAY ≠ CURRENT veya BEFDAY ≠ POTENTIAL ve gap yeterince büyük (≥200). Örnek: KIM PRL BEFDAY=200, CURRENT=0, POTENTIAL=0 → tamamen satılmış, “reload” (geri al) gerekir.
- **Recovery REV placed:** Bu pozisyon için REV emri hesaplandı ve placement’a gönderildi (callback veya HTTP). Örnek: `REV_RECOVERY_INCREASE BUY 200.0 @ $20.28` = KIM PRL için 200 adet $20.28’den BUY (reload).
- **Redis save error** bu yüzden her REV’den sonra tekrarlanıyordu; `setex` → `set(..., ex=86400)` düzeltmesiyle artık REV’ler Redis’e yazılıyor.

---

## Özet

| Sorun | Sebep | Düzeltme |
|-------|--------|----------|
| Open orders: event loop already running | `func()` ana loop thread’inde çalışıyordu | `func` ana loop’un executor’ında çalıştırılıyor |
| Redis save: no attribute 'setex' | RedisClient’ta sadece `set(..., ex=...)` var | `setex` → `set(key, value, ex=86400)` |

Terminal mantığı: Açık hesabın BEFDAY/CURRENT/POTENTIAL’ına bakıp health gap’leri buluyor; fill fiyatı + L1 ile REV (reload/save veya kar al) hesaplayıp placement’a gönderiyor ve Redis’e yazıyor.
