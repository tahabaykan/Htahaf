# PSFALGO / QAGENTT Strateji DNA'sı
## Agent Hafızası: Tam Sistem Anlayışı

> Bu belge, tüm quant engine motorlarının çalışma mantığını, user stratejisini ve
> sistemin ne yapmaya çalıştığını kapsamlı biçimde dokumenter. Paper trading agent
> bu belgeyi "stratejik hafıza" olarak kullanır.

---

## 1. BÜYÜK RESİM: Ne Yapılıyor?

Bu sistem, **US preferred stock** (öncelikli hisse) piyasasında **çift yönlü portföy yönetimi** yapan
otomatik bir trading sistemidir. Temel felsefe:

### 1.1 Core Strateji
- **MEAN REVERSION (Ortalamaya Dönüş)**: Preferred stock'lar genellikle sabit gelirli
  menkul kıymetlerdir. Fiyatları bir "adil değer" etrafında salınır. Sistem bu
  sapmaları tespit edip exploit eder.
- **DÜŞÜK RİSK, YÜKSEK GETİRİ**: Solid fixed-income ürünlerden yüksek yield aranır.
  Capital appreciation potansiyeli olan düşük riskli fırsatlar hedeflenir.
- **ÇİFT YÖNLÜ**: Hem LONG (ucuz alana al) hem SHORT (pahalı olana sat) pozisyon açılır.

### 1.2 İşlem Felsefesi
- **HIDDEN (Gizli) Emirler**: Tüm emirler gizli gönderilir. Piyasaya görünmez.
- **SPREAD İçinde Pozisyonlanma**: Emirler bid-ask spread'inin %15'i kadar içeri konur.
  - BUY: `bid + spread × 0.15`
  - SELL: `ask - spread × 0.15`
- **Minimum Kâr Hedefi**: Her işlemde minimum $0.04-$0.07/hisse kâr hedeflenir.
- **Truth Tick Tabanlı**: Gerçek piyasa baskıları (100-200 lot FNRA, 15+ lot diğer)
  baz alınarak frontlama yapılır.

### 1.3 XNL/DUAL PROCESS: Sistem Nasıl Çalışıyor?

> ❗ **AGENT BU BÖLÜMÜ ANLAMAZSA SİSTEMİ ANLAYAMAZ**

