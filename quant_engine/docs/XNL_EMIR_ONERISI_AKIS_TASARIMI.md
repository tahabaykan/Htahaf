# XNL Emir Önerisi ve Gönderim Akışı — Tasarım

Bu doküman, istediğin hedef akışı tarif ediyor ve “nasıl işleyecek / nasıl yapacağız”ı adım adım tanımlıyor.

---

## 1) Hedef Davranış (Ne İstiyoruz?)

1. **Emir önerileri her sekme için hazırlansın**  
   Kurallar/filtreler zaten belli; LT_TRIM, KARBOTU, REDUCEMORE, ADDNEWPOS, MM her biri kendi sekmesinde öneri üretsin.

2. **Hangi hesap açıksa oraya gitsin**  
   XNL / IBKR (PED veya GUN) veya Hammer Pro — **tek bir “aktif hesap”** baz alınsın, tüm emir gönderimi ve takip bu hesaba yapılsın.

3. **Hesap sürekli takip edilsin**  
   RevnBookCheck (revnbookcheck) terminali bu hesabı takip etsin: fill’ler, frontlama, REV üretimi hep bu hesaba göre çalışsın.

4. **Genel akış net ve tekrarlanabilir olsun**  
   - Kurallar/koşullar/filtreler uygulansın → öneriler sunulsun ve (onaylanınca) gönderilsin.  
   - Cycle ile frontlama vs. takip edilsin.  
   - “İş bittiğinde” ilgili emirler cancel edilsin, ardından refresh cycle ile yeniden öneri üretilip emirler yazılsın.

Bu doküman bu davranışı sağlayacak **tek bir sistem tasarımı** olarak yazıldı.

---

## 2) Üst Düzey Akış (Nasıl İşleyecek?)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TEK HESAP KAYNAĞI (Redis + UI)                        │
│  trading_mode = HAMPRO | IBKR_PED | IBKR_GUN  →  Tüm emir ve takip bu hesap  │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
          ┌───────────────────────────────┼───────────────────────────────┐
          ▼                               ▼                               ▼
┌─────────────────────┐     ┌─────────────────────────────┐     ┌─────────────────────┐
│  ÖNERİ HAZIRLAMA    │     │  EMİR GÖNDERİMİ             │     │  HESAP TAKİBİ      │
│  (Her sekme)        │     │  (Hangi hesap açıksa oraya)  │     │  (RevnBookCheck)    │
│                     │     │                             │     │                     │
│  • _prepare_request │     │  ExecutionService           │     │  • Fill izleme      │
│  • Motorlar         │     │  → ExecutionRouter          │     │  • Frontlama        │
│  • Proposal Store  │     │  → get_trading_context()     │     │  • REV üretimi      │
│  • Sekme = engine   │     │  → HAMPRO/IBKR provider      │     │  • account = mode   │
└─────────────────────┘     └─────────────────────────────┘     └─────────────────────┘
          │                               │                               │
          └───────────────────────────────┼───────────────────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CYCLE: Cancel → Refresh → Öneri üret → Gönder → Takip → (süre/koşul) → ...  │
