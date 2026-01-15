# JANALL SKORLAMA METRİKLERİ - DETAYLI AÇIKLAMA

## 📊 GENEL BAKIŞ

Bu dokümantasyon, janall uygulamasındaki tüm skorlama metriklerini ve hesaplama formüllerini açıklar.

---

## 1️⃣ PORT ADJUSTER (Portföy Ayarlayıcı)

### Ne Yapar?
Port Adjuster, portföyünüzdeki lot dağıtımını yönetir ve optimize eder.

### Özellikler:
- **Total Exposure**: Toplam portföy değeri (örn: 1,000,000 USD)
- **Avg Pref Price**: Ortalama preferred stock fiyatı (örn: 25 USD)
- **Long/Short Ratio**: Long ve Short pozisyonların yüzdesi (örn: %85 Long, %15 Short)
- **Lot Hakları**: Long ve Short için toplam lot miktarları

### Nasıl Çalışır?
1. Total Exposure ve Avg Pref Price'dan **Total Lot** hesaplanır:
   ```
   Total Lot = Total Exposure / Avg Pref Price
   ```

2. Long/Short ratio'ya göre lot dağıtımı yapılır:
   ```
   Long Lot = Total Lot × (Long Ratio / 100)
   Short Lot = Total Lot × (Short Ratio / 100)
   ```

3. Her grup (heldff, heldkuponlu, vs.) için yüzde belirlenir ve lot dağıtımı yapılır.

### Kullanım:
- Portföyünüzün risk dağılımını kontrol eder
- Grup bazlı lot dağıtımı yapar
- Exposure limitlerini yönetir

---

## 2️⃣ BID BUY UCUZLUK & ASK SELL PAHALILIK SKORLARI

### Bid Buy Ucuzluk (Bid'den Alış Ne Kadar Ucuz?)

**Formül:**
```
1. Passive Fiyat Hesaplama:
   pf_bid_buy = bid + (spread × 0.15)

2. Değişim Hesaplama:
   pf_bid_buy_chg = pf_bid_buy - prev_close

3. Ucuzluk Skoru:
   bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
```

**Açıklama:**
- Bid'den alış yaparsanız, spread'in %15'ini ödersiniz
- Bu fiyatın prev_close'a göre değişimi hesaplanır
- Benchmark (ETF) değişimi çıkarılarak **göreceli ucuzluk** bulunur
- **Pozitif değer** = Benchmark'a göre daha ucuz
- **Negatif değer** = Benchmark'a göre daha pahalı

### Ask Sell Pahalılık (Ask'ten Satış Ne Kadar Pahalı?)

**Formül:**
```
1. Passive Fiyat Hesaplama:
   pf_ask_sell = ask - (spread × 0.15)

2. Değişim Hesaplama:
   pf_ask_sell_chg = pf_ask_sell - prev_close

3. Pahalılık Skoru:
   ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
```

**Açıklama:**
- Ask'ten satış yaparsanız, spread'in %15'ini kaybedersiniz
- Bu fiyatın prev_close'a göre değişimi hesaplanır
- Benchmark değişimi çıkarılarak **göreceli pahalılık** bulunur
- **Pozitif değer** = Benchmark'a göre daha pahalı (iyi - satış için)
- **Negatif değer** = Benchmark'a göre daha ucuz (kötü - satış için)

---

## 3️⃣ FRONT BUY & FRONT SELL SKORLARI

### Front Buy (Last Print + $0.01 ile Alış)

**Formül:**
```
1. Passive Fiyat:
   pf_front_buy = last_price + 0.01

2. Değişim:
   pf_front_buy_chg = pf_front_buy - prev_close

3. Ucuzluk Skoru:
   front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
```

**Açıklama:**
- Son işlem fiyatının **1 cent üstüne** emir verirsiniz
- Bu, spread'in ortasına yakın bir fiyattır
- **Pozitif değer** = Benchmark'a göre ucuz
- **Negatif değer** = Benchmark'a göre pahalı

### Front Sell (Last Print - $0.01 ile Satış)

**Formül:**
```
1. Passive Fiyat:
   pf_front_sell = last_price - 0.01

2. Değişim:
   pf_front_sell_chg = pf_front_sell - prev_close

3. Pahalılık Skoru:
   front_sell_pahalilik = pf_front_sell_chg - benchmark_chg
```

**Açıklama:**
- Son işlem fiyatının **1 cent altına** emir verirsiniz
- Bu, spread'in ortasına yakın bir fiyattır
- **Pozitif değer** = Benchmark'a göre pahalı (iyi - satış için)
- **Negatif değer** = Benchmark'a göre ucuz (kötü - satış için)