Kullanıcı **Dual Process** adı verilen bir yöntemle **2 broker hesabı** arasında
sırayla geçiş yapar: **HAMPRO** (her zaman) + **IBKR hesabı** (IBKR_PED veya IBKR_GUN,
UI'dan seçilir, varsayılan IBKR_PED). Her hesap için bir **XNL fazı** çalışır.

**Her Hesap Fazında Olan Bitünşey (3.5 dakika):**

```
ADİM 1: Hesaba Geç → TÜM mevcut emirleri iptal et (REV dahil)
        → Neden? Çünkü eski fiyatlar bayatlıyor, her şey taze başlatmalı

ADİM 2: MinMax Area yeniden hesapla (taze BEFDAY + pozisyonlar)
        → Neden? Günlük limitler her hesap için farklı olabilir

ADİM 3: XNL Engine BAŞLAT → Initial Cycle çalıştırılır:
        a) prepare_cycle_request: Pozisyonlar, metrikler, exposure, L1 data
           hepsi bir anda toplanır (RUNALL katmanı)
        b) Skor hesaplama: FastScoreCalculator güncellenir (BB/FB/SAS/SFS)
        c) Phase 1: LT_TRIM çalışır → Satış emirleri üretir (portföy bakımı)
        d) Phase 2: KARBOTU/REDUCEMORE çalışır → Macro sinyallere göre al/sat
        e) Phase 3: ADDNEWPOS çalışır → Yeni pozisyon açma emirleri
        f) Phase 4: MM çalışır → Market making emirleri
        g) Conflict Resolution: Aynı hisse+yön için sadece en yüksek
           öncelikli motorın emri alınır (REV > LT > KARBOTU > ADDNEWPOS > MM)
        h) Tüm emirler FRONTLAMA kontrolünden geçirilir:
           - Truth tick'e bakılır
           - Fiyat truth tick'e göre ayarlanır (sacrifice limitleri içinde)
           - MinMax Area safety net uygulanır
           - Emir brokere gönderilir (HIDDEN!)

ADİM 3 (devam): 3.5 dakika bekle — bu sürede:
        - Emirler piyasada bekler ve dolmayı (fill) bekler
        - Front cycle döngüsü çalışır (açık emirleri günceller):
          Örnek: BUY emri $24.12'de açık, truth tick $24.10'a düştü
          → Frontlama emri $24.11'e çeker (truth tick + $0.01)

ADİM 4: XNL DURDUR (emirler piyasada kalır!)

ADIM 5: REV sağlık kontrolü (XNL sırasında dolmuş emirlere tepki)

        >>> 2 AŞAMALI FİYATLAMA <<<

        KOŞUL 1 (Kolay Yol - Max Kâr):
          BUY fill → mevcut ask'a bak → (ask - fill_price) ≥ $0.04 mi?
            EVET → ask - (spread * 0.15) fiyata hidden SELL koy (MAX kâr!)
            Örn: BUY fill @$25.50, ask=$25.56, spread=$0.06
              → SELL @$25.56-$0.009 = $25.55 → $0.05 kâr ✓
          SELL fill → mevcut bid'e bak → (fill_price - bid) ≥ $0.04 mi?
            EVET → bid + (spread * 0.15) fiyata hidden BUY koy (MAX kâr!)

        KOŞUL 2 (Orderbook Fallback - spread dar ise):
          KOŞUL 1 sağlanmıyorsa → Orderbook kademelerini tara
          BUY fill → ASK kademeleri yukarı doğru tara → ilk $0.04+ olan kademe
            → O kademenin $0.01 önüne hidden SELL koy
            Örn: BUY fill @$20.50, ask kademeleri: $20.52, $20.53, $20.58
              $20.52 → kâr $0.02 ✗, $20.53 → kâr $0.03 ✗, $20.58 → kâr $0.08 ✓
              → SELL @$20.57 (kademenin $0.01 önü)
          SELL fill → BID kademeleri aşağı doğru tara → ilk $0.04+ olan kademe
            → O kademenin $0.01 önüne hidden BUY koy

        → $0.04 = MİNİMUM kâr kuralı, hedef HER ZAMAN MAKSİMUM
        → Koşul 1: spread*0.15 offset (oransal), Koşul 2: $0.01 offset (sabit)
        → REV order health gap varsa HER ZAMAN olmalı, sadece NEREYE yazılacağı değişir
        → TÜM REV EMİRLERİ HIDDEN!

ADİM 6: REV emirlerini gönder

→ SONRA: Diğer hesaba geç, aynı döngüyü tekrarla
```

**NEDEN BÖYLE YAPILIYOR?**

1. **Çoklu hesap = Daha fazla likidite erişimi**: Farklı brokerler farklı order book'lar
2. **Her döngüde taze veri**: 3.5 dk'da piyasa değişti, eski emirler bayatlıyor
3. **REV her zaman sonra**: Çünkü fill'e reaksiyon verir, fill olmadan REV anlamsız
4. **Frontlama = Akilli emir yönetimi**: Piyasa hareketini takip ederek spread'i yakalamak
5. **MinMax/Company Limit = Risk kontrolü**: Hiçbir tek hisseye aşırı yüklenme

**AGENT NE ANLAMALI?**

Her XNL döngüsünde gönderilen her emir bir **SEBEPLA** gönderiliyor:
- LT_TRIM emri: "Bu hisse yeterince pahalılaştı, %20 azalt"
- KARBOTU emri: "FBTOT 1.3'e çıktı, bu hisse benchmark'ı aştı, sat"
- ADDNEWPOS emri: "Bu hisse ucuzluk skoru -0.12, FBTOT yüksek, GORT düşük, 400 lot al"
- MM emri: "Spread $0.08, score 45, 200 lot bid'e koy"
- REV emri: "500 lot BUY fill oldu @$25.50, ask $25.56, ask'ın önüne $25.55'e hidden SELL koy"

Agent bu SEBEPLERI anlayacak, gözlemleyecek, ve kendi de benzer mantıkla
karar verecek + kendi keşfettiği örüntüleri test edecek.

### 1.4 Portföy Ölçeği
- **POT_MAX (Tavan)**: $1.4M portföy tavanı
- **Ortalama 150+ hisse** takip edilir (preferred stock evreni)
- **Gruplar**: Hisseler DOS (group) bazlı kategorilere ayrılır

---

## 2. MOTOR HİYERARŞİSİ (Yüksek → Düşük Öncelik)

Sistemde 5 ana motor sıralı çalışır. Üst motor her zaman önceliklidir:

### 2.1 REV (Recovery/Maintenance) — Öncelik: ∞
**Amaç**: "Equation of Health" => `Gap = BEFDAY - POTENTIAL`
- **BEFDAY**: Günün başındaki planlanan pozisyon miktarı
- **POTENTIAL**: Mevcut miktar + bekleyen emirler
- Bir emir dolduğunda (fill) Gap oluşur → REV ekipmanı devreye girer
- **TP (Take Profit)**: Fill fiyatından $0.04 uzağa kâr al emri
- **RELOAD (Geri Al)**: Fill fiyatından $0.06 uzağa geri alım emri
- Orderbook'un ilk %15 spread mesafesine HIDDEN emir koyar
- **Gap Eşiği**: Min 200 lot fark olmalı

### 2.2 LT_TRIM (Strategic Reduction) — Öncelik: 30
**Amaç**: Pahalı (Long) veya ucuzlamış (Short) pozisyonları kademeli azaltma

**4 Aşamalı Befday Modeli:**

**Aşama 1 - Spread Kapısı:**
| Spread ≥ | Long Score ≥ | Short Score ≤ |
|----------|-------------|---------------|
| $0.06    | 0.08        | -0.08         |
| $0.10    | 0.05        | -0.05         |
| $0.15    | 0.02        | -0.02         |
| $0.25    | 0.00        | 0.00          |
| $0.45    | -0.02       | 0.02          |
| $10.0    | -0.08       | 0.08          |

**Aşama 2-4 - Kademeli Satış:**
| Aşama | Score (Long ≥) | Score (Short ≤) | Aksiyon           |
|-------|---------------|-----------------|-------------------|
| 2     | 0.10          | -0.10           | Befday'in %20'si  |
| 3     | 0.20          | -0.20           | +%20 daha         |
| 4     | 0.40          | -0.40           | +%20 daha         |

**Küçük Pozisyon (<400 lot):**
- Aşama 2 (Score 0.10): 200 lot sat
- Aşama 3 (Score 0.20): Pozisyonu kapat

### 2.3 KARBOTU (Macro Decision & Signal Engine) — Öncelik: 20
**Amaç**: FBTOT/SFSTOT (Fiyat/Benchmark) ve spesifik Score aralıklarına göre
pozisyon trim'leme. Ağırlıklı **OFANSIF** modda çalışır.

**Long Filtreleme (Steps 2-7):**
| Step | FBTOT Aralığı | Pahalılık Score | Lot %  |
|------|--------------|-----------------|--------|
| 2    | < 1.10       | ≥ -0.10         | 50%    |
| 3    | 1.11-1.45    | -0.05 → 0.04    | 25%    |
| 4    | 1.11-1.45    | ≥ 0.05          | 50%    |
| 5    | 1.46-1.85    | -0.05 → 0.02    | 15%    |
| 6    | 1.46-1.85    | ≥ 0.03          | 30%    |
| 7    | 1.86-2.10    | Any             | 10%    |

**Short Filtreleme (Steps 8-13):**
| Step | SFSTOT Aralığı | Lot %  |
|------|---------------|--------|
| 8    | Any           | 50%    |
| 9    | ≥ 1.70        | 50%    |
| 10   | 1.40-1.69     | 25%    |
| 11   | 1.40-1.69     | 50%    |
| 12   | 1.10-1.39     | 15%    |
| 13   | 1.10-1.39     | 30%    |

### 2.4 ADDNEWPOS (Entry Engine) — Öncelik: 15
**Amaç**: Yeni pozisyon açma. En düşük öncelik; sadece OFANSIF modda çalışır.

#### 2.4.1 Dört Sekme Sistemi: BB, FB, SAS, SFS

ADDNEWPOS'ta hisselere yapılan öneriler 4 farklı "sekme" (tab) üzerinden sunulur.
Her sekmenin kendi sıralama mantığı ve kullanım amacı vardır:

| Sekme | Tam İsim | Formül | Kullanım | Passive? |
|-------|----------|--------|----------|----------|
| **BB** | Bid Buy | `FINAL_THG - 1000 × bid_buy_ucuzluk` | Long pozisyon AÇMAK | ✅ Evet |
| **FB** | Front Buy | `FINAL_THG - 1000 × front_buy_ucuzluk` | FBTOT ölçümü (benchmark) | ❌ Hayır |
| **SAS** | Short Ask Sell | `SHORT_FINAL - 1000 × ask_sell_pahalilik` | Short pozisyon AÇMAK | ✅ Evet |
| **SFS** | Short Front Sell | `SHORT_FINAL - 1000 × front_sell_pahalilik` | SFSTOT ölçümü (benchmark) | ❌ Hayır |

**Kullanıcı genelde BB ve SAS sekmelerini kullanır.** Nedeni:

- **BB (Bid Buy)**: Bid'in hemen önüne HIDDEN emir koyar → `pf_bid_buy = bid + (spread × 0.15)`
  → Makası (spread'i) LEHİNE kullanır. Pasif fill almak istediği için bid tarafında bekler.
  → **BB ne kadar yüksekse, o hisse o kadar iyi Long adayıdır.**

- **SAS (Short Ask Sell)**: Ask'in hemen önüne HIDDEN emir koyar → `pf_ask_sell = ask - (spread × 0.15)`
  → Yine makası lehine kullanır. Pasif fill almak istediği için ask tarafında bekler.
  → **SAS ne kadar düşükse, o hisse o kadar iyi Short adayıdır.**

#### 2.4.2 PASSİF FİLL FELSEFESİ

Kullanıcının temel stratejisi: **Piyasaya emir fırlatmak yerine, piyasanın onun emrine gelmesini beklemek.**

```
LONG açarken:  BUY emri → bid + (spread × 0.15) → Bid'in 15% önünde bekle
SHORT açarken: SELL emri → ask - (spread × 0.15) → Ask'in 15% önünde bekle
```

Bu pasif yaklaşım sayesinde:
- Spread'in bir kısmını baştan kazanır (her işlemde $0.04-$0.07/hisse avantaj)
- Slippage minimize edilir
- Fill almak zaman alabilir ama alınan her fill spread-avantajlıdır

#### 2.4.3 FB ve SFS: Benchmark Ölçümü İçin

FB ve SFS sekmeleri doğrudan alım/satım için değil, **grup bazlı benchmark performansının**
ölçümü için kullanılır:

- **FB (Front Buy)**: `last + 0.01` fiyatından hesaplanır → Son print'in frontlaması
  → Bu değerden **FBTOT** metriği türetilir (grup içi ranking)
  → FBTOT > 1.10 = hisse kendi grubuna göre UCUZ
  
- **SFS (Short Front Sell)**: `last - 0.01` fiyatından hesaplanır → Son print'in frontlaması
  → Bu değerden **SFSTOT** metriği türetilir (grup içi ranking)
  → SFSTOT > 1.10 = hisse kendi grubuna göre PAHALI

#### 2.4.4 Giriş Filtreleri

**Long Giriş (BB sekmesi üzerinden):**
- `bid_buy_ucuzluk < -0.06` (grup benchmark'ına göre ucuz olmalı!)
- `fbtot > 1.10` (benchmark'a göre ucuz)
- `spread < $0.25`
- `AVG_ADV > 500`

**Short Giriş (SAS sekmesi üzerinden):**
- `ask_sell_pahalilik > 0.06` (grup benchmark'ına göre pahalı olmalı!)
- `sfstot > 1.10` (benchmark'a göre pahalı)
- `spread < $0.25`
- `AVG_ADV > 500`

#### 2.4.5 Lot Hesaplama (Mental Model v1)
```
Final Lot = Base Lot × Desire
Desire = (AddIntent/100)^α × (Goodness/100)^β
```
- **AddIntent**: Global risk ekleme isteği (Intent Model, exposure'a göre kısılır)
- **Goodness**: Hisse bazlı kalite skoru [0-100]
- **α = 1.0** (intent hassasiyeti), **β = 2.0** (goodness hassasiyeti — ağırlığı daha yüksek)

#### 2.4.6 MEAN REVERSION ZAMAN HORİZONU

> ⚠️ **KRİTİK KAVRAM**: FINAL_THG'si en yüksek veya SHORT_FINAL'ı en düşük olan hisseler
> **bugün hemen** iyi performans göstermeyebilir!

Preferred stock'lar mean reversion piyasasıdır. Bu yüzden:
- **Orta vade (15-20 gün)**: En iyi Long adaylarının outperform etmesi beklenir
- **Uzun vade (1-2 ay)**: En iyi Short adaylarının piyasayı underperform etmesi beklenir
- **Sabır gereklidir**: Skor bugün iyi olan hisse yarın değil, 2-3 hafta sonra sonuç verir
- **Portföy etkisi**: Tek hisse değil, portföy genelinde mean reversion çalışır

#### 2.4.7 PORTFÖY OLUŞTURMA PAİPLINE'I (ntumcsvport → JFIN)

ADDNEWPOS'ta hangi hisselere ne kadar lot açılacağı 6 aşamalı bir pipeline ile belirlenir:

**Aşama 1: TUMCSV Seçimi (ntumcsvport.py — Günlük Batch)**

Günlük `run_daily_n.py` çalıştırıldığında, her grup dosyasından (ssfinek*.csv) Long ve Short
adayları seçilir. İki kriter **kesişimi** (intersection) kullanılır:

```
LONG seçim = Top X% (Final FB skoru en yüksek) ∩ (Final FB ≥ Ortalama × Çarpan)
SHORT seçim = Bottom X% (Final SFS skoru en düşük) ∩ (Final SFS ≤ Ortalama × Çarpan)
```

Her grup için özel kurallar vardır:

| Grup | Long Top% | Long Çarpan | Short Bottom% | Short Çarpan | Max Short |
|------|-----------|------------|---------------|-------------|----------|
| heldkuponlu | 35% | 1.3x | 35% | 0.75x | ∞ (özel mantık) |
| heldff | 25% | 1.6x | 10% | 0.35x | 2 |
| heldflr | 20% | 1.7x | 10% | 0.35x | 2 |
| heldsolidbig | 15% | 1.7x | 10% | 0.35x | 2 |
| highmatur | 20% | 1.7x | 5% | 0.2x | 2 |
| Varsayılan | 25% | 1.5x | 25% | 0.7x | 3 |

**Aşama 2: Company Limit (CMON Sınırlaması — /1.6 Kuralı)**

Aynı şirketten (CMON) çok fazla hisse seçilmesini önler:
```
max_allowed = max(1, round(şirketin_toplam_hisse_sayısı / 1.6))
```

Örnek: Bir şirketin 5 preferred hissesi varsa → max 3 tanesi seçilebilir.
Seçim sırası: Long için en yüksek Final FB, Short için en düşük Final SFS.

**Aşama 3: CGRUP Sınırlaması (Maksimum 3 hisse/grup)**

Aynı alt gruptan (CGRUP) en fazla 3 hisse seçilebilir.
Bu da çeşitlendirmeyi (diversification) sağlar.

**Aşama 4: RECSIZE Hesaplama (Önerilen Lot Boyutu)**

Her seçilen hisse için önerilen lot boyutu hesaplanır:
```
KUME_PREM = Hissenin Final skoru - Şirketin (CMON) ortalama skoru
RECSIZE = round((KUME_PREM × 8 + AVG_ADV / 25) / 4 / 100) × 100
MAX_RECSIZE = round(AVG_ADV / 6 / 100) × 100
RECSIZE = min(RECSIZE, MAX_RECSIZE)
```

Bu formül şunu söyler:
- **KUME_PREM yüksekse** (hisse kendi şirket kardeşlerinden çok daha iyi)→ daha büyük lot
- **AVG_ADV yüksekse** (hisse likit)→ daha büyük lot izni
- Ama **AVG_ADV/6** ile hard cap uygulanır (likiditeyi aşma yasak)
- HELDFF grubu için çarpanlar daha agresif: `KUME_PREM × 12`, `AVG_ADV/4` cap

**Aşama 5: JFIN Engine (Gerçek Zamanlı Lot Dağıtımı)**

JFIN, ntumcsvport'un çıktılarını alarak gerçek zamanlı lot dağıtımı yapar:

```
1. Grup bazlı toplam lot hakkı:
   Group Lot = Total Rights × (Group Weight / 100) × Alpha

2. Skor bazlı dağıtım (her hisseye):
   Stock Lot = Group Lot × (Stock Score / Group Total Score)

3. MAXALW klipleme:
   Addable Lot = min(Calculated Lot, MAXALW - CurrentPosition, Rule Limit)

4. Yüzde uygulama:
   Final Lot = Addable Lot × (JFIN Percentage / 100)  [25%, 50%, 75%, 100%]

5. Fiyat hesaplama:
   BB: bid + (spread × 0.15)   SAS: ask - (spread × 0.15)
   FB: last + 0.01             SFS: last - 0.01

6. Intent oluşturma (emir DEĞİL, kullanıcı onayı gerekir)
```

Konfigürasyon:
- `total_long_rights`: 28,000 lot (tüm Long'lar için toplam)
- `total_short_rights`: 12,000 lot (tüm Short'lar için toplam)
- `min_lot_per_order`: 200 lot minimum
- `lot_rounding`: 100'e yuvarlama

**Aşama 6: HELDKUPONLU Özel Mantığı**

En büyük grup olan heldkuponlu için özel seçim kuralları:
- C600, C625 grupları: Zorunlu seçim YOK (sadece kurallara uyanlar)
- Diğer tüm CGRUP'lar: Her gruptan EN İYİ 1 Long + EN KÖTÜ 1 Short **zorunlu** seçilir
- Kalan slotlar skora göre doldurulur
- Her CGRUP'tan toplam max 3 hisse
- Company limit yine /1.6 kuralıyla uygulanır

#### 2.4.8 MAXALW VE GÜNLÜK LİMİTLER

**MAXALW (Maximum Allowed)**: Her hisse için tanımlanan maximum pozisyon büyüklüğü.
Static CSV'den okunur. Varsayılan: 5000 lot.

**Günlük Limit Servisi (Fren Mekanizması):**

Portföy büyüklüğüne göre günlük artış/azalış limitleri:

| Portföy % | MAXALW Çarpanı (Artış) | Portföy Limiti (Artış) |
|-----------|----------------------|----------------------|
| < 1%      | 0.50                 | 5.0%                 |
| < 3%      | 0.40                 | 4.0%                 |
| < 5%      | 0.30                 | 3.0%                 |
| < 7%      | 0.20                 | 2.0%                 |
| < 10%     | 0.10                 | 1.5%                 |
| ≥ 10%     | 0.05                 | 1.0%                 |

Yani büyük pozisyon (portföyün 10%+) için günde sadece MAXALW × 0.05 kadar artırabilir.
Küçük pozisyon (< 1%) için MAXALW × 0.50 artırabilir.

Azaltma limitleri ise BEFDAY bazlıdır:
| Portföy % | Limit |
|-----------|-------|
| < 3%      | Sınırsız |
| < 5%      | MAXALW × 0.75 |
| < 7%      | MAXALW × 0.60 |
| < 10%     | MAXALW × 0.50 |
| ≥ 10%     | MAXALW × 0.40 |

### 2.5 GREATEST MM (Market Making) — Öncelik: 10
**Amaç**: Spread arbitrajı ile küçük, hızlı kâr.

**Çalışma Prensibi:**
- Minimum spread $0.06 gerekli
- Son5Tick (son 5 truth tick'in modu) hesaplanır
- 4 senaryo analizi yapılır (hem LONG hem SHORT potansiyel)
- Score aralığı: 30 ≤ score < 250
- Sabit 200 lot ile işlem
- Truth Tick tabanlı fill takibi

---

## 3. EXPOSURE REJİMLERİ (Portföy Koruması)

Portföy büyüklüğüne göre 3 mod:

| Rejim      | Aralık      | Aktif Motorlar        | Duruş           |
|------------|------------|----------------------|-----------------|
| **OFANSIF** | < 92.7%    | KARBOTU + ADDNEWPOS  | Büyüme          |
| **GEÇIŞ**   | 92.7-95.5% | KARBOTU + REDUCEMORE | Dikkatli küçülme |
| **DEFANSIF** | > 95.5%    | REDUCEMORE           | Panik küçülme    |

### 3.1 Güvenlik Katmanları
1. **Intent Throttle (84.9%)**: ADDNEWPOS lot boyutu kademeli azalır
2. **Hard Risk (92%)**: Yeni pozisyon artırma YASAK
3. **Geçiş (92.7%)**: KARBOTU + REDUCEMORE aktif
4. **Defansif (95.5%)**: Sadece REDUCEMORE

### 3.2 HEAVY Mode (Manuel Acil Durum)
- Tüm macro filtreleri bypass eder
- Score ≥ 0.02 yeterli
- %30 pozisyon azaltma
- FBTOT/SFSTOT, SMA63, spread gating — hepsi devre dışı

---

## 4. KRİTİK METRİKLER

### 4.1 FINAL_THG Formülü (Tam Detay)

**FINAL_THG**, her hissenin Long tarafı genel kalite skorudur. Günlük batch'te hesaplanır
(`ncalculate_thebest.py`). Grup tipine göre **farklı formüller** kullanılır:

**Standart Gruplar (heldkuponlu, heldkuponlukreorta, heldkuponlukreciliz, vb.):**
```
EX_FINAL_THG = (
  (SMA20_norm × 0.4 + SMA63_norm × 0.9 + SMA246_norm × 1.1) × 2.4
  + (1Y_High_diff_norm + 1Y_Low_diff_norm) × 2.2
  + Aug4_chg_norm × 0.50
  + Oct19_chg_norm × 0.50
  + SOLIDITY_SCORE_NORM × solidity_weight
  + CUR_YIELD_LIMITED × yield_weight × 0.75
  + AVG_ADV × adv_weight
  + SOLCALL_SCORE_NORM × solcall_weight × 0.85
  + CREDIT_SCORE_NORM × credit_weight
)

FINAL_THG = EX_FINAL_THG × 0.6 + GORT_NORM × 10
```

**Özel Gruplar (farklı formüller):**
- **YTM Grupları** (heldbesmaturlu, heldhighmatur, notbesmatur, highmatur):
  `FINAL_THG = YTM_NORM × 4 + SMA63_norm × 9 + SOLIDITY_NORM × 2`
- **YTC Grupları** (helddeznff, heldnff):
  `FINAL_THG = YTC_NORM × 3 + SOLIDITY_NORM × 2 + SMA63_norm × 10`
- **EXP_RETURN Grupları** (heldff, heldflr, heldsolidbig, heldtitrekhc, nottitrekhc):
  `FINAL_THG = SOLIDITY_NORM × 2 + SMA63_norm × 13`

Bileşenler:
- **SMA20/63/246_norm**: Hareketli ortalama değişimleri (5-95 normalize)
- **SOLIDITY_SCORE**: Şirketin finansal sağlamlığı (kredi notu, market cap)
- **CUR_YIELD**: Mevcut temettü verimi (max 10'a kısılır)
- **GORT_NORM**: Grup bazlı relatif trend (TERSİNE normalize: düşük GORT = yüksek skor = iyi)
- **SOLCALL_SCORE**: Adj Risk Premium + Solidity kombinasyonu (kuponlu gruplarda)
- **YTM/YTC**: Yield to Maturity / Yield to Call (vade/çağrı getirisi)

### 4.2 SHORT_FINAL Formülü

```
SHORT_FINAL = FINAL_THG + (SMI × 1000)
```

- **SMI (Short Margin Interest)**: Short maliyeti/faiz oranı
- SMI yüksekse → SHORT_FINAL yükselir → Short'a daha az uygun
- SMI düşükse → SHORT_FINAL düşer → **En düşük SHORT_FINAL = En iyi Short adayı**

Yani SHORT_FINAL, FINAL_THG'ye short maliyetini ekleyerek o hissenin short'a
ne kadar uygun olduğunu ölçer.

### 4.3 Canlı Skorlar (Fast Score Calculator)

Gün içi, real-time olarak L1 market data'dan türetilen skorlar:

- **bid_buy_ucuzluk**: `(bid + spread×0.15 - prev_close) - benchmark_chg`
  - Negatif = hisse benchmark'tan daha ucuz (Long al!)
- **ask_sell_pahalilik**: `(ask - spread×0.15 - prev_close) - benchmark_chg`
  - Pozitif = hisse benchmark'tan daha pahalı (Short at!)
- **FBTOT**: Front Buy Total (grup rank + oran) → > 1.10 = UCUZ
- **SFSTOT**: Short Front Sell Total → > 1.10 = PAHALI
- **GORT**: `0.25×(SMA63-grp_avg) + 0.75×(SMA246-grp_avg)`
  - Long: GORT düşükken al, yükselince sat
  - Short: GORT yüksekken short, düşünce kapat
- **SMA63_CHG / SMA246_CHG**: Momentum ve uzun vadeli trend göstergeleri
- **Benchmark_CHG**: Grup ortalama günlük değişimi (cent cinsinden)

### 4.4 Grup Analizi (DOS/CGRUP)

Hisseler ~20 gruba ayrılır. Her grubun:
- Ortalama fiyat değişimi izlenir
- Üyelerin mean reversion davranışı karşılaştırılır
- Grup "yönü" (alıcı/satıcı baskısı) tespit edilir
- Company limit ve CGRUP limit bu yapıya göre çalışır

Önemli gruplar: heldkuponlu (en büyük), heldff, heldflr, heldsolidbig,
heldbesmaturlu, helddeznff, heldnff, highmatur, notbesmatur, heldtitrekhc

---

## 5. GÜVENLİK KURALLARI

### 5.1 Zero-Snap Kuralı (Anti-Remnant)
- DECREASE emirlerinde kalan miktar -400 ile +400 arasına düşecekse
  pozisyon TAMAMEN kapatılır
- "İncik cincik" pozisyon kalmasını engeller

### 5.2 MinMax Area (Hard Perimeter)
- Her hisse için günlük min/max miktar belirlenir
- BEFDAY + MAXALW'den hesaplanır
- TÜM motorlar bu limitlere tabidir (HEAVY dahil)

### 5.3 Downward Lot Rounding
- Agresif azaltma motorları lot'u AŞAĞI yuvarlar
- 528 → 500, 266 → 200, 105 → 100

### 5.4 Frontlama Sacrifice Limitleri
| Tag        | Max Cent  | Max Spread Oranı | Açıklama          |
|------------|----------|------------------|--------------------|
| MM_*_DEC   | $0.60    | 50%              | En agresif (Kâr Al)|
| LT_*_DEC   | $0.35    | 25%              | Risk azaltma       |
| LT_*_INC   | $0.10    | 10%              | Pozisyon artırma   |
| MM_*_INC   | $0.07    | 7%               | En katı            |

---

## 6. CONFLICT RESOLUTION (Çatışma Çözümü)

Birden fazla motor aynı hisse için emir ürettiğinde:
1. **Grup by**: Symbol + Action bazında grupla
2. **Öncelik sırası**: Emergency(40) > Reducemore(30) > Karbotu(20) > LT(10)
3. **Eşit öncelikte**: MAX lot kazanır
4. **Residual Logic**: Alt motora kalan miktar verilir (Karbotu=1000, LT=400 → LT=400, Karbotu=600)

---

## 7. DUAL PROCESS (Çoklu Hesap)

Sistem birden fazla broker hesabıyla çalışır:
- **HAMPRO**: Hammer Pro (hızlı execution)
- **IBKR_PED**: Interactive Brokers PED hesap
- **IBKR_GUN**: Interactive Brokers GUN hesap

3.5 dakika arayla hesap değiştirir (DualProcessRunner):
1. Hesap Değiştir
2. Eski emirleri iptal et (REV emirleri hariç)
3. Bekleyen REV emirlerini gönder
4. XNL Engine'i başlat

---

## 8. USER RECOMMENDED STRATEJI (Ayrı Mekanizma)

> Bu bölüm, kullanıcının (user) subjektif olarak önerdiği, deneyimine dayalı
> stratejileri kapsar. Agent bu önerileri "kurallar" olarak değil, "hipotezler"
> olarak değerlendirir ve performanslarını ayrı izler.

### 8.1 User Insights
- **Preferred'lar spread'i geniş olan illiquid enstrümanlardır**: Bu hem fırsat hem risk
- **Group behavior matters**: Bir grubun yönelimi, bireysel hisseyi etkiler
- **Timing önemli**: Piyasa açılışında spreadler geniş, öğleden sonra daralır
- **Mean reversion en güçlü sinyal**: Score yükseldikçe satış, düştükçe alış
- **Truth Tick doğrulaması şart**: Gerçek olmayan işlemlere (odd-lot, manipulation) tepki verme
- **Risk yönetimi büyümeden önce gelir**: REV > LT_TRIM > KARBOTU > ADDNEWPOS sırası kutsal

### 8.2 User Tarafından Test Edilmek İstenen Hipotezler
(Agent bu hipotezleri günlük olarak ölçer ve sonuçları raporlar)
1. "Spread $0.20'den fazla olan hisselerde MM daha kârlı"
2. "GORT ekstremi (-2 ve altı veya +2 ve üstü) olan hisseler güçlü mean reversion yapar"
3. "FBTOT > 1.50 satılan hisseler çoğunlukla tekrar ucuzlar" (premature sell riski)
4. "Grup yön değiştirdiğinde (alıcı→satıcı) bireysel hisseler 1-2 gün gecikmeli tepki verir"
5. "Piyasa açılışının ilk 30 dakikasında yapılan MM emirleri daha sık dolar"

---

## 9. AGENT'IN KENDİ FİKİR ÜRETME MEKANİZMASI

Agent, aşağıdaki verileri toplayarak kendi hipotezlerini oluşturur:

### 9.1 Toplanacak Veriler (Her Scan'de)
- Her hissenin spread'i, bid/ask/last, truth tick sayısı
- Alıcı/satıcı oranı (bid size vs ask size)
- Grup genelindeki hareket yönü
- Fill oranı (kaç emir doldu / kaç emir konuldu)
- Hold süresi vs PnL korelasyonu

### 9.2 Fikir Üretme Süreci
1. **Pattern Detection**: N gün veriden tekrarlayan kalıplar tespit et
2. **Korelasyon Analizi**: Hangi metrikler fill/PnL ile korelasyon gösteriyor?
3. **Hypothesis Formation**: "X metriği Y threshold'unu geçtiğinde Z olasılığı artıyor"
4. **Backtesting**: Hipotezi geçmiş verilerle doğrula
5. **Paper Test**: Doğrulanan hipotezi paper trade'de test et
6. **Raporlama**: Sonuçları günlük raporda sun

### 9.3 Başarı Ölçütleri
| Metrik                     | Hedef      |
|---------------------------|------------|
| Günlük Net PnL             | > $0       |
| Fill Rate                  | > %30      |
| Win Rate                   | > %55      |
| Avg Win / Avg Loss         | > 1.5      |
| Max Drawdown               | < $5,000   |
| Sharpe Ratio (annualized)  | > 1.0      |

---

## 10. GÜNLÜK RAPORLAMA YAPISI

Her gün sonunda agent şunları raporlar:

### 10.1 USER Strateji Performansı
- Bu günün kural bazlı sonuçları
- Hangi kurallar iyi çalıştı, hangisi başarısız
- Kural bazlı PnL breakdown

### 10.2 Agent Kendi Stratejisi
- Agent'ın kendi hipotezlerinin sonuçları
- Yeni tespit edilen kalıplar
- Önerilen parametre değişiklikleri

### 10.3 Karşılaştırma
- User rules vs Agent rules performans karşılaştırması
- "Bugün user kuralları $X kâr/zarar etti, agent kuralları $Y kâr/zarar etti"
- Öğrenilen dersler

---

## 11. SÖZLÜK

| Terim          | Açıklama                                              |
|---------------|------------------------------------------------------|
| BEFDAY        | Before Day — günün başındaki pozisyon planı            |
| POTENTIAL     | Current + Pending emirler                              |
| FBTOT         | Front Buy Total — benchmark'a göre ucuzluk             |
| SFSTOT        | Short Front Sell Total — benchmark'a göre pahalılık    |
| GORT          | Group Ortalama Relative Trend                          |
| Ucuzluk       | Bid tarafı cheapness score (negatif = ucuz)            |
| Pahalılık     | Ask tarafı expensiveness score (pozitif = pahalı)      |
| Truth Tick    | Doğrulanmış gerçek piyasa işlemi                       |
| Frontlama     | Aktif emirleri gerçek piyasaya göre güncelleme          |
| Sacrifice     | Frontlama sırasında kabul edilen fiyat kaybı           |
| OFANSIF       | Büyüme modu — tüm motorlar aktif                      |
| GEÇIŞ         | Geçiş modu — seçici büyüme + agresif küçülme          |
| DEFANSIF      | Savunma modu — sadece küçülme                          |
| HEAVY         | Manuel acil küçülme                                    |
| MinMax Area   | Günlük min/max pozisyon limitleri                      |
| Zero-Snap     | <400 lot kalan pozisyonu tamamen kapat                 |
| Incik Cincik  | Anlamsız küçük pozisyon artığı                         |
| DOS/CGRUP     | Hisse grubu/sektör kategorisi                          |

---

*Bu belge, paper trading agent'ın "beyni" olarak görev yapar.
Agent her scan'de bu kurallara başvurur, kararlarını açıklar ve sonuçlarını ölçer.*

---

## 12. AGENT ÖĞRENME ARCHİTEKTÜRÜ (Dual-Mode)

Agent, iki paralel modda çalışır:

### 12.1 MOD A: User-Based Yaklaşım (Önce Anla, Sonra Taklit Et)

**Amaç**: User'ın mevcut sistemiyle aynı karar mantığını geliştirmek.

**Nasıl Çalışır:**
1. Her XNL döngüsünde gönderilen emirleri gözlemle
2. Her emrin SEBEBINI anla:
   - Hangi motor üretti? (LT_TRIM? KARBOTU? ADDNEWPOS? MM?)
   - Hangi skorlar tetikledi? (FBTOT > 1.10? Ucuzluk < -0.06?)
   - Hangi guard'lardan geçti? (MAXALW ok? Company limit ok? MinMax ok?)
3. Emrin sonucunu izle:
   - Fill oldu mu? Kaç dakikada doldu?
   - Fill fiyatı ne? Spread'in neresinde doldu?
   - TP/RELOAD geldi mi? PnL ne oldu?
4. İstatistik topla:
   - Hangi motor en kârlı? (LT_TRIM? KARBOTU? ADDNEWPOS?)
   - Hangi skor aralığında en çok fill oluyor?
   - Hangi saatlerde fill oranı yüksek?
   - Hangi gruplarda mean reversion hızlı çalışıyor?
5. User stratejisini paper trade et:
   - Aynı kurallarla, aynı filtrelerle sanal emir gönder
   - Performansı ölç ve raporla

**Karara Dönüştürme**:
```
Agent görür: "ADDNEWPOS, ABC-PD'ye 400 lot BUY gönderdi
  Çünkü: ucuzluk=-0.14, FBTOT=1.25, spread=$0.04, grup=heldkuponlu"

Agent öğrenir: "Ucuzluk < -0.10 VE FBTOT > 1.20 olduğunda
  fill oranı %78, ortalama kâr $0.06/hisse, ortalama dolma süresi 8 dk"

Agent karar verir: "Bu koşullar iyi, paper trade'de de 400 lot BUY"
```

### 12.2 MOD B: Bağımsız Öğrenme (Keşfet ve Test Et)

**Amaç**: User'ın kuralları dışında kendi örüntülerini keşfetmek.

**Canlı Gözlem Alanları:**

1. **Spread Dynamics** (Sürekli İzle):
   - Hangi hisselerde spread genellikle daralıyor/açılıyor?
   - Spread daraldığında fiyat hareket eder mi?
   - Spread > $0.15 olan hisselerde MM daha kârlı mı?

2. **Volume Örüntüleri** (Truth Tick Bazlı):
   - Günün hangi saatinde volume spike oluyor?
   - Volume spike → fiyat hareketi korelasyonu var mı?
   - Büyük lot işlemler (1000+) sonrası ne oluyor?

3. **Grup Momentum** (30 dk Periyotlar):
   - Bir grup yukarı hareket ederken hangi üyeler geride kalıyor?
   - Geride kalan üyeler catch-up yapıyor mu? (mean reversion içinde mean reversion)
   - ETF hareketleri preferred stock'ları ne kadar etkiliyor?

4. **Fill Pattern Analizi**:
   - Pasif emirler (spread içinde) kaç dakikada doluyor?
   - Fill süresi ile kârlılık arasında korelasyon var mı?
   - Hızlı fill = iyi mi kötü mü? (adverse selection riski)

5. **Cross-Symbol İlişkiler**:
   - Aynı şirketten iki preferred stock arasındaki spread daralıyor mu?
   - Pair trading fırsatları var mı?
   - CGRUP içinde leadership hisseyi takip eden follower'lar var mı?

6. **Kolay Para Fırsatları** (Agent'ın Asıl Hedefi):
   - Düşük riskli, yüksek olasılıklı trade'ler:
     - Ex-dividend öncesi/sonrası fiyat davranışları
     - Market open/close spread pattern'leri
     - GORT extrem dönüşlerinde agresif pozisyon
     - MM'de tekrar eden fill pattern'leri

**Hipotez Oluşturma ve Test:**
```
Agent gözlemler: "Son 5 günde, saat 10:30-11:00 arasında
  heldff grubunda spread ortalama %40 daralıyor"

Agent hipotez kurar: "10:30'da heldff'de MM emri açarsam
  spread daralmasından önce fill olur, sonra spread açılınca kâr ederim"

Agent paper test eder: 5 gün boyunca bu hipotezi test et
Sonuçları raporla: Win rate, avg PnL, risk/reward
```

### 12.3 Canlı Raporlama Döngüsü

| Frekans | Analiz Türü | İçerik |
|---------|------------|--------|
| 5 dk    | Quick Check | Anomali tarama, acil fırsat algılama |
| 30 dk   | Trend Analiz | Grup trendleri, momentum değişimi |
| 2 saat  | Deep Analiz | Strateji performansı, hipotez güncelleme |
| Gün sonu| Günlük Rapor | User vs Agent performans, öğrenilen dersler |

### 12.4 Bilgi Akışı

```
LİVE PİYASA VERİSİ (Redis, L1 Data, Truth Ticks)
       ↓
Metrics Collector (snapshot üretir)
       ↓
┌─────────────────────────────────────────┐
│ MOD A: User Logic                         │
│ - XNL emirlerini gözlemle                  │
│ - Sebepleri anla (motor + skor)            │
│ - Sonuçları ölç (fill, PnL)               │
│ - Aynı mantıkla paper trade et             │
└─────────────────────────────────────────┘
       ↓                    ↓
┌─────────────────────────────────────────┐
│ MOD B: Bağımsız Öğrenme                  │
│ - Spread/volume/momentum gözle            │
│ - Örüntü keşfet                            │
│ - Hipotez oluştur + test et                │
│ - Kolay para fırsatlarını bul              │
└─────────────────────────────────────────┘
       ↓
GÜNLÜK RAPOR (User vs Agent karşılaştırması)
       ↓
STRATEJİ DNA GÜNCELLEME (bu belge evrilir)
```

---

*Bu belge, paper trading agent'ın "beyni" olarak görev yapar.
Agent her scan'de bu kurallara başvurur, kararlarını açıklar ve sonuçlarını ölçer.
Mod A ile user'ın büyük resmini anlayarak taklit eder;
Mod B ile kendi deneyimlerinden öğrenerek daha iyi fırsatlar keşfeder.*

*Son güncelleme: 2026-02-17*