└─────────────────────────────────────────────────────────────────────────────┘
```

Yani:

- **Tek hesap**: TradingAccountContext (Redis: `psfalgo:trading:account_mode`). UI’da “XNL IBKR” / “Hammer Pro” seçimi bu değeri yazar; RevnBookCheck ve ExecutionRouter bu değeri okur.
- **Öneri hazırlama**: RUNALL tarafındaki `_prepare_request` + motorlar + proposal_store. Her “sekme” = bir engine’in proposals’ı (LT_TRIM, KARBOTU, REDUCEMORE, ADDNEWPOS, MM).
- **Gönderim**: Onaylanan proposal → ExecutionService → Router → `trading_mode`’a göre ilgili provider (HAMPRO / IBKR_PED / IBKR_GUN). Yani “hangi hesap açıksa oraya” mantığı zaten router’da var; eksik olan tek şey her yerde **aynı hesap kaynağının** kullanılması.
- **Hesap takibi**: RevnBookCheck fill/frontlama/REV’i bu hesaba göre yapsın; bunun için hesabı TradingAccountContext ile aynı kaynaktan (veya senkron key’den) okuması yeterli.

---

## 3) Bileşenler ve Rolleri

### 3.1) Tek hesap kaynağı

| Bileşen | Rol |
|--------|-----|
| **TradingAccountContext** | `trading_mode`: HAMPRO / IBKR_PED / IBKR_GUN. Redis key: `psfalgo:trading:account_mode`. |
| **UI (PSFALGO / ayarlar)** | Kullanıcı “XNL IBKR” veya “Hammer Pro” seçer → `set_trading_mode` ile Redis’e yazılır. |
| **RevnBookCheck** | Hesabı okumalı. Şu an `psfalgo:account_mode` (JSON) kullanıyor; TradingAccountContext `psfalgo:trading:account_mode` kullanıyor. **Tasarım kararı:** Tek kaynak `psfalgo:trading:account_mode` olsun; RevnBookCheck bu key’i okusun (veya bu key’i yazan servis `psfalgo:account_mode`’u da sync etsin). |

Böylece “hangi hesap açıksa” tüm sistemde aynı yerden gelir.

### 3.2) Emir önerileri (her sekme)

| Bileşen | Rol |
|--------|-----|
| **RUNALL _prepare_request** | Pozisyon, metrics (GORT/Fbtot/SFStot), exposure, JFIN adayları. Tüm motorlar bu request ile beslenir. |
| **Motorlar** | LT_TRIM, KARBOTU, REDUCEMORE, ADDNEWPOS, MM. Kurallar/filtreler burada; çıktı intent/decision. |
| **Proposal Engine + Store** | Intent/decision → proposal. Her proposal `engine` (ve dolayısıyla “sekme”) ile işaretlenir. |
| **UI sekmeleri** | “Live / Core Execution”, “Add New Pos”, “GEM (MM)” vb. Her sekme ilgili engine’in proposals’ını listeler (örn. `engine === 'LT_TRIM'`, `engine.includes('MM')`). |

“Her sekme için emir önerileri hazırlansın” = RUNALL (veya RUNALL ile aynı veriyi kullanan XNL) döngüde _prepare_request → motorlar → proposal_store; UI sadece filtreleyerek gösterir. Ek bir “hazırlama” katmanı gerekmez; hazırlama zaten RUNALL tarafında.

### 3.3) Emir gönderimi (hangi hesap açıksa oraya)

| Bileşen | Rol |
|--------|-----|
| **ExecutionService** | Onaylanmış proposal’ı alır → order_plan üretir → Router’a gider. Zaten `get_trading_context()` / AccountModeManager ile “aktif hesap”a göre çalışıyor. |
| **ExecutionRouter** | `get_trading_context().trading_mode` → HAMPRO → HammerExecutionProvider, IBKR_* → IBKRExecutionProvider. Emir **her zaman** aktif hesaba gider. |
| **XNL _place_order** | XNL kendi emir yolunda `account_id` alıyor; bu değerin tek kaynaktan (TradingAccountContext) gelmesi gerekir. Tasarım: XNL emir atarken `get_trading_context().trading_mode.value` kullansın; böylece “XNL IBKR / Hammer” seçimi ile uyumlu olur. |

Yani “XNL IBKR veya Hammer Pro, hangi hesap açıksa oraya” davranışı, **tüm gönderim yolunun tek hesap kaynağını kullanması** ile sağlanır.

### 3.4) Hesap takibi ve cycle (RevnBookCheck)

| Bileşen | Rol |
|--------|-----|
| **RevnBookCheck** | Fill izleme, frontlama (örn. 60 sn’de bir), REV üretimi, recovery. **Hesap:** Başlangıçta ve periyodik olarak “aktif hesap”ı okur; fill/positions/orders hep bu hesaba göre. |
| **Hesap okuma** | `TradingAccountContext.trading_mode` veya aynı değeri okuyan Redis key. RevnBookCheck’in `_get_account_mode()` bu kaynağa bağlanmalı. |
| **Frontlama / “iş bitti”** | Frontlama mevcut döngüde çalışıyor. “İş bitti” = zaman (örn. refresh süresi) veya koşul (örn. tüm bekleyen emirler fill/cancel). Cycle orchestrator bu koşula göre “cancel → refresh” adımını tetikler. |

RevnBookCheck’in yapması gereken: Doğru hesabı okuyup fill/frontlama/REV’i o hesaba kilitlemek. “Cycle’da takip” bu terminalin mevcut davranışı; tasarım sadece hesap kaynağını netleştiriyor.

### 3.5) Cycle: cancel → refresh → yeniden yaz

İstediğin davranış:

- İlgili emirler cancel edilsin.  
- Ardından refresh cycle atılsın; kurallar/filtreler tekrar uygulansın, yeni öneriler üretilsin ve (onaylanırsa) yeniden emir yazılsın.

Bunu sağlayan “cycle orchestrator” akışı:

```
1) Öneri üret (RUNALL veya XNL ile aynı veri hazırlığını kullanan tek yol)
   → _prepare_request(account_id)
   → Motorlar (LT_TRIM, KARBOTU, REDUCEMORE, ADDNEWPOS, MM)
   → Proposal Store