### Bid Sell Pahalılık & Ask Buy Ucuzluk

**Bid Sell Pahalılık:**
```
pf_bid_sell = bid - 0.01
pf_bid_sell_chg = pf_bid_sell - prev_close
bid_sell_pahalilik = pf_bid_sell_chg - benchmark_chg
```

**Ask Buy Ucuzluk:**
```
pf_ask_buy = ask + 0.01
pf_ask_buy_chg = pf_ask_buy - prev_close
ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
```

---

## 4️⃣ FINAL SKORLAR (800 Katsayılı)

### Final BB (Final Bid Buy)
```
Final BB = FINAL_THG - (800 × bid_buy_ucuzluk)
```

### Final FB (Final Front Buy)
```
Final FB = FINAL_THG - (800 × front_buy_ucuzluk)
```

### Final AS (Final Ask Sell)
```
Final AS = FINAL_THG - (800 × ask_sell_pahalilik)
```

### Final FS (Final Front Sell)
```
Final FS = FINAL_THG - (800 × front_sell_pahalilik)
```

### Final SAS (Final Short Ask Sell)
```
Final SAS = SHORT_FINAL - (800 × ask_sell_pahalilik)
```

### Final SFS (Final Short Front Sell)
```
Final SFS = SHORT_FINAL - (800 × front_sell_pahalilik)
```

