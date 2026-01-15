# Decision Helper Metrikleri - Detaylı Açıklama

## 🎯 Decision Helper Ne Yapıyor?

Decision Helper, tick-by-tick (her işlem) verilerini analiz ederek piyasanın **anlık durumunu** sınıflandırır. Amacı:
- Hangi yönde baskı var? (Alıcı mı, satıcı mı?)
- Bu baskı ne kadar güçlü?
- Fiyat hareketi ne kadar verimli?
- Piyasa durumu nedir? (BUYER_DOMINANT, SELLER_DOMINANT, NEUTRAL, vb.)

---

## 📊 Metriklerin Detaylı Açıklaması

### 1. **PRICE DISPLACEMENT (Fiyat Sapması)**

**Formül:**
```
Price Displacement = Son Fiyat - İlk Fiyat
```

**Nasıl Hesaplanıyor:**
1. Seçilen zaman penceresi içindeki (örn: 15 dakika) tüm tick'ler alınır
2. Tick'ler zamana göre sıralanır
3. **İlk tick'in fiyatı** (pencerenin başındaki fiyat)
4. **Son tick'in fiyatı** (pencerenin sonundaki fiyat)
5. Fark hesaplanır: `last_price - first_price`

**Ne Anlama Geliyor:**
- **Pozitif Değer (+0.210)**: Fiyat **YUKARI** hareket etmiş
  - Örnek: WRB PRE için +0.210 = 15 dakikada 21 cent yukarı gitmiş
- **Negatif Değer (-0.150)**: Fiyat **AŞAĞI** hareket etmiş
  - Örnek: -0.150 = 15 dakikada 15 cent aşağı gitmiş

**⚠️ ÖNEMLİ:**
- Displacement **SADECE fiyat hareketini** gösterir
- **Hangi yönde baskı olduğunu göstermez!**
- Örnek: Fiyat yukarı gidebilir ama satıcı baskısı olabilir (kısa vadeli)

**WRB PRE Örneği:**
- Displacement: +0.210 (21 cent yukarı)
- Bu, fiyatın **yukarı hareket ettiğini** gösterir
- Ama bu **"en çok satan"** demek değil!

---

### 2. **NET PRESSURE (Net Baskı)**

**Formül:**
```
Net Pressure = Σ(Aggressor × Trade Size) / Toplam Volume
```