2) UI’da öneriler sekme bazlı listelensin; kullanıcı onaylar.

3) Onaylanan öneriler → ExecutionService → Router → aktif hesaba gönderilir.

4) Takip (RevnBookCheck): Fill, frontlama, REV bu hesaba göre çalışır.

5) “Cycle bitişi” (zamanlayıcı veya koşul):
   a) İlgili emirler cancel edilir (örn. LT book, veya tüm bekleyen PSFALGO emirleri).
   b) Refresh: Yeni cycle başlar → 1’e dön.

account_id tüm adımlarda get_trading_context().trading_mode.value ile belirlenir.
```

“İlgili emirler” tanımı: O cycle’da hangi book/tag ile gönderildiyse (örn. LT_*, MM_*). Cancel API’leri zaten account + book/tag ile çalışıyor; cycle sonunda bu API’nin “aktif hesap + ilgili book” ile çağrılması yeterli.

---

## 4) Şu An Eksik / Sorun Olan Noktalar

### 4.1) XNL öneri üretmiyor, veri boş

- XNL `_run_initial_cycle` metrics={}, exposure=None ile motor çalıştırıyor → motorlar anlamlı öneri üretemiyor.
- XNL proposal_store’a yazmıyor → hangi sekmede olursa olsun “XNL’den gelen öneriler” UI’da yok.

**Yapılacak:** XNL’in ilk (ve gerekirse sonraki) cycle’ları RUNALL’daki `_prepare_request` ile aynı veriyi kullansın; çıkan intent/decision’lar proposal_engine + proposal_store’a yazılsın. Böylece “emir önerileri her sekme için” XNL çalıştığında da dolar.

### 4.2) Hesap kaynağı iki yerde

- TradingAccountContext: `psfalgo:trading:account_mode`
- RevnBookCheck: `psfalgo:account_mode` (JSON içinde `mode`)

İkisi farklı key; senkron değilse “hangi hesap açık” RevnBookCheck ile UI/execution arasında farklı olabilir.

**Yapılacak:** Hesap bilgisini tek key’de topla. Tercih: `psfalgo:trading:account_mode` = canonical. UI ve ExecutionRouter zaten TradingAccountContext kullanıyor. RevnBookCheck’i bu key’i okuyacak şekilde güncelle (veya ortak bir “account_mode” servisi hem bu key’i yazsın hem de RevnBookCheck’in okuduğu key’i sync etsin).

### 4.3) XNL emir atarken hesap nereden geliyor?

- XNL `_place_order(..., account_id)` alıyor; bu `account_id`’nin nereden geldiği önemli. Eğer sabit veya yanlış kaynaktan geliyorsa “hangi hesap açıksa oraya” bozulur.

**Yapılacak:** XNL içinde emir gönderirken `account_id = get_trading_context().trading_mode.value` kullanılsın. Çağrıyı yapan yer (örn. _send_orders_with_frontlama, _run_initial_cycle) bu değeri geçirsin.

### 4.4) Cycle “cancel → refresh” tek yerden tetiklenmiyor

- RUNALL cycle içinde “cancel LT orders” var; XNL’de cancel_all / cancel by book var ama “cycle sonu → cancel → refresh” tek bir orchestrator’da toplanmış değil.

**Yapılacak:** “Cycle orchestrator” (RUNALL olabilir veya XNL’in cycle’ı) şu sırayı net tanımlasın:  
(1) Öneri üret (tek veri hazırlığı),  
(2) Önerileri göster/gönder,  
(3) Süre veya koşul dolunca ilgili emirleri cancel et,  
(4) Hemen ardından yeni cycle (refresh) başlat.  
Bunu ya RUNALL’ın mevcut _cycle_loop’una “cancel + sleep + next cycle” olarak ekleyebiliriz ya da XNL’i “RUNALL ile aynı veriyi kullanan + cancel→refresh” döngüsüne taşırız.

---

## 5) Nasıl Yapacağız? (Uygulama Sırası)

### Adım 1: Tek hesap kaynağı

- **TradingAccountContext** ve Redis key `psfalgo:trading:account_mode` değişmesin.
- **RevnBookCheck `_get_account_mode()`:**  
  - Ya doğrudan `get_trading_context().trading_mode.value` kullanacak (aynı process içinde çalışıyorsa),  
  - Ya da Redis’ten `psfalgo:trading:account_mode` okuyacak (ayrı process ise).  
  Böylece “hangi hesap açık” tek kaynaktan gelir.
- İsterseniz eski `psfalgo:account_mode` key’ini kaldırıp sadece `psfalgo:trading:account_mode` bırakın; veya bir “AccountModeSync” fonksiyonu `psfalgo:trading:account_mode` değişince `psfalgo:account_mode`’u da güncellesin, RevnBookCheck eski key’i okumaya devam etsin. Tercih: her yeri yeni key’e geçirmek.

### Adım 2: XNL’i RUNALL veri katmanına bağla

- Ortak “request hazırlık”:
  - Ya RunallEngine._prepare_request(account_id) dışarıdan çağrılabilir hale getirilir,
  - Ya da aynı işi yapan paylaşılan bir modül fonksiyonu (örn. `prepare_cycle_request(account_id)`) yazılır; hem RUNALL hem XNL bunu kullanır.
- XNL `_run_initial_cycle` (ve ileride front/refresh cycle’ları):
  - Önce bu preparer’dan `request` alır.
  - _run_lt_trim / _run_karbotu / _run_addnewpos / _run_mm artık kendi içinde boş request üretmez; hepsi bu ortak `request` ile çalışır.
- XNL motor çıktılarını (intent/decision) proposal_engine + proposal_store’a yazar; **decision_source** = “XNL” veya ilgili engine adı. Böylece “emir önerileri her sekme için” XNL’den de gelir.

### Adım 3: XNL emir gönderiminde hesap = trading_context

- XNL’de emir atan her yer (`_place_order`, `_send_orders_with_frontlama`, cancel çağrıları) `account_id`’yi şuradan alsın:  
  `account_id = get_trading_context().trading_mode.value`
- Böylece “XNL IBKR / Hammer Pro, hangi hesap açıksa oraya” tüm XNL emirlerinde tutarlı olur.

### Adım 4: Cycle’da “cancel → refresh” netleştir

- RUNALL’da zaten “cancel LT orders” var. Genişletilebilir: “cycle bitişi”nde (zaman veya koşul) tüm ilgili PSFALGO emirleri (veya sadece belirli book’lar) aktif hesap için cancel edilsin.
- Hemen ardından yeni cycle (refresh) koşulsuz başlasın: _prepare_request → motorlar → proposal_store. Bu, “yeniden yaz” kısmı.
- Bu davranış tek bir döngüde toplanırsa (RUNALL _cycle_loop veya XNL’in cycle’ı), “cancel → refresh → öneri üret → gönder → takip” hattı net olur.

### Adım 5: UI’da “aktif hesap” seçimi

- PSFALGO (veya ana ayarlar) sayfasında “Aktif hesap: XNL IBKR / Hammer Pro” gibi bir seçim olsun; değer `TradingAccountContext.set_trading_mode` ile Redis’e yazılsın.
- Böylece kullanıcı hangi hesabın “açık” olduğunu tek yerden seçer; öneri, gönderim ve RevnBookCheck hep bu hesabı kullanır.

### Adım 6: RevnBookCheck’in sürekli aynı hesabı kullanması

- Start’ta bir kere değil, periyodik (örn. her döngüde veya her 30 sn) aktif hesabı okusun; `self.account_mode` güncellensin.  
  Böylece kullanıcı UI’dan hesap değiştirdiğinde RevnBookCheck bir sonraki okumada doğru hesaba geçer.
- Fill/positions/orders/frontlama çağrıları hep `self.account_mode` ile yapılmaya devam eder.

---

## 6) Özet: Akış Tek Cümlede

**“Emir önerileri her sekme için hazırlanır (RUNALL/XNL aynı veri hazırlığını kullanır, proposal_store’a yazar); hangi hesap açıksa (TradingAccountContext) tüm emir gönderimi oraya gider; RevnBookCheck bu hesabı takip eder; cycle sonunda ilgili emirler cancel edilir ve refresh ile yeniden öneri üretilip emirler yazılır.”**

Bu tasarımı uygularken sıra: **1 → 2 → 3 → 4 → 5 → 6**. Önce hesap ve veri hazırlığı, sonra cancel/refresh ve UI, en sonda RevnBookCheck’in sürekli doğru hesabı okuması.

Bu doküman, mevcut RUNALL/ExecutionService/RevnBookCheck/XNL kodlarına göre yazıldı. İstersen bir sonraki adımda Adım 1–2 için somut patch (hangi dosyada hangi satırlar) çıkarılabilir.