**Açıklama:**
- **800 katsayısı**: Ucuzluk/pahalılık skorlarının ağırlığı
- **FINAL_THG**: Long pozisyonlar için temel skor (CSV'den)
- **SHORT_FINAL**: Short pozisyonlar için temel skor (CSV'den)
- **Daha yüksek Final skor** = Daha iyi alış/satış fırsatı

---

## 5️⃣ FBTOT & SFSTOT (Toplam Skorlar)

### Fbtot (Final Buy Total - Long Pozisyonlar İçin)

**Formül:**
`Fbtot = FBplagr + FBratgr` (Basit Toplam)

**Bileşenlerin Gizli Mantığı (Balanced/Dengeli Logic):**
Kullanıcı seçimi üzerine formül "Dengeli" (Balanced) senaryoya güncellenmiştir. Sıralama ve Oran **eşit ağırlıklıdır (1.0)**:
1.  **FBplagr (Ağırlıklı Rank):** `(Ham Rank / Grup Sayısı) * 1.0`
2.  **FBratgr (Ağırlıklı Ratio):** `(Final FB / Grup Ortalaması) * 1.0`

Bu sayede **Fbtot**, hem sıra hem de performans farkına eşit önem verir.

**Terimlerin Net Anlamı (Janall Kaynaklı):**
*   **Ham Rank (Sıralama):** Hissenin grubu içindeki **küçükten büyüğe (Ascending)** sıralamadaki yeridir.
    *   *Mantık:* Yüksek puan = Yüksek Rank.
*   **Grup Sayısı:** O grupta bulunan ve geçerli (0'dan büyük) 'Final FB' puanına sahip toplam hisse sayısıdır.

**Yorumlama:**
- **Daha YÜKSEK Fbtot** = Daha **İYİ** Long (Alış) fırsatı.
- **Daha DÜŞÜK Fbtot** = Long pozisyonu kapatmak (Cover) veya azaltmak için daha uygun.

### SFStot (Short Front Sell Total - Short Pozisyonlar İçin)

**Formül:**
`SFStot = SFSplagr + SFSRatgr` (Basit Toplam)

**Bileşenlerin Gizli Mantığı (Balanced/Dengeli Logic):**
Aynı şekilde Short tarafında da bileşenler eşit ağırlıklıdır:
1.  **SFSplagr (Ağırlıklı Rank):** `(Ham Rank / Grup Sayısı) * 1.0`
2.  **SFSRatgr (Ağırlıklı Ratio):** `(Final SFS / Grup Ortalaması) * 1.0`

**Terimlerin Net Anlamı:**
*   **Ham Rank:** Hissenin, Final SFS puanına göre **küçükten büyüğe** sıralamasıdır.
    *   *Mantık:* Düşük SFS puanı (Short için iyi) = Düşük Rank.
*   **Grup Sayısı:** O grupta geçerli 'Final SFS' puanı olan toplam hisse sayısıdır.

**Yorumlama:**
- **Daha DÜŞÜK SFStot** = Daha **İYİ** Short fırsatı.
- **Daha YÜKSEK SFStot** = Short pozisyonu kapatmak (Cover) için daha uygun.
- Düşük SFStot, hissenin ranking'de alt sıralarda (düşük puanlı/cazip) olduğunu gösterir.

---

## 6️⃣ GORT (Grup Ortalama Relative Trend)

### Formül:
```
GORT = (0.25 × (SMA63chg - Grup_Ort_SMA63)) + (0.75 × (SMA246chg - Grup_Ort_SMA246))
```

### Açıklama:
- **SMA63chg**: 63 günlük hareketli ortalama değişimi
- **SMA246chg**: 246 günlük hareketli ortalama değişimi
- **Grup_Ort_SMA63**: Grubunun 63 günlük ortalama değişimi
- **Grup_Ort_SMA246**: Grubunun 246 günlük ortalama değişimi

### Anlamı:
- **Pozitif GORT**: Hisse, grubundan daha iyi performans gösteriyor (trend yukarı)
- **Negatif GORT**: Hisse, grubundan daha kötü performans gösteriyor (trend aşağı)
- **0'a yakın**: Hisse, grubuyla aynı performansı gösteriyor

### Kullanım:
- **Long pozisyonlar için**: GORT > -1 (grup ortalamasından çok kötü değil)
- **Short pozisyonlar için**: GORT < 1 (grup ortalamasından çok iyi değil)

### Ağırlıklar:
- **%25 SMA63**: Kısa vadeli trend (daha az ağırlık)
- **%75 SMA246**: Uzun vadeli trend (daha fazla ağırlık)

---

## 7️⃣ GRPAN (Grouped Real Print Analyzer)

### Ne Yapar?
GRPAN, son 15 tick'teki **gerçek lot bazlı fiyat yoğunluğunu** analiz eder.

### Filtreleme:
- **9 lot ve altındaki print'ler IGNORE edilir** (gürültü)
- Sadece **10+ lot** print'ler analiz edilir

### Ağırlıklandırma:
- **100/200/300 lot**: Ağırlık = **1.00** (gerçek lot)
- **Diğer lotlar**: Ağırlık = **0.25** (daha az önemli)

### Hesaplama:
```
1. Son 15 tick alınır (9 lot altı filtrelendikten sonra)
2. Her tick için ağırlık belirlenir
3. Ağırlıklı MOD (en çok tekrar eden fiyat) bulunur
4. ±0.04 cent aralığındaki yoğunluk hesaplanır
```

### Çıktı:
- **GRPAN Fiyatı**: En yoğun fiyat aralığı
- **Concentration %**: Yoğunluk yüzdesi (≥50% = güvenilir)
- **Real Lot Count**: 100/200/300 lot sayısı

### Kullanım:
- **Qpcal hesaplamasında** kullanılır (LRPAN yerine)
- **Spread analizinde** kullanılır
- **Emir fiyatlandırmasında** referans olarak kullanılır

---

## 8️⃣ BGGG (Bugünün GRPAN Grup Analizi)

### Ne Yapar?
BGGG, **bugünün printlerinden** hesaplanan GRPAN'ı grup ortalamasıyla karşılaştırır.

### Hesaplama:
```
1. BGRPAN (Bugünün GRPAN):
   - Sadece bugünün printlerinden hesaplanır
   - Aynı GRPAN mantığı (9 lot altı ignore, ağırlıklandırma)

2. BGRPAN Sapması:
   bgrpan_sapma = BGRPAN - prev_close

3. Grup Ortalama BGRPAN Sapması:
   - Aynı gruptaki tüm hisseler için BGRPAN sapması hesaplanır
   - Ortalama alınır

4. BGGG AYRISMA:
   bggg_ayrisma = bgrpan_sapma - grup_ort_sapma
```

### Anlamı:
- **Pozitif BGGG AYRISMA**: Hisse, grubundan daha iyi performans gösteriyor (bugün)
- **Negatif BGGG AYRISMA**: Hisse, grubundan daha kötü performans gösteriyor (bugün)
- **0'a yakın**: Hisse, grubuyla aynı performansı gösteriyor

### Kullanım:
- **Günlük momentum** analizi
- **Grup içi göreceli performans** karşılaştırması
- **Kısa vadeli fırsat** tespiti

---

## 9️⃣ ETF CARDINAL (Otomatik Emir İptal Sistemi)

### Ne Yapar?
ETF Cardinal, belirli ETF'lerdeki **hızlı fiyat değişimlerini** izler ve otomatik olarak emirleri iptal eder.

### İzlenen ETF'ler:
- **PFF**: Preferred stock ETF
- **SPY**: S&P 500 ETF
- **KRE**: Regional bank ETF
- **IWM**: Small cap ETF
- **TLT**: Treasury bond ETF

### Çalışma Mantığı:
```
1. Her 1 dakikada ETF fiyatları çekilir
2. 2 dakika ve 5 dakika önceki fiyatlarla karşılaştırılır
3. Eşik değerleri kontrol edilir:
   - 2dk değişim ≥ threshold_2min → Tetikleme
   - 5dk değişim ≥ threshold_5min → Tetikleme
```

### Tetikleme Durumları:

**BEARISH (Ayı Piyasası):**
- ETF düşüşü eşiği aşarsa
- **Tüm BUY emirleri iptal edilir**

**BULLISH (Boğa Piyasası):**
- ETF yükselişi eşiği aşarsa
- **Tüm SELL emirleri iptal edilir**

### Eşik Tipleri:
- **Absolute**: Mutlak dolar değişimi (örn: -$0.50)
- **Percentage**: Yüzde değişimi (örn: -2%)

### Kullanım:
- **Risk yönetimi**: Hızlı piyasa hareketlerinde pozisyon koruması
- **Otomatik koruma**: Manuel müdahale gerektirmeden emir iptali
- **Piyasa durumu**: ETF'lerin genel piyasa yönünü gösterir

---

## 📋 ÖZET TABLO

| Metrik | Formül | Kullanım | İyi Değer |
|--------|--------|----------|-----------|
| **Bid Buy Ucuzluk** | `(bid + spread×0.15 - prev_close) - benchmark_chg` | Long alış fırsatı | Pozitif |
| **Ask Sell Pahalılık** | `(ask - spread×0.15 - prev_close) - benchmark_chg` | Long satış fırsatı | Pozitif |
| **Front Buy** | `(last + 0.01 - prev_close) - benchmark_chg` | Long alış fırsatı | Pozitif |
| **Front Sell** | `(last - 0.01 - prev_close) - benchmark_chg` | Long satış fırsatı | Pozitif |
| **Final BB** | `FINAL_THG - 800 × bid_buy_ucuzluk` | Long alış skoru | Yüksek |
| **Final FB** | `FINAL_THG - 800 × front_buy_ucuzluk` | Long alış skoru | Yüksek |
| **Final AS** | `FINAL_THG - 800 × ask_sell_pahalilik` | Long satış skoru | Yüksek |
| **Final FS** | `FINAL_THG - 800 × front_sell_pahalilik` | Long satış skoru | Yüksek |
| **Final SAS** | `SHORT_FINAL - 800 × ask_sell_pahalilik` | Short satış skoru | Yüksek |
| **Final SFS** | `SHORT_FINAL - 800 × front_sell_pahalilik` | Short satış skoru | Yüksek |
| **Fbtot** | `FBplagr + FBratgr` | Long toplam skor | Yüksek (en iyi) |
| **SFStot** | `SFSplagr + SFSRatgr` | Short toplam skor | Düşük (en iyi) |
| **GORT** | `0.25×(SMA63chg-ort) + 0.75×(SMA246chg-ort)` | Trend skoru | Long: > -1, Short: < 1 |
| **GRPAN** | Ağırlıklı lot bazlı fiyat yoğunluğu | Fiyat referansı | Concentration ≥ 50% |
| **BGGG AYRISMA** | `BGRPAN_sapma - grup_ort_sapma` | Günlük momentum | Pozitif (iyi) |
| **ETF Cardinal** | ETF değişim izleme | Risk yönetimi | Otomatik iptal |

---

## 🎯 KULLANIM ÖRNEKLERİ

### Long Pozisyon İçin:
1. **Fbtot YÜKSEK** → İyi Alış Fırsatı
2. **Fbtot DÜŞÜK** → Satış (Cover) Fırsatı
3. **GORT > -1** → Grup ortalamasından çok kötü değil

### Short Pozisyon İçin:
1. **SFStot DÜŞÜK** → İyi Short Fırsatı
2. **SFStot YÜKSEK** → Short Kapatma (Cover) Fırsatı
3. **GORT < 1** → Grup ortalamasından çok iyi değil

### Risk Yönetimi:
- **ETF Cardinal**: Piyasa hızlı düşerse BUY emirleri iptal
- **GRPAN**: Gerçek lot bazlı fiyat referansı
- **BGGG**: Günlük momentum takibi

---

## 📝 NOTLAR

1. **800 Katsayısı**: Ucuzluk/pahalılık skorlarının Final skorlara etkisini belirler
2. **Benchmark**: Genellikle ETF (PFF, SPY, vs.) değişimi kullanılır
3. **Grup Analizi**: Her hisse kendi grubuyla karşılaştırılır (heldff, heldkuponlu, vs.)
4. **Real Lot**: 100/200/300 lot print'ler daha önemlidir (ağırlık 1.00)
5. **9 Lot Filtresi**: Küçük print'ler gürültü olarak kabul edilir ve ignore edilir

---

**Son Güncelleme**: 2025-01-13