**Nasıl Hesaplanıyor:**
Her tick için:
1. **Aggressor (Saldırgan) Belirleme:**
   - Eğer `trade_price >= ask_price` → **+1** (Alıcı saldırgan - ask'i yedi)
   - Eğer `trade_price <= bid_price` → **-1** (Satıcı saldırgan - bid'i yedi)
   - Eğer `bid < trade_price < ask` → **0** (Mid-spread, nötr)

2. **Ağırlıklı Toplam:**
   - Her tick için: `aggressor × trade_size`
   - Tüm tick'lerin toplamı: `Σ(aggressor × size)`

3. **Normalizasyon:**
   - `net_pressure = toplam / window_volume`

**Ne Anlama Geliyor:**
- **Pozitif Değer (+0.116)**: **ALICI BASKISI** var
  - Alıcılar ask fiyatını yiyor, fiyatı yukarı itiyor
  - Örnek: PSA PRP için +0.116 = %11.6 net alıcı baskısı
- **Negatif Değer (-0.708)**: **SATICI BASKISI** var
  - Satıcılar bid fiyatını yiyor, fiyatı aşağı itiyor
  - Örnek: WRB PRG için -0.708 = %70.8 net satıcı baskısı (çok güçlü!)

**⚠️ ÖNEMLİ:**
- **Net Pressure = Gerçek Baskı Yönü**
- Displacement'ten daha önemli!
- WRB PRE için +0.009 = Çok hafif alıcı baskısı (neredeyse nötr)

**WRB PRE Örneği:**
- Net Pressure: +0.009 (çok hafif alıcı baskısı)
- Bu, **"en çok satan"** değil, **neredeyse nötr** demek!

---

### 3. **ADV FRACTION (Günlük Ortalama Hacim Oranı)**

**Formül:**
```
ADV Fraction = (Pencere İçindeki Toplam Volume) / AVG_ADV
```

**Nasıl Hesaplanıyor:**
1. 15 dakika içindeki tüm tick'lerin volume'u toplanır
2. Symbol'ün AVG_ADV (Average Daily Volume) değerine bölünür
3. Yüzde olarak gösterilir

**Ne Anlama Geliyor:**
- **100%+ (153.0%)**: Normalden **FAZLA** işlem hacmi
  - Örnek: KIM PRL için 153% = Günlük ortalamanın 1.5 katı işlem var
  - Yüksek ilgi/aktivite gösterir
- **100%- (95.2%)**: Normalden **AZ** işlem hacmi
  - Örnek: WRB PRE için 95.2% = Normal seviyede

**⚠️ ÖNEMLİ:**
- Yüksek ADV Fraction = Yüksek ilgi/aktivite
- Düşük ADV Fraction = Düşük ilgi/aktivite

---

### 4. **EFFICIENCY (Verimlilik)**

**Formül:**
```
Efficiency = |Price Displacement| / ADV_Fraction
```

**Nasıl Hesaplanıyor:**
1. Displacement'in mutlak değeri alınır
2. ADV Fraction'a bölünür

**Ne Anlama Geliyor:**
- **Yüksek Değer (0.47)**: Fiyat **VERİMLİ** hareket etmiş
  - Az volume ile çok fiyat hareketi
  - Net, temiz, yönlü hareket
- **Düşük Değer (0.11)**: Fiyat **VERİMSİZ** hareket etmiş
  - Çok volume ile az fiyat hareketi
  - Choppy, karışık, yön belirsiz

**⚠️ ÖNEMLİ:**
- Efficiency = Hareket kalitesi
- Yüksek efficiency = Temiz trend
- Düşük efficiency = Choppy/karışık piyasa

---

### 5. **TRADE FREQUENCY (İşlem Sıklığı)**

**Formül:**
```
Trade Frequency = Tick Sayısı / Pencere Süresi (dakika)
```

**Nasıl Hesaplanıyor:**
1. Pencere içindeki toplam tick sayısı
2. Pencere süresine (örn: 15 dakika) bölünür

**Ne Anlama Geliyor:**
- **Yüksek Değer (6.7)**: Saniyede/dakikada **ÇOK** işlem
  - Yüksek likidite, aktif piyasa
- **Düşük Değer (2.1)**: Saniyede/dakikada **AZ** işlem
  - Düşük likidite, pasif piyasa

---

## 🎯 STATE CLASSIFICATION (Durum Sınıflandırması)

Decision Helper, yukarıdaki metrikleri kullanarak piyasayı **5 duruma** sınıflandırır:

### 1. **BUYER_DOMINANT (Alıcı Baskın)**
**Koşullar:**
- Displacement > +0.05¢ (yukarı hareket)
- Net Pressure > +0.1 (alıcı baskısı)
- ADV Fraction > 5% (yeterli volume)

**Anlamı:** Alıcılar aktif, fiyatı yukarı itiyor, güçlü yükseliş trendi

---

### 2. **SELLER_DOMINANT (Satıcı Baskın)**
**Koşullar:**
- Displacement < -0.05¢ (aşağı hareket)
- Net Pressure < -0.1 (satıcı baskısı)
- ADV Fraction > 5% (yeterli volume)

**Anlamı:** Satıcılar aktif, fiyatı aşağı itiyor, güçlü düşüş trendi

---

### 3. **SELLER_VACUUM (Satıcı Boşluğu)**
**Koşullar:**
- Displacement < -0.05¢ (aşağı hareket)
- ADV Fraction < 2.5% (düşük volume)

**Anlamı:** Fiyat düşüyor ama volume düşük - satıcılar tükendi, potansiyel bounce

---

### 4. **ABSORPTION (Emilim)**
**Koşullar:**
- |Displacement| < 0.025¢ (küçük fiyat hareketi)
- ADV Fraction > 5% (yüksek volume)
- Efficiency < 1.0 (düşük verimlilik)

**Anlamı:** Yüksek volume var ama fiyat hareket etmiyor - likidite emiliyor, potansiyel breakout

---

### 5. **NEUTRAL (Nötr)**
**Koşullar:**
- Yukarıdaki durumlardan hiçbiri değil

**Anlamı:** Belirsiz, karışık, yön yok

---

## 🔍 WRB PRE Örneği - Detaylı Analiz

**Görünen Değerler:**
- Displacement: **+0.210** (21 cent yukarı)
- Net Pressure: **+0.009** (çok hafif alıcı baskısı)
- ADV Fraction: **95.2%** (normal volume)
- State: **NEUTRAL** (50% confidence)

**Analiz:**
1. **Displacement +0.210:**
   - Fiyat 15 dakikada **21 cent yukarı** gitmiş
   - Bu **yukarı hareket** gösterir

2. **Net Pressure +0.009:**
   - **Çok hafif alıcı baskısı** var (neredeyse 0)
   - **"En çok satan" değil!**
   - Eğer "en çok satan" olsaydı, Net Pressure **-0.5 veya daha negatif** olurdu

3. **State: NEUTRAL:**
   - Displacement yüksek ama Net Pressure çok düşük
   - Bu yüzden NEUTRAL sınıflandırılmış
   - Güçlü bir yön yok

**Sonuç:**
- WRB PRE **"en çok satan" değil**
- Fiyat yukarı gitmiş ama baskı çok hafif
- NEUTRAL durumda

**Gerçek "En Çok Satan" Örneği:**
- WRB PRG: Net Pressure **-0.708** (güçlü satıcı baskısı)
- Bu, gerçek satıcı baskısını gösterir

---

## 📝 Özet - Hangi Metriğe Bakmalı?

### "En Çok Satan" Bulmak İçin:
1. **NET PRESSURE** → En önemli! Negatif değerler aranmalı
2. **STATE** → SELLER_DOMINANT veya SELLER_VACUUM olmalı
3. **DISPLACEMENT** → İkincil öncelik (negatif olabilir ama zorunlu değil)

### "En Çok Alan" Bulmak İçin:
1. **NET PRESSURE** → Pozitif değerler aranmalı
2. **STATE** → BUYER_DOMINANT olmalı
3. **DISPLACEMENT** → İkincil öncelik (pozitif olmalı)

### "En İyi Hareket" Bulmak İçin:
1. **EFFICIENCY** → Yüksek değerler
2. **DISPLACEMENT** → Büyük mutlak değer
3. **NET PRESSURE** → Güçlü yön (pozitif veya negatif)

---

## ⚠️ ÖNEMLİ NOTLAR

1. **Displacement ≠ Baskı Yönü**
   - Displacement sadece fiyat hareketini gösterir
   - Net Pressure gerçek baskı yönünü gösterir

2. **State Classification Karmaşık**
   - Birden fazla metrik birlikte değerlendirilir
   - Yüksek displacement tek başına yeterli değil

3. **Zaman Penceresi Önemli**
   - 15 dakika = Kısa vadeli trend
   - 30 dakika = Orta vadeli trend
   - Farklı pencereler farklı sonuçlar verebilir

4. **Group Normalization**
   - Symbol'ler grup içinde normalize edilir
   - Grup ortalamasına göre değerlendirilir
   - Bu, daha doğru karşılaştırma sağlar

---

## 🎯 Sonuç

**WRB PRE "en çok satan" değil!**
- Net Pressure: +0.009 (hafif alıcı baskısı)
- Displacement: +0.210 (yukarı hareket)
- State: NEUTRAL (belirsiz)

**Gerçek satıcı baskısı için:**
- Net Pressure negatif olmalı (-0.5 veya daha negatif)
- State SELLER_DOMINANT olmalı
- Displacement genelde negatif olur (ama zorunlu değil)


