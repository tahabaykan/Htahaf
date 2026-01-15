# QPCAL (Q Profit Calculator) - Detaylı Açıklama

Bu dokümantasyon, janall uygulamasındaki **Qpcal (Q Profit Calculator)** sisteminin ne yaptığını, nasıl çalıştığını ve nasıl kullanıldığını detaylı olarak açıklar.

---

## 🎯 QPCAL NEDİR?

**Qpcal = Q Profit Calculator (Q Kar Hesaplayıcı)**

Qpcal, bir hisse senedinin **GRPAN fiyatına** (gerçek piyasa fiyatı) göre, mevcut **bid/ask fiyatlarından** ne kadar uzakta olduğunu hesaplayan bir **profit skorlama sistemidir**. Bu sistem, **hangi hisselerde işlem yapmanın daha karlı olacağını** belirlemek için kullanılır.

### Temel Mantık

Qpcal şu soruyu cevaplar:
> **"GRPAN fiyatı (gerçek piyasa fiyatı) ile mevcut bid/ask fiyatları arasında ne kadar fark var? Bu fark, işlem yapmak için yeterince büyük mü?"**

**Neden önemli?**
- GRPAN, gerçek işlemlerden hesaplanan **en güvenilir fiyat referansıdır**
- Bid/Ask, piyasa yapıcıların (market makers) teklif ettiği fiyatlardır
- Bu ikisi arasındaki fark ne kadar büyükse, **işlem yapmak için o kadar iyi bir fırsat** vardır

---

## 📊 QPCAL NASIL HESAPLANIR?

### Adım 1: GRPAN Fiyatını Al

**GRPAN (Grouped Real Print Analyzer)** nedir?
- Son 15 gerçek işlemden (trade print) hesaplanan **en sık görülen fiyat** (modal price)
- **9 lot ve altındaki işlemler ignore edilir** (gürültü olarak kabul edilir)
- **Ağırlıklandırma**:
  - **100, 200, 300 lot işlemler**: Ağırlık = 1.0 (tam ağırlık)
  - **Diğer işlemler**: Ağırlık = 0.25 (çeyrek ağırlık)
- En yüksek ağırlığa sahip fiyat = **GRPAN fiyatı**

**Örnek:**
- Son 15 işlem: $20.50 (100 lot), $20.51 (50 lot), $20.50 (200 lot), $20.52 (30 lot), $20.50 (300 lot)
- Ağırlıklar: $20.50 = 1.0 + 1.0 + 1.0 = 3.0, $20.51 = 0.25, $20.52 = 0.25
- **GRPAN = $20.50** (en yüksek ağırlık)

### Adım 2: Bid ve Ask Fiyatlarını Al

- **Bid**: Alıcının teklif ettiği en yüksek fiyat (alış fiyatı)
- **Ask**: Satıcının teklif ettiği en düşük fiyat (satış fiyatı)

**Örnek:**
- Bid = $20.45
- Ask = $20.55

### Adım 3: Uzaklıkları Hesapla

**Bid Uzaklığı:**
```
bid_distance = |GRPAN - Bid|
```

**Ask Uzaklığı:**
```
ask_distance = |GRPAN - Ask|
```

**Örnek:**
- GRPAN = $20.50
- Bid = $20.45
- Ask = $20.55
- **bid_distance = |20.50 - 20.45| = $0.05**
- **ask_distance = |20.50 - 20.55| = $0.05**

### Adım 4: Qpcal Değerini Belirle

**Qpcal değeri**, bid ve ask uzaklıklarından **en büyük olanıdır**:

```
if bid_distance > ask_distance:
    qpcal_value = bid_distance
    direction = 'Long'  # Bid'den alış yapmak daha karlı
else:
    qpcal_value = ask_distance
    direction = 'Short'  # Ask'ten satış yapmak daha karlı
```

