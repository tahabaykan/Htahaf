# Health Gap Detayı ve Offline Fill / Fill Fiyatı Kaynağı

## 1. Health gap’ten ne anlayabiliriz (fill bildirimi yokken)

Sistem offline iken fill gelmişse stream’e yazılmadığı için **fill fiyatını** stream’den bilemeyiz. Ama **BEFDAY / current / potential** üçlüsü snapshot’tan (broker + BEFDAY + açık emirler) geldiği için, uygulama açıldıktan sonra pozisyon çekildiğinde şunları **çıkarabiliriz**:

| Bilgi | Kaynak | Açıklama |
|-------|--------|----------|
| **Gap miktarı** | `gap = befday - potential` | Kaç adet REV (reload/TP) gerektiği; `abs(gap)` = REV qty. |
| **Yön** | `gap > 0` → BUY (reload), `gap < 0` → SELL (TP) | Hangi aksiyon. |
| **Long/Short** | `befday` (ve gerekiyorsa `current`) | INC/DEC ve 8-tag (LT_LONG_INC vb.) için. |
| **Fill fiyatı** | **Health gap’ten çıkarılamaz** | Sadece miktar ve yön var; fiyat başka kaynaktan gelmeli. |

Yani: **Quantity, yön, REV gerekli mi** evet; **hangi fiyattan fill oldu** hayır — bunun için broker/execution kaynağı gerekir.

---

## 2. Şu anki fill fiyatı kaynakları

### 2.1 Fill stream (online)

- Fill geldiği anda **psfalgo:execution:ledger** stream’ine yazılıyor (IBKR callback / Hammer listener).
- Mesajda: `symbol`, `qty`, `price`, `action`, `order_id`, `account_id`.
- RevnBookCheck bu mesajı okuyup `fill.get('price', 0.0)` ile REV hesaplıyor.

### 2.2 Recovery (health broken, fill stream’de yok)

- **RevRecoveryService._get_last_fill_price(symbol)**:
  1. **Redis ledger:** `psfalgo:execution:ledger` stream’inde o sembolün **en son** fill’ini arar (xrevrange, 500 mesaj).
  2. **Fallback:** Ledger’da yoksa **snap.current_price** (anlık piyasa fiyatı) kullanılır.

Sonuç: Sistem offline iken fill gelmişse ledger’a hiç yazılmadığı için ledger’da fiyat yok; recovery sadece **current_price** ile REV fiyatı hesaplıyor (gerçek fill fiyatı değil).

---

## 3. IBKR: O günkü işlemler (executions) isteyebilir miyiz?

**Evet.** TWS API ile **o günkü (ve isteğe göre belirli tarihten sonraki) execution’lar** çekilebiliyor.

### 3.1 API

- **reqExecutions(ExecutionFilter)**  
  - Execution listesini ister.  
  - **ExecutionFilter** parametreleri (ib_insync `ExecutionFilter`):  
    - **time**: `"yyyymmdd hh:mm:ss"` — bu zamandan **sonraki** execution’lar döner.  
    - **clientId**, **acctCode**, **symbol**, **secType**, **exchange**, **side** ile filtre daraltılabilir.
- **Varsayılan davranış (dökümantasyon):** Sadece **o gün midnight’tan itibaren** olan execution’lar verilir. Son 7 gün için TWS Trade Log ayarı “Show trades for ...” değiştirilmeli; **IB Gateway** bu ayarı değiştiremediği için genelde sadece **o gün** kullanılır.

### 3.2 Callback

- **execDetails(reqId, contract, execution)** her eşleşen execution için çağrılır.
- **Execution** nesnesinde: **price**, **shares**, **time**, **execId**, **orderId**, **side** (BOT/SLD), **acctNumber** vb. var — yani **fill fiyatı** buradan alınır.

### 3.3 Projedeki kullanım

- **ibkr_connector**: `connect()` sonrası `_register_fill_recovery()` çağrılıyor.
- Orada **reqExecutions(ExecutionFilter())** (boş filter) ile **o günkü execution’lar** isteniyor.
- Gelen her **execDetails** callback’inde fill **psfalgo:execution:ledger** stream’ine yazılıyor (symbol, price, qty, action, account_id, order_id).
- Sonuç: **Uygulama açılıp IBKR’a connect olduğunda**, o günkü fill’ler (fiyat dahil) ledger’a yazılıyor; recovery veya RevnBookCheck buradan fill fiyatını alabiliyor.

Özet: IBKR tarafında **o gün içindeki transaction’lar** (executions) **request atarak** alınabiliyor; fill fiyatı da bu execution objesinden okunuyor. Bunu zaten connect sonrası yapıyoruz; offline kaldığımız fill’ler, **ilk connect** anında ledger’a düşüyor.

---

## 4. Hammer Pro: O günkü işlemler

Hammer Pro tarafında **günlük işlem / execution history** için API olup olmadığı, gönderilecek dokümantasyona göre incelenecek.  
- Varsa: “O günkü fill’leri listele” benzeri bir endpoint ile offline fill’ler + fiyatları alınıp ledger’a yazılabilir veya recovery’de fill fiyatı olarak kullanılabilir.  
- Dokümantasyon geldikten sonra bu bölüm güncellenecek.

---

## 5. Özet tablo

| Durum | Fill fiyatı nereden? | Not |
|-------|----------------------|-----|
| Fill anında online | Stream mesajı `price` | Doğrudan fill fiyatı. |
| Offline fill, sonra IBKR connect | reqExecutions → execDetails → ledger’a yazma | Connect sonrası o günkü fill’ler ledger’da; recovery/RevnBookCheck buradan fiyat alır. |
| Offline fill, henüz IBKR connect yok | Yok; fallback **current_price** | Gerçek fill fiyatı bilinmez. |
| Hammer Pro offline fill | Şu an sadece stream (online); günlük history API dokümana göre eklenecek | Dokümantasyon sonrası netleşecek. |

Health gap ile **miktar ve REV gerekliliği** her zaman çıkarılabilir; **fill fiyatı** ancak broker/execution kaynağı (IBKR executions, Hammer history vb.) ile sağlanır.
