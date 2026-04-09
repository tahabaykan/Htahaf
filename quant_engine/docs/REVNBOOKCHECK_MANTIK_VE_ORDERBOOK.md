# RevnBookCheck: Mantık Özeti ve Order Book (Kademe) Nasıl Çalışıyor

## 1. REV Açma Mantığı (Güncel)

**REV açılması sadece şu durumda gerekir:**
- **|gap| >= 200** (gap = BEFDAY − POTENTIAL)
- **Ve** BEFDAY hem CURRENT'a hem POTENTIAL'a eşit **değil** (ikisinden birine eşitse yeter, REV açma).

**Yani:**
- **|gap| < 200** → Sağlıklı, REV açılmaz.
- **|gap| >= 200** ve **(BEFDAY = CURRENT veya BEFDAY = POTENTIAL)** → Sağlıklı, REV açılmaz (ikisine birden eşit olmak zorunda değil).
- **|gap| >= 200** ve **BEFDAY ≠ CURRENT** ve **BEFDAY ≠ POTENTIAL** → Fill alınmış ama REV açılmamış; REV gerekir.

Eşitlik kontrolü float için 0.01 toleransla yapılıyor (`abs(befday - current) < 0.01` vb.).

---

## 2. Order Book (Kademe) Nasıl Çalışıyor

### Kaynak
- **OrderBookFetcher** (`app/terminals/orderbook_fetcher.py`) tahtayı **Hammer Pro** üzerinden alıyor.
- `HammerClient.get_l2_snapshot(symbol)` ile o sembol için L2 (bid/ask kademeleri) isteniyor.
- Hammer bağlı değilse veya sembol L2'ye abone değilse snapshot boş dönüyor → kademe yok, "Hard Target" / "Hard Reload" kullanılıyor.

### Ne Zaman Kademe Kullanılıyor?
**RevOrderEngine** önce L1 (bid/ask/spread) ile "ideal" fiyatı hesaplıyor; bu hedefe yetmiyorsa **order book'a** bakıyor.

**Örnek – Long Increase (SELL, kar al 0.04):**
1. `min_price = fill_price + 0.04`
2. L1: `ideal_price = ask - (spread * 0.15)`
3. **Eğer** `ideal_price >= min_price` → Emir fiyatı = `ideal_price` (L1 spread offset), kademe kullanılmaz.
4. **Eğer** L1 yeterli değilse → `find_suitable_ask(symbol, min_price)` çağrılır:
   - Hammer'dan L2 (ask kademeleri) alınır.
   - Ask kademeleri **fiyata göre sıralı** (en düşük ask en önde).
   - **İlk ask >= min_price** olan kademe "uygun kademe" sayılır; emir o kademenin 1 cent altına konur (öncelik almak için).
   - Hiç ask >= min_price yoksa → kademe yok, **Hard Target 0.04** (sadece `min_price`).

**Örnek – Long Decrease (BUY, reload 0.06):**
1. `max_price = fill_price - 0.06`
2. L1: `ideal_price = bid + (spread * 0.15)`
3. **Eğer** `ideal_price <= max_price` → Emir fiyatı = `ideal_price` (L1), kademe yok.
4. **Eğer** L1 yeterli değilse → `find_suitable_bid(symbol, max_price)`:
   - L2 bid'ler alınır, **fiyata göre sıralı** (en yüksek bid en önde).
   - **İlk bid <= max_price** olan kademe uygun; emir o kademenin 1 cent üstüne konur.
   - Uygun bid yoksa → **Hard Reload 0.06** (sadece `max_price`).

### Kademe Bulma (find_suitable_ask / find_suitable_bid)
- **find_suitable_ask(symbol, min_price):** Ask listesinde **ilk ask >= min_price** olan kademeyi döner; (fiyat, 1-tabanlı level).
- **find_suitable_bid(symbol, max_price):** Bid listesinde **ilk bid <= max_price** olan kademeyi döner; (fiyat, 1-tabanlı level).

Order book boş veya uygun kademe yoksa `None, None` döner → engine "Uygun Kademe Bulunamadı" deyip Hard Target / Hard Reload fiyatını kullanır.

### Neden "Uygun Kademe Bulunamadı" Çıkıyor?
- Terminal Hammer'a bağlanıyor ama **L2 (order book)** genelde sadece **subscribe edilmiş** semboller için dolar.
- Recovery/fill işlenirken o sembol için L2 hiç istenmemiş/abone olunmamış olabilir → `get_l2_snapshot(symbol)` boş veya gecikmeli.
- Ya da Hammer tarafında `getQuotes`/L2 cevabı fail (logda `getQuotes, success=fail` görülebilir).

**Özet:** Kademe kontrolü gerektiğinde yapılıyor; veri Hammer L2'den geliyor. L2 yoksa veya uygun kademe yoksa emir yine açılıyor, fiyat sadece "Hard Target" / "Hard Reload" (0.04 / 0.06) ile belirleniyor.

---

## 3. Recovery'de Neden Current=0, Potential=0 Görünüyordu?

**Sebep:** Health check snapshot'ları **IBKR hesaplarında** backend HTTP (`GET /api/trading/positions`) ile alınıyordu. Backend sürecinin IBKR'a bağlantısı yok (sadece terminal IBKR'a bağlı). Backend'deki PositionSnapshotAPI `connector.is_connected() == False` olduğu için IBKR'dan 0 pozisyon çekiyor; BEFDAY'deki her sembol için **phantom** pozisyon (qty=0, potential_qty=0) üretiyordu. Bu yüzden logda hep `Current=0, Potential=0` görünüyordu.

**Çözüm:** IBKR hesapları (IBKR_PED, IBKR_GUN) için recovery artık **HTTP kullanmıyor**; snapshot'ları doğrudan **yerel PositionSnapshotAPI** ile alıyor. Terminal sürecinde IBKR zaten bağlı olduğu için gerçek `qty` ve `potential_qty` gelir; health denklemi doğru çalışır. Hammer (HAMPRO) için backend HTTP kullanımı aynen devam eder.