**Örnek:**
- bid_distance = $0.05
- ask_distance = $0.15
- **qpcal_value = $0.15** (ask_distance daha büyük)
- **direction = 'Short'** (Ask'ten satış yapmak daha karlı)

### Adım 5: "Both" Kontrolü

**Both (Her İkisi) Flag:**
- Eğer hem bid_distance hem de ask_distance **$0.20'den büyükse**, `both_flag = True`
- Bu, **hem alış hem satış için iyi bir fırsat** olduğunu gösterir

**Örnek:**
- bid_distance = $0.25
- ask_distance = $0.30
- **both_flag = True** (her ikisi de $0.20'den büyük)

---

## 📈 QPCAL DEĞERİNİN ANLAMI

### Qpcal Değeri Ne Kadar Olmalı?

**Yüksek Qpcal Değeri = İyi Fırsat**

- **Qpcal ≥ $0.30**: **Çok iyi fırsat** (yüksek profit potansiyeli)
- **Qpcal ≥ $0.15**: **İyi fırsat** (orta profit potansiyeli)
- **Qpcal < $0.15**: **Zayıf fırsat** (düşük profit potansiyeli)

**Neden?**
- Yüksek Qpcal = GRPAN ile bid/ask arasında büyük fark var
- Bu, piyasanın **"yanlış fiyatlandırılmış"** olduğunu gösterir
- Bu fırsatı yakalarsanız, **daha iyi bir fiyattan işlem yapabilirsiniz**

### Direction (Yön) Ne Anlama Geliyor?

**Long (Alış Yönü):**
- `bid_distance > ask_distance`
- **Anlamı**: GRPAN fiyatı, bid fiyatından daha uzakta (ask fiyatına daha yakın)
- **Strateji**: Bid'den alış yapmak daha karlı (çünkü GRPAN daha yüksek, fiyat yükselme potansiyeli var)

**Short (Satış Yönü):**
- `ask_distance > bid_distance`
- **Anlamı**: GRPAN fiyatı, ask fiyatından daha uzakta (bid fiyatına daha yakın)
- **Strateji**: Ask'ten satış yapmak daha karlı (çünkü GRPAN daha düşük, fiyat düşme potansiyeli var)

**Both (Her İkisi):**
- Hem bid hem ask uzaklığı > $0.20
- **Anlamı**: Hem alış hem satış için iyi fırsat var
- **Strateji**: Hem bid'den alış hem ask'ten satış yapılabilir (iki yönlü işlem)

---

## 🎯 QPCAL KULLANIM SENARYOLARI

### Senaryo 1: Spreadkusu Panel'de Qpcal

**Ne zaman kullanılır?**
- Spreadkusu tablosundaki tüm hisseler için Qpcal analizi yapmak istediğinizde
- **Hangi hisselerde işlem yapmanın daha karlı olduğunu** görmek için

**Nasıl çalışır?**
1. Spreadkusu panelinde **"Qpcal" butonuna** tıklarsınız
2. Sistem, tablodaki tüm hisseler için:
   - GRPAN fiyatını alır
   - Bid/Ask fiyatlarını alır
   - Qpcal değerini hesaplar
   - Direction (Long/Short) belirler
   - Both flag'ini kontrol eder
3. Sonuçlar bir tabloda gösterilir, **Qpcal değerine göre büyükten küçüğe sıralanır**
4. En yüksek skorlu **80 hisse** gösterilir
5. İstediğiniz hisseleri seçip **"Runqp" butonuna** basarak emir gönderebilirsiniz

### Senaryo 2: Take Profit Panel'de Qpcal

**Ne zaman kullanılır?**
- Mevcut pozisyonlarınız (long veya short) için **kar alma fırsatlarını** görmek istediğinizde
- **Hangi pozisyonları kapatmak daha karlı** olduğunu görmek için

**Nasıl çalışır?**
1. Take Profit panelinde pozisyonları seçersiniz
2. **"Qpcal" butonuna** tıklarsınız
3. Sistem, seçili pozisyonlar için Qpcal analizi yapar
4. Sonuçlar gösterilir, **en karlı pozisyonlar** üstte görünür

### Senaryo 3: RUNALL Algoritmasında Qpcal

**Ne zaman kullanılır?**
- RUNALL algoritması çalıştığında, **otomatik olarak** Qpcal analizi yapılır
- ADDNEWPOS emirleri gönderildikten sonra, Qpcal işlemi başlatılır

**Nasıl çalışır?**
1. RUNALL algoritması, ADDNEWPOS emirlerini gönderir
2. Sonra **otomatik olarak** Qpcal penceresi açılır
3. Qpcal analizi yapılır ve sonuçlar gösterilir
4. **Otomatik olarak** "Runqp" butonuna basılır (RUNALL modunda)
5. Seçili hisseler için emirler gönderilir
6. Emirler gönderildikten sonra, **2 dakika sayacı** başlatılır

---

## 🚀 RUNQP (Run Qpcal Orders) - Emir Gönderme

### Runqp Ne Yapar?

**Runqp (Run Qpcal Orders)**, Qpcal tablosunda seçili hisseler için **otomatik emir gönderme** işlemidir.

### Emir Gönderme Mantığı

#### 1. Lot Hesaplama

Her hisse için lot miktarı şöyle hesaplanır:
```
lot = MAXALW / 4
lot = round(lot / 100) * 100  # Yüzlere yuvarla
if lot < 200:
    lot = 200  # Minimum 200 lot
```

**Açıklama:**
- **MAXALW**: CSV'den gelen, o hisse için maksimum alınabilir lot miktarı
- **MAXALW / 4**: Maksimum lot'un dörtte biri (risk yönetimi için)
- **Yüzlere yuvarlama**: Lot miktarı 100'ün katı olmalı (örneğin: 200, 300, 400)
- **Minimum 200 lot**: Çok küçük emirler gönderilmez

**Örnek:**
- MAXALW = 1000 lot
- lot = 1000 / 4 = 250
- lot = round(250 / 100) * 100 = 200 lot (yüzlere yuvarlanmış)

#### 2. Emir Fiyatı Hesaplama

**Bid Buy (Alış Emri) için:**
```
bid_buy_price = bid + (spread × 0.15)
```

**Ask Sell (Satış Emri) için:**
```
ask_sell_price = ask - (spread × 0.15)
```

**Açıklama:**
- **Spread**: Ask - Bid (fiyat farkı)
- **%15 spread**: Emir fiyatı, bid/ask'ten spread'in %15'i kadar uzakta olur
- Bu, **"passive" (pasif) emir** stratejisidir - piyasa yapıcıların fiyatını kabul etmek yerine, biraz daha iyi bir fiyat teklif edersiniz

**Örnek:**
- Bid = $20.45
- Ask = $20.55
- Spread = $20.55 - $20.45 = $0.10
- **bid_buy_price = $20.45 + ($0.10 × 0.15) = $20.45 + $0.015 = $20.465**
- **ask_sell_price = $20.55 - ($0.10 × 0.15) = $20.55 - $0.015 = $20.535**

#### 3. Emir Türü ve Yönü

**Long (Alış Yönü) için:**
- **Emir Türü**: BUY (Alış)
- **Fiyat**: bid_buy_price
- **Lot**: MAXALW / 4 (yüzlere yuvarlanmış, minimum 200)

**Short (Satış Yönü) için:**
- **Emir Türü**: SELL (Satış)
- **Fiyat**: ask_sell_price
- **Lot**: MAXALW / 4 (yüzlere yuvarlanmış, minimum 200)

**Both (Her İkisi) için:**
- **İki emir gönderilir**:
  1. BUY emri: bid_buy_price
  2. SELL emri: ask_sell_price
- Her ikisi de aynı lot miktarıyla (MAXALW / 4)

#### 4. Emir Özellikleri

- **Order Type**: LIMIT (limit emir - belirli bir fiyattan)
- **Hidden**: True (gizli emir - piyasada görünmez)
- **Symbol Conversion**: 
  - Hammer modunda: "PR" → "-" (örneğin: "NSA PRA" → "NSA-A")
  - IBKR modunda: Symbol olduğu gibi kalır

---

## 📋 QPCAL TABLOSU KOLONLARI

Qpcal penceresinde gösterilen kolonlar:

1. **Select (✓)**: Hisseleri seçmek için checkbox
2. **Symbol**: Hisse senedi sembolü
3. **GRPAN**: GRPAN fiyatı (gerçek piyasa fiyatı)
4. **GRConf (GR%)**: GRPAN konsantrasyon yüzdesi (≥50% = güvenilir)
5. **RealLot**: 100/200/300 lot sayısı (gerçek lot)
6. **Bid**: Alış fiyatı
7. **Ask**: Satış fiyatı
8. **Qpcal**: Qpcal değeri ve yön (örneğin: "0.25 Long")
9. **Direction**: Long veya Short
10. **Both**: Hem bid hem ask uzaklığı > $0.20 ise ✓
11. **MAXALW**: Maksimum alınabilir lot miktarı (CSV'den)

---

## 🎨 RENK KODLARI

Qpcal tablosunda, hisseler **Qpcal değerine göre** renklendirilir:

- **Yeşil (Lime)**: Qpcal ≥ $0.30 (çok iyi fırsat)
- **Açık Yeşil**: Qpcal ≥ $0.15 (iyi fırsat)
- **Açık Sarı**: Qpcal < $0.15 (zayıf fırsat)
- **Gri**: Qpcal hesaplanamadı (veri yok)

Ayrıca, **Direction'a göre** arka plan rengi:
- **Mavi**: Long (alış yönü)
- **Açık Kırmızı**: Short (satış yönü)

---

## 🔄 QPCAL İŞLEM AKIŞI

### Manuel Kullanım (Spreadkusu Panel)

1. **Spreadkusu panelini açın**
2. **"Qpcal" butonuna tıklayın**
3. **Qpcal penceresi açılır** ve analiz başlar
4. **Sonuçlar tabloda gösterilir** (Qpcal değerine göre sıralı)
5. **İstediğiniz hisseleri seçin** (checkbox ile)
6. **"Runqp" butonuna tıklayın**
7. **Onay mesajı** görünür (kaç hisse için emir gönderileceği)
8. **Onayladıktan sonra**, emirler gönderilir
9. **Sonuç mesajı** görünür (kaç emir başarılı, kaç emir hatalı)

### Otomatik Kullanım (RUNALL Algoritması)

1. **RUNALL algoritması çalışır**
2. **ADDNEWPOS emirleri gönderilir**
3. **Otomatik olarak Qpcal penceresi açılır**
4. **Qpcal analizi yapılır**
5. **Otomatik olarak "Runqp" butonuna basılır** (onay mesajı yok)
6. **Emirler gönderilir**
7. **2 dakika sayacı başlatılır** (emirlerin iptal edilmesi için)

---

## 💡 QPCAL ÖRNEKLERİ

### Örnek 1: Long Fırsatı

**Veriler:**
- GRPAN = $20.50
- Bid = $20.30
- Ask = $20.55

**Hesaplama:**
- bid_distance = |20.50 - 20.30| = $0.20
- ask_distance = |20.50 - 20.55| = $0.05
- **qpcal_value = $0.20** (bid_distance daha büyük)
- **direction = 'Long'**
- both_flag = False (ask_distance < $0.20)

**Yorum:**
- GRPAN fiyatı ($20.50), bid fiyatından ($20.30) $0.20 uzakta
- Bu, **bid'den alış yapmak için iyi bir fırsat** olduğunu gösterir
- Fiyat, GRPAN seviyesine ($20.50) yükselme potansiyeli var

**Strateji:**
- Bid Buy emri gönderilir: `bid + (spread × 0.15)`
- Lot: MAXALW / 4

### Örnek 2: Short Fırsatı

**Veriler:**
- GRPAN = $20.50
- Bid = $20.45
- Ask = $20.70

**Hesaplama:**
- bid_distance = |20.50 - 20.45| = $0.05
- ask_distance = |20.50 - 20.70| = $0.20
- **qpcal_value = $0.20** (ask_distance daha büyük)
- **direction = 'Short'**
- both_flag = False (bid_distance < $0.20)

**Yorum:**
- GRPAN fiyatı ($20.50), ask fiyatından ($20.70) $0.20 uzakta
- Bu, **ask'ten satış yapmak için iyi bir fırsat** olduğunu gösterir
- Fiyat, GRPAN seviyesine ($20.50) düşme potansiyeli var

**Strateji:**
- Ask Sell emri gönderilir: `ask - (spread × 0.15)`
- Lot: MAXALW / 4

### Örnek 3: Both Fırsatı (Her İkisi)

**Veriler:**
- GRPAN = $20.50
- Bid = $20.25
- Ask = $20.75

**Hesaplama:**
- bid_distance = |20.50 - 20.25| = $0.25
- ask_distance = |20.50 - 20.75| = $0.25
- **qpcal_value = $0.25** (ikisi de aynı, herhangi biri seçilir)
- **direction = 'Long'** (veya 'Short', eşitse bid_distance seçilir)
- **both_flag = True** (her ikisi de > $0.20)

**Yorum:**
- Hem bid hem ask, GRPAN fiyatından $0.25 uzakta
- Bu, **hem alış hem satış için çok iyi bir fırsat** olduğunu gösterir
- İki yönlü işlem yapılabilir

**Strateji:**
- **İki emir gönderilir**:
  1. Bid Buy emri: `bid + (spread × 0.15)`
  2. Ask Sell emri: `ask - (spread × 0.15)`
- Her ikisi de aynı lot miktarıyla (MAXALW / 4)

---

## ⚠️ ÖNEMLİ NOTLAR

### 1. GRPAN Güvenilirliği

- **GRPAN konsantrasyon yüzdesi ≥ 50%**: Güvenilir (yüksek güven)
- **GRPAN konsantrasyon yüzdesi < 50%**: Düşük güvenilirlik (GRPAN fiyatının yanında "?" işareti görünür)
- **GRPAN yoksa**: Qpcal hesaplanamaz (N/A gösterilir)

### 2. MAXALW Kontrolü

- **MAXALW > 0**: Emir gönderilebilir
- **MAXALW = 0 veya N/A**: Emir gönderilmez (atlanır)

### 3. Bid/Ask Verisi

- **Bid/Ask yoksa**: Qpcal hesaplanamaz (N/A gösterilir)
- **Bid/Ask = 0**: Qpcal hesaplanamaz

### 4. Lot Hesaplama

- **Minimum lot**: 200 lot (MAXALW / 4 < 200 ise, 200 lot kullanılır)
- **Yüzlere yuvarlama**: Lot miktarı her zaman 100'ün katıdır (200, 300, 400, vs.)

### 5. Emir Fiyatlandırması

- **Passive strateji**: Emir fiyatı, bid/ask'ten spread'in %15'i kadar uzakta
- Bu, **piyasa yapıcıların fiyatını kabul etmek yerine**, biraz daha iyi bir fiyat teklif etmek anlamına gelir
- **Hidden emir**: Emirler piyasada görünmez (gizli)

---

## 🎯 QPCAL KULLANIM STRATEJİLERİ

### Strateji 1: Yüksek Qpcal Değerli Hisseleri Seç

- **Qpcal ≥ $0.30**: En iyi fırsatlar (öncelik verin)
- **Qpcal ≥ $0.15**: İyi fırsatlar (ikinci öncelik)
- **Qpcal < $0.15**: Zayıf fırsatlar (dikkatli olun)

### Strateji 2: Both Flag'li Hisseleri Tercih Et

- **Both = ✓**: Hem alış hem satış için iyi fırsat
- İki yönlü işlem yapılabilir (daha fazla profit potansiyeli)

### Strateji 3: GRPAN Güvenilirliğini Kontrol Et

- **GRConf ≥ 50%**: Güvenilir (tercih edin)
- **GRConf < 50%**: Düşük güvenilirlik (dikkatli olun, "?" işareti var)

### Strateji 4: MAXALW Kontrolü

- **MAXALW > 0**: Emir gönderilebilir
- **MAXALW = 0**: Emir gönderilmez (atlanır)

### Strateji 5: Direction'a Göre Karar Ver

- **Long**: Bid'den alış yapmak daha karlı (fiyat yükselme potansiyeli)
- **Short**: Ask'ten satış yapmak daha karlı (fiyat düşme potansiyeli)

---

## 📚 TERİMLER SÖZLÜĞÜ

- **Qpcal**: Q Profit Calculator (Q Kar Hesaplayıcı)
- **GRPAN**: Grouped Real Print Analyzer (Gruplandırılmış Gerçek İşlem Analizörü)
- **LRPAN**: Last Real Print Analyzer (Son Gerçek İşlem Analizörü) - Eski versiyon, artık GRPAN kullanılıyor
- **Bid**: Alıcının teklif ettiği en yüksek fiyat
- **Ask**: Satıcının teklif ettiği en düşük fiyat
- **Spread**: Ask - Bid (fiyat farkı)
- **Direction**: Long (alış yönü) veya Short (satış yönü)
- **Both**: Hem bid hem ask uzaklığı > $0.20 (iki yönlü fırsat)
- **MAXALW**: Maksimum Alınabilir Lot (CSV'den gelen, o hisse için maksimum lot miktarı)
- **Runqp**: Run Qpcal Orders (Qpcal emirlerini çalıştır)
- **Passive Fiyat**: Bid/Ask'ten spread'in %15'i kadar uzakta olan emir fiyatı
- **Hidden Emir**: Piyasada görünmeyen, gizli emir

---

## 🔄 QPCAL vs LRPAN

**Eski Sistem (LRPAN):**
- LRPAN = Last Real Print Analyzer
- Son işlem fiyatını kullanırdı
- Daha az güvenilir (tek bir işlem fiyatı)

**Yeni Sistem (GRPAN):**
- GRPAN = Grouped Real Print Analyzer
- Son 15 işlemden hesaplanan modal fiyatı kullanır
- Daha güvenilir (çoklu işlem analizi)
- Ağırlıklandırma ile daha doğru sonuç

**Not:** Artık Qpcal hesaplamasında **GRPAN kullanılıyor**, LRPAN kullanılmıyor.

---

## 🎯 ÖZET

**Qpcal ne yapar?**
1. GRPAN fiyatını (gerçek piyasa fiyatı) alır
2. Bid/Ask fiyatlarını alır
3. GRPAN ile bid/ask arasındaki uzaklığı hesaplar
4. En büyük uzaklığı bulur (Qpcal değeri)
5. Yönü belirler (Long veya Short)
6. Both flag'ini kontrol eder
7. Sonuçları sıralar ve gösterir
8. Seçili hisseler için emir gönderir (Runqp)

**Neden önemli?**
- **Profit skorlama**: Hangi hisselerde işlem yapmanın daha karlı olduğunu gösterir
- **Otomatik emir gönderme**: Runqp ile seçili hisseler için otomatik emir gönderilir
- **Risk yönetimi**: MAXALW kontrolü ile lot miktarı sınırlandırılır
- **Passive strateji**: Spread'in %15'i kadar uzakta emir gönderilir (daha iyi fiyat)

---

*Bu dokümantasyon, janall uygulamasının mevcut durumunu yansıtmaktadır ve güncellemeler yapıldıkça revize edilecektir.*


