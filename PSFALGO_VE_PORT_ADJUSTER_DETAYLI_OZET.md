# PSFALGO ve Port Adjuster - Kapsamlı Detaylı Özet

## 📋 İÇİNDEKİLER

1. [PSFALGO Nedir?](#1-psfalgo-nedir)
2. [Janall İçindeki PSFALGO Sistemi](#2-janall-içindeki-psfalgo-sistemi)
3. [Port Adjuster Nedir?](#3-port-adjuster-nedir)
4. [RUNALL Mod](#4-runall-mod)
5. [ALLOWED Mod](#5-allowed-mod)
6. [KARBOTU](#6-karbotu)
7. [REDUCEMORE](#7-reducemore)
8. [ADDNEWPOS](#8-addnewpos)
9. [Croplit6 ve Croplit9](#9-croplit6-ve-croplit9)
10. [Kurallar Sistemi](#10-kurallar-sistemi)
11. [Fbtot, GORT, SMA63CHG ve Diğer Metrikler](#11-fbtot-gort-sma63chg-ve-diğer-metrikler)

---

## 1. PSFALGO NEDİR?

**PSFALGO**, Janall uygulamasının kalbi olan **otomatik trading sistemi**dir. "PSF" muhtemelen "Preferred Stock Follower" veya benzer bir kısaltmadır, "ALGO" ise "Algorithm" anlamına gelir.

### 1.1. PSFALGO'nun Amacı

PSFALGO, **7/24 çalışabilen, risk kontrollü, kar garantili bir otomatik trading sistemi** olarak tasarlanmıştır. Sistemin temel amacı:

- **Otomatik pozisyon yönetimi**: Mevcut pozisyonları analiz edip, kar realizasyonu veya risk azaltma işlemleri yapmak
- **Yeni pozisyon açma**: Uygun fırsatları tespit edip yeni pozisyonlar açmak
- **Risk kontrolü**: Çoklu limit kontrolleri ile riski minimize etmek
- **Kar garantisi**: Reverse order sistemi ile minimum kar garantisi sağlamak

### 1.2. PSFALGO'nun Temel Bileşenleri

1. **Ana Otomasyon Motoru**: Tüm işlemleri koordine eden merkezi sistem
2. **PISDoNGU Sistemi**: 3 dakikalık döngüsel işlem zinciri (ileride detaylı açıklanacak)
3. **Fill Listener**: Gerçek zamanlı fill (emir gerçekleşme) tespit sistemi
4. **Reverse Order Sistemi**: Otomatik kar garantisi emirleri
5. **Position Control**: Pozisyon yönetimi ve limit kontrolü

---

## 2. JANALL İÇİNDEKİ PSFALGO SİSTEMİ

Janall uygulamasında PSFALGO, **manuel ve otomatik modlarda** çalışabilen bir sistemdir. Sistem şu ana modüllere sahiptir:

### 2.1. PSFALGO Modülleri

#### A) **KARBOTU** (Pozisyon Azaltma - Agresif)
- **Amaç**: Long pozisyonları kar realizasyonu için azaltmak
- **Çalışma Şekli**: 13 adımlı otomasyon süreci
- **Kullanım**: OFANSIF modda kullanılır

#### B) **REDUCEMORE** (Pozisyon Azaltma - Konservatif)
- **Amaç**: Long ve Short pozisyonları risk azaltma için azaltmak
- **Çalışma Şekli**: 13 adımlı otomasyon süreci (KARBOTU'dan daha konservatif)
- **Kullanım**: DEFANSIF veya GEÇİŞ modunda kullanılır

#### C) **ADDNEWPOS** (Pozisyon Artırma)
- **Amaç**: Mevcut pozisyonlara ekleme yapmak veya yeni pozisyonlar açmak
- **Çalışma Şekli**: Port Adjuster ile entegre çalışır
- **Kullanım**: Exposure limitleri içinde yeni pozisyonlar açmak

#### D) **CROPLIT** (Spread Bazlı Kar Realizasyonu)
- **Amaç**: Yüksek spread'li pozisyonlarda kar realizasyonu
- **Çalışma Şekli**: Spread > 0.06 (Croplit6) veya > 0.09 (Croplit9) olan pozisyonları tespit edip satış yapar
- **Kullanım**: Manuel veya otomatik tetiklenebilir

#### E) **RUNALL** (Tam Otomasyon Döngüsü)
- **Amaç**: Tüm sistemleri sırayla çalıştıran master otomasyon
- **Çalışma Şekli**: Sürekli döngü halinde çalışır
- **Kullanım**: En üst seviye otomasyon

### 2.2. PSFALGO'nun Çalışma Mantığı

PSFALGO, **skor bazlı filtreleme** sistemi kullanır. Her hisse için şu skorlar hesaplanır:

- **Fbtot**: Front Buy toplam skoru (Long pozisyonlar için)
- **SFStot**: Short Front Sell toplam skoru (Short pozisyonlar için)
- **GORT**: Grup ortalamasına göre relative değer skoru
- **SMA63 chg**: 63 günlük hareketli ortalama değişimi
- **Ask Sell Pahalılık**: Ask fiyatından satış yapıldığında ne kadar pahalı
- **Bid Buy Ucuzluk**: Bid fiyatından alış yapıldığında ne kadar ucuz

Bu skorlara göre pozisyonlar filtrelenir ve uygun olanlar için emirler gönderilir.

---

## 3. PORT ADJUSTER NEDİR?

**Port Adjuster**, portföyün **exposure (maruz kalma)** ve **lot dağılımını** ayarlamak için kullanılan bir araçtır.

### 3.1. Port Adjuster'ın Amacı

Port Adjuster, şu işlemleri yapar:

1. **Total Exposure Hesaplama**: Toplam exposure limitini belirler
2. **Long/Short Oranı Ayarlama**: Portföyün % kaçının Long, % kaçının Short olacağını belirler
3. **Grup Bazlı Lot Dağıtımı**: Her grup (heldff, heldkuponlu, vs.) için ne kadar lot ayrılacağını hesaplar
4. **Lot Hakları Hesaplama**: Long ve Short için ayrı lot hakları hesaplar

### 3.2. Port Adjuster'ın Çalışma Şekli

#### Step 1: Temel Parametreler
- **Total Exposure**: Toplam exposure limiti (örn: 1,000,000 USD)
- **Avg Pref Price**: Ortalama preferred stock fiyatı (örn: 25 USD)
- **Long Ratio**: Long pozisyonların yüzdesi (örn: %85)
- **Short Ratio**: Short pozisyonların yüzdesi (örn: %15)

Bu parametrelere göre:
- **Total Lot** = Total Exposure / Avg Pref Price = 1,000,000 / 25 = 40,000 lot
- **Long Lot** = Total Lot × Long Ratio = 40,000 × 0.85 = 34,000 lot
- **Short Lot** = Total Lot × Short Ratio = 40,000 × 0.15 = 6,000 lot

#### Step 2: Grup Bazlı Dağıtım

Port Adjuster, **22 farklı grup** için lot dağılımı yapar:

**Long Gruplar:**
- `heldff`: %35.0 (en büyük pay)
- `heldkuponlu`: %15.0
- `highmatur`: %15.0
- `helddeznff`: %10.0
- `heldtitrekhc`: %8.0
- `heldnff`: %5.0
- `heldsolidbig`: %5.0
- `nottitrekhc`: %4.0
- `heldotelremorta`: %3.0
- Diğerleri: %0.0 (aktif değil)

**Short Gruplar:**
- `heldkuponlu`: %50
- `helddeznff`: %30
- Diğerleri: %0 (aktif değil)

Her grup için:
- **Grup Lot Miktarı** = Long/Short Lot × (Grup Yüzdesi / 100)
- **Grup Toplam Değer** = Grup Lot Miktarı × Avg Pref Price

### 3.3. Port Adjuster'ın Kullanımı

Port Adjuster, **ADDNEWPOS** modülü ile entegre çalışır. ADDNEWPOS yeni pozisyon açarken:

1. Port Adjuster'dan grup bazlı lot limitlerini alır
2. Mevcut pozisyonları kontrol eder
3. Kalan lot haklarına göre yeni pozisyonlar açar
4. Exposure limitlerini kontrol eder

### 3.4. Port Adjuster'ın Önemi

Port Adjuster, **risk yönetimi** için kritik bir araçtır:

- **Diversifikasyon**: Portföyün farklı gruplara dağıtılmasını sağlar
- **Exposure Kontrolü**: Toplam exposure'ın limitler içinde kalmasını garanti eder
- **Long/Short Dengesi**: Portföyün Long/Short oranını kontrol eder
- **Grup Bazlı Limitler**: Her grup için maksimum lot limitleri belirler

---

## 4. RUNALL MOD

**RUNALL**, PSFALGO sisteminin **en üst seviye otomasyon modülü**dür. Tüm alt sistemleri sırayla çalıştıran master döngüdür.

### 4.1. RUNALL'ın Amacı

RUNALL, şu işlemleri **sürekli döngü halinde** yapar:

1. **Lot Bölücü Açma**: Lot bölücü penceresini açar (eğer checkbox işaretliyse)
2. **Controller ON**: Controller'ı aktif hale getirir (limit kontrolleri için)
3. **Exposure Kontrolü**: Mevcut exposure'ı kontrol eder ve mod belirler (OFANSIF/DEFANSIF/GEÇİŞ)
4. **KARBOTU veya REDUCEMORE Başlatma**: Moda göre KARBOTU (OFANSIF) veya REDUCEMORE (DEFANSIF) başlatır
5. **ADDNEWPOS Kontrolü**: KARBOTU/REDUCEMORE bitince ADDNEWPOS'u kontrol eder
6. **Qpcal İşlemi**: Spreadkusu panel üzerinden Qpcal işlemini yapar
7. **Emir İptali**: 2 dakika sonra tüm emirleri iptal eder
8. **Yeni Döngü**: Tüm işlemler bitince yeni döngü başlar

### 4.2. RUNALL'ın Çalışma Akışı

```
RUNALL Başlatıldı
    ↓
Adım 1: Lot Bölücü Aç (checkbox kontrolü)
    ↓
Adım 2: Controller ON
    ↓
Adım 3: Exposure Kontrolü (Async - thread'de)
    ↓
Adım 4: Mod Belirleme
    ├─ OFANSIF → KARBOTU başlat
    ├─ DEFANSIF → REDUCEMORE başlat
    └─ GEÇİŞ → REDUCEMORE başlat
    ↓
KARBOTU/REDUCEMORE Bitince:
    ↓
Adım 5: ADDNEWPOS Kontrolü
    ├─ Pot Toplam < Pot Max → ADDNEWPOS aktif
    └─ Pot Toplam >= Pot Max → ADDNEWPOS pasif
    ↓
Adım 6: Qpcal İşlemi (Spreadkusu panel)
    ↓
Adım 7: 2 Dakika Bekle
    ↓
Adım 8: Emirleri İptal Et
    ↓
Adım 9: Yeni Döngü Başlat (Adım 1'e dön)
```

### 4.3. RUNALL'ın Özellikleri

#### A) **Döngü Sayacı**
- Her döngü için bir sayaç tutulur
- Döngü numarası UI'da gösterilir
- Döngü raporları döngü numarasına göre filtrelenebilir

#### B) **Allowed Modu**
- **RUNALL Allowed** checkbox'ı işaretliyse, otomatik onay sistemi devreye girer
- Emir onay pencereleri otomatik olarak onaylanır
- Manuel müdahale gerektirmez

#### C) **Lot Bölücü Entegrasyonu**
- **Lot Bölücü** checkbox'ı işaretliyse, her döngüde lot bölücü penceresi açılır
- Lot bölücü, emirleri parçalara böler (200'lük parçalar)

#### D) **RevOrder Mod Entegrasyonu**
- **RevOrder Mod** checkbox'ı işaretliyse, reverse order sistemi aktif olur
- Reverse order, kar garantisi için otomatik emirler gönderir

### 4.4. RUNALL'ın Durdurulması

RUNALL, **"RUNALL DURDUR"** butonu ile durdurulabilir. Durdurulduğunda:

- Tüm alt sistemler durdurulur
- Emirler iptal edilmez (manuel iptal gerekir)
- Döngü sayacı sıfırlanmaz (kalıcıdır)

---

## 5. ALLOWED MOD

**ALLOWED Mod**, RUNALL'ın **otomatik onay sistemi**dir. Bu mod aktif olduğunda, emir onay pencereleri otomatik olarak onaylanır.

### 5.1. ALLOWED Mod'un Amacı

ALLOWED Mod, **tam otomasyon** için gereklidir. Manuel müdahale olmadan sistemin çalışmasını sağlar.

### 5.2. ALLOWED Mod'un Çalışma Şekli

ALLOWED Mod aktif olduğunda:

1. **KARBOTU/REDUCEMORE**: Onay pencereleri otomatik onaylanır
2. **ADDNEWPOS**: Onay pencereleri otomatik onaylanır
3. **CROPLIT**: Onay pencereleri otomatik onaylanır
4. **Diğer Emirler**: Tüm emir onay pencereleri otomatik onaylanır

### 5.3. ALLOWED Mod'un Güvenliği

ALLOWED Mod, **risk kontrolü** ile korunur:

- **Limit Kontrolleri**: Tüm limit kontrolleri (MAXALW, BEFDAY, SMI) hala aktif
- **Exposure Kontrolleri**: Exposure limitleri hala kontrol edilir
- **Grup Limitleri**: Grup bazlı limitler hala aktif
- **JFIN Kontrolleri**: JFIN hesaplanan lot kontrolleri hala aktif

ALLOWED Mod sadece **onay pencerelerini** atlar, **limit kontrollerini** atlamaz.

### 5.4. ALLOWED Mod'un Kullanımı

ALLOWED Mod, **RUNALL Allowed** checkbox'ı ile aktif edilir:

- ✅ **İşaretli**: ALLOWED Mod aktif, otomatik onay
- ❌ **İşaretsiz**: ALLOWED Mod pasif, manuel onay gerekir

**ÖNEMLİ**: ALLOWED Mod aktifken sistem tam otomatik çalışır. Dikkatli kullanılmalıdır.

---

## 6. KARBOTU

**KARBOTU**, "Kar Botu" anlamına gelir. **Long pozisyonları kar realizasyonu için azaltan** agresif bir otomasyon modülüdür.

### 6.1. KARBOTU'nun Amacı

KARBOTU, şu durumlarda kullanılır:

- **OFANSIF Mod**: Exposure limitleri içinde, agresif kar realizasyonu
- **Yüksek Kar Fırsatları**: Ask Sell pahalılık skorları yüksek olan pozisyonlar
- **Fbtot Bazlı Filtreleme**: Fbtot skorlarına göre pozisyonları filtreler

### 6.2. KARBOTU'nun 13 Adımlı Süreci

KARBOTU, **13 adımlı bir otomasyon süreci** izler:

#### **Adım 1: Take Profit Longs Penceresi Aç**
- Take Profit Longs panelini açar
- Tüm Long pozisyonları yükler
- GORT kontrolü yapar (Gort > -1 ve Ask Sell pahalılık > -0.05)

#### **Adım 2: Fbtot < 1.10 Kontrolü**
- **Filtre**: Fbtot < 1.10 ve Ask Sell pahalılık > -0.10
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Ask Sell
- **Mantık**: Çok düşük Fbtot'lu pozisyonları agresif şekilde sat

#### **Adım 3: Fbtot 1.11-1.45 (Düşük) Kontrolü**
- **Filtre**: 1.11 ≤ Fbtot < 1.45 ve Ask Sell pahalılık > -0.10
- **Lot Yüzdesi**: %25
- **Emir Tipi**: Ask Sell
- **Mantık**: Orta düşük Fbtot'lu pozisyonları orta seviyede sat

#### **Adım 4: Fbtot 1.11-1.45 (Yüksek) Kontrolü**
- **Filtre**: 1.11 ≤ Fbtot < 1.45 ve Ask Sell pahalılık > 0.05
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Ask Sell
- **Mantık**: Orta Fbtot'lu ama yüksek pahalılık skorlu pozisyonları agresif sat

#### **Adım 5: Fbtot 1.46-1.85 (Düşük) Kontrolü**
- **Filtre**: 1.46 ≤ Fbtot < 1.85 ve Ask Sell pahalılık > -0.10
- **Lot Yüzdesi**: %25
- **Emir Tipi**: Ask Sell
- **Mantık**: Orta yüksek Fbtot'lu pozisyonları orta seviyede sat

#### **Adım 6: Fbtot 1.46-1.85 (Yüksek) Kontrolü**
- **Filtre**: 1.46 ≤ Fbtot < 1.85 ve Ask Sell pahalılık > 0.10
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Ask Sell
- **Mantık**: Orta yüksek Fbtot'lu ama çok yüksek pahalılık skorlu pozisyonları agresif sat

#### **Adım 7: Fbtot 1.86-2.10 Kontrolü**
- **Filtre**: 1.86 ≤ Fbtot < 2.10 ve Ask Sell pahalılık > 0.15
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Ask Sell
- **Mantık**: Yüksek Fbtot'lu ve çok yüksek pahalılık skorlu pozisyonları agresif sat

#### **Adım 8: Take Profit Shorts Penceresi Aç**
- Take Profit Shorts panelini açar
- Tüm Short pozisyonları yükler
- GORT kontrolü yapar (Gort < 1 ve Bid Buy ucuzluk < +0.08)

#### **Adım 9: SFStot > 1.70 Kontrolü**
- **Filtre**: SFStot > 1.70 ve Bid Buy ucuzluk < 0.10
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Bid Buy (Short pozisyonları kapatmak için)
- **Mantık**: Çok yüksek SFStot'lu Short pozisyonları agresif şekilde kapat

#### **Adım 10: SFStot 1.40-1.69 (Düşük) Kontrolü**
- **Filtre**: 1.40 ≤ SFStot < 1.69 ve Bid Buy ucuzluk < 0.10
- **Lot Yüzdesi**: %25
- **Emir Tipi**: Bid Buy
- **Mantık**: Orta yüksek SFStot'lu Short pozisyonları orta seviyede kapat

#### **Adım 11: SFStot 1.40-1.69 (Yüksek) Kontrolü**
- **Filtre**: 1.40 ≤ SFStot < 1.69 ve Bid Buy ucuzluk < -0.05
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Bid Buy
- **Mantık**: Orta yüksek SFStot'lu ama çok yüksek ucuzluk skorlu Short pozisyonları agresif kapat

#### **Adım 12: SFStot 1.20-1.39 Kontrolü**
- **Filtre**: 1.20 ≤ SFStot < 1.39 ve Bid Buy ucuzluk < -0.10
- **Lot Yüzdesi**: %50
- **Emir Tipi**: Bid Buy
- **Mantık**: Orta SFStot'lu ama çok yüksek ucuzluk skorlu Short pozisyonları agresif kapat

#### **Adım 13: Tamamlandı**
- KARBOTU süreci tamamlandı
- RUNALL'a callback gönderilir
- ADDNEWPOS kontrolü yapılır

### 6.3. KARBOTU'nun Filtreleme Mantığı

KARBOTU, **çoklu filtreleme** kullanır:

1. **Fbtot/SFStot Skorları**: Pozisyonun skoruna göre filtreleme
2. **Ask Sell/Bid Buy Pahalılık/Ucuzluk**: Fiyat skorlarına göre filtreleme
3. **GORT Kontrolü**: Grup ortalamasına göre relative değer kontrolü
4. **Minimum Lot**: 100 lot altı pozisyonlar göz ardı edilir
5. **Exclude List**: Exclude listesindeki hisseler atlanır

### 6.4. KARBOTU'nun Lot Hesaplama Mantığı

KARBOTU, **yüzde bazlı lot hesaplama** kullanır:

- **Lot Yüzdesi**: Her adım için farklı lot yüzdesi (örn: %25, %50)
- **Hesaplama**: `calculated_lot = qty × (lot_percentage / 100)`
- **Yuvarlama**: 100'lük birimlere yuvarlanır (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, vs.)
- **Minimum**: 200 lot altı pozisyonlar için tamamı gönderilir

### 6.5. KARBOTU'nun Limit Kontrolleri

KARBOTU, **çoklu limit kontrolü** yapar:

1. **MAXALW Kontrolü**: MAXALW × çarpan (reduce_rules'a göre)
2. **BEFDAY Kontrolü**: BEFDAY × çarpan (reduce_rules'a göre)
3. **SMI Kontrolü**: SMI limiti
4. **Günlük Azaltma Limiti**: Günlük maksimum azaltma limiti
5. **Ters Pozisyon Kontrolü**: Tersine geçme önleme

**ÖNEMLİ**: KARBOTU, **pozisyon azaltma** işlemi yaptığı için, toplam pozisyon limiti kontrolü **YAPILMAZ**. Sadece azaltma limitleri kontrol edilir.

---

## 7. REDUCEMORE

**REDUCEMORE**, "Daha Fazla Azalt" anlamına gelir. **KARBOTU'dan daha konservatif** bir pozisyon azaltma modülüdür.

### 7.1. REDUCEMORE'un Amacı

REDUCEMORE, şu durumlarda kullanılır:

- **DEFANSIF Mod**: Exposure limitleri yüksek, konservatif yaklaşım
- **GEÇİŞ Modu**: Exposure limitleri orta seviyede, dengeli yaklaşım
- **Risk Azaltma**: Pozisyonları agresif şekilde azaltmak yerine, kontrollü şekilde azaltmak

### 7.2. REDUCEMORE'un 13 Adımlı Süreci

REDUCEMORE, KARBOTU ile **aynı 13 adımlı süreci** izler, ancak **daha konservatif parametreler** kullanır:

#### **Temel Farklar:**

1. **GORT Kontrolü (Longs)**: 
   - KARBOTU: Gort > -1 ve Ask Sell pahalılık > -0.05
   - REDUCEMORE: Gort > -1 ve Ask Sell pahalılık > -0.08 (daha gevşek)

2. **GORT Kontrolü (Shorts)**:
   - KARBOTU: Gort < 1 ve Bid Buy ucuzluk < +0.08
   - REDUCEMORE: Gort < 1 ve Bid Buy ucuzluk < +0.08 (aynı)

3. **Lot Yüzdeleri**: Genellikle KARBOTU ile aynı, ancak bazı adımlarda daha düşük olabilir

4. **Filtre Eşikleri**: Bazı filtre eşikleri KARBOTU'dan daha gevşektir (daha fazla pozisyon seçer)

### 7.3. REDUCEMORE'un Kullanım Senaryoları

REDUCEMORE, şu durumlarda tercih edilir:

1. **Yüksek Exposure**: Exposure limitleri yüksek olduğunda
2. **Risk Azaltma Önceliği**: Kar realizasyonundan çok risk azaltma öncelikli olduğunda
3. **Piyasa Volatilitesi**: Piyasa volatilitesi yüksek olduğunda
4. **Konservatif Yaklaşım**: Daha konservatif bir yaklaşım istenildiğinde

### 7.4. REDUCEMORE vs KARBOTU

| Özellik | KARBOTU | REDUCEMORE |
|---------|---------|------------|
| **Mod** | OFANSIF | DEFANSIF/GEÇİŞ |
| **Yaklaşım** | Agresif kar realizasyonu | Konservatif risk azaltma |
| **Filtre Eşikleri** | Daha sıkı | Daha gevşek |
| **Lot Yüzdeleri** | Genellikle daha yüksek | Genellikle daha düşük |
| **GORT Kontrolü** | Daha sıkı | Daha gevşek |
| **Kullanım** | Yüksek kar fırsatları | Risk azaltma önceliği |

---

## 8. ADDNEWPOS

**ADDNEWPOS**, "Add New Position" anlamına gelir. **Yeni pozisyonlar açmak veya mevcut pozisyonlara ekleme yapmak** için kullanılan modüldür.

### 8.1. ADDNEWPOS'un Amacı

ADDNEWPOS, şu işlemleri yapar:

1. **Yeni Pozisyon Açma**: Uygun fırsatları tespit edip yeni pozisyonlar açar
2. **Pozisyon Artırma**: Mevcut pozisyonlara ekleme yapar
3. **Port Adjuster Entegrasyonu**: Port Adjuster'dan grup bazlı lot limitlerini alır
4. **Exposure Kontrolü**: Exposure limitleri içinde kalır

### 8.2. ADDNEWPOS'un Çalışma Şekli

ADDNEWPOS, **Port Adjuster** ile entegre çalışır:

1. **Port Adjuster'dan Limitler Al**: Her grup için maksimum lot limitlerini alır
2. **Mevcut Pozisyonları Kontrol Et**: Her grup için mevcut pozisyonları kontrol eder
3. **Kalan Lot Hesapla**: Maksimum lot - Mevcut lot = Kalan lot
4. **Uygun Hisseleri Filtrele**: Skor bazlı filtreleme yapar
5. **Yeni Pozisyonlar Aç**: Kalan lot limitleri içinde yeni pozisyonlar açar

### 8.3. ADDNEWPOS'un Modları

ADDNEWPOS, **3 farklı modda** çalışabilir:

#### A) **AddLong Only** (Sadece Long Ekleme)
- **Amaç**: Sadece Long pozisyonlar açar
- **Kullanım**: Long exposure'ı artırmak için
- **Filtreleme**: Bid Buy ucuzluk skorlarına göre

#### B) **AddShort Only** (Sadece Short Ekleme)
- **Amaç**: Sadece Short pozisyonlar açar
- **Kullanım**: Short exposure'ı artırmak için
- **Filtreleme**: Ask Sell pahalılık skorlarına göre

#### C) **AddBoth** (Her İkisini de Ekleme)
- **Amaç**: Hem Long hem Short pozisyonlar açar
- **Kullanım**: Dengeli exposure artışı için
- **Filtreleme**: Her iki yönde de skor bazlı filtreleme

### 8.4. ADDNEWPOS'un Kuralları

ADDNEWPOS, **eşik bazlı kurallar** kullanır:

```python
addnewpos_rules = {
    1: (0.50, 5.0),    # < %1: MAXALW×0.50, Portföy×%5
    3: (0.40, 4.0),    # %1-2.99: MAXALW×0.40, Portföy×%4
    5: (0.30, 3.0),    # %3-4.99: MAXALW×0.30, Portföy×%3
    7: (0.20, 2.0),    # %5-6.99: MAXALW×0.20, Portföy×%2
    10: (0.10, 1.5),   # %7-9.99: MAXALW×0.10, Portföy×%1.5
    100: (0.05, 1.0)   # >= %10: MAXALW×0.05, Portföy×%1
}
```

**Açıklama:**
- **Eşik Yüzdesi**: Mevcut pozisyonun portföy içindeki yüzdesi
- **MAXALW Çarpanı**: MAXALW değerinin çarpanı (ne kadar lot açılabilir)
- **Portföy Yüzdesi**: Portföyün maksimum % kaçı bu hisseye ayrılabilir

**Örnek:**
- Bir hisse portföyün %2'sini oluşturuyorsa → Eşik: 3
- MAXALW = 1000 lot → Maksimum lot = 1000 × 0.40 = 400 lot
- Portföy = 40,000 lot → Maksimum portföy % = %4 = 1,600 lot
- **Sonuç**: Minimum(400, 1,600) = 400 lot açılabilir

### 8.5. ADDNEWPOS'un Exposure Kontrolü

ADDNEWPOS, **exposure limit kontrolü** yapar:

- **Pot Toplam**: Mevcut toplam exposure
- **Pot Max**: Maksimum exposure limiti
- **Kalan Exposure**: Pot Max - Pot Toplam
- **Exposure Yüzdesi**: Kalan exposure'ın % kaçı kullanılacak (default: %60)

**Örnek:**
- Pot Max = 6,363,600 USD
- Pot Toplam = 5,000,000 USD
- Kalan Exposure = 1,363,600 USD
- Exposure Yüzdesi = %60
- **Kullanılabilir Exposure** = 1,363,600 × 0.60 = 818,160 USD

### 8.6. ADDNEWPOS'un Limit Kontrolleri

ADDNEWPOS, **çoklu limit kontrolü** yapar:

1. **MAXALW Kontrolü**: MAXALW × çarpan (addnewpos_rules'a göre)
2. **Portföy Yüzdesi Kontrolü**: Portföyün maksimum % kaçı
3. **Grup Lot Limiti**: Port Adjuster'dan gelen grup bazlı lot limitleri
4. **Exposure Limiti**: Kalan exposure × exposure yüzdesi
5. **JFIN Kontrolü**: JFIN hesaplanan lot × 2 kontrolü
6. **Günlük Değişim Limiti**: Günlük maksimum değişim limiti

**ÖNEMLİ**: ADDNEWPOS, **pozisyon artırma** işlemi yaptığı için, toplam pozisyon limiti kontrolü **YAPILIR**.

---

## 9. CROPLIT6 VE CROPLIT9

**CROPLIT**, "Crop Split" anlamına gelir. **Yüksek spread'li pozisyonlarda kar realizasyonu** için kullanılan modüldür.

### 9.1. CROPLIT'in Amacı

CROPLIT, şu durumlarda kullanılır:

- **Yüksek Spread**: Spread > 0.06 (Croplit6) veya > 0.09 (Croplit9)
- **Kar Realizasyonu**: Yüksek spread'den faydalanarak kar realizasyonu
- **Pozisyon Azaltma**: Pozisyonların bir kısmını satarak kar almak

### 9.2. CROPLIT6

**CROPLIT6**, spread eşiği **0.06** olan CROPLIT versiyonudur.

#### **CROPLIT6 Koşulları (Longs):**
- **Spread > 0.06**: Bid-Ask spread'i 6 cent'ten büyük olmalı
- **Ask Sell Pahalılık > -0.06**: Ask fiyatından satış yapıldığında en az -6 cent pahalılık
- **Minimum Lot**: 200 lot (200'den küçükse tamamı)

#### **CROPLIT6 Koşulları (Shorts):**
- **Spread > 0.06**: Bid-Ask spread'i 6 cent'ten büyük olmalı
- **Bid Buy Ucuzluk < 0.06**: Bid fiyatından alış yapıldığında en fazla +6 cent ucuzluk
- **Minimum Lot**: 200 lot (200'den küçükse tamamı)

#### **CROPLIT6 Lot Hesaplama:**
- **200'den Küçük**: Tamamı gönderilir
- **200'den Büyük**: %10 hesaplanır ve 100'lük birime yuvarlanır
- **Minimum**: 200 lot

**Örnek:**
- Pozisyon: 1,000 lot Long
- Spread: 0.08 (> 0.06 ✓)
- Ask Sell Pahalılık: -0.04 (> -0.06 ✓)
- **Hesaplanan Lot**: 1,000 × 0.10 = 100 lot → 200 lot (minimum)
- **Emir**: 200 lot Ask Sell

### 9.3. CROPLIT9

**CROPLIT9**, spread eşiği **0.09** olan CROPLIT versiyonudur.

#### **CROPLIT9 Koşulları:**
- **Spread > 0.09**: Bid-Ask spread'i 9 cent'ten büyük olmalı
- **Longs**: Ask Sell Pahalılık > -0.06 (CROPLIT6 ile aynı)
- **Shorts**: Bid Buy Ucuzluk < 0.06 (CROPLIT6 ile aynı)

#### **CROPLIT9 vs CROPLIT6:**

| Özellik | CROPLIT6 | CROPLIT9 |
|---------|----------|----------|
| **Spread Eşiği** | > 0.06 | > 0.09 |
| **Pahalılık/Ucuzluk** | > -0.06 / < 0.06 | > -0.06 / < 0.06 |
| **Kullanım** | Daha sık tetiklenir | Daha seçici, daha yüksek spread |

### 9.4. CROPLIT'in Çalışma Şekli

CROPLIT, şu adımları izler:

1. **Take Profit Longs Panelini Aç**: Tüm Long pozisyonları yükler
2. **Long Pozisyonları Kontrol Et**: Her pozisyon için spread ve pahalılık kontrolü
3. **Uygun Pozisyonları Filtrele**: Koşullara uyan pozisyonları seçer
4. **Lot Hesapla**: %10 hesaplama ve yuvarlama
5. **Emir Gönder**: Ask Sell emirleri gönderir
6. **Take Profit Shorts Panelini Aç**: Tüm Short pozisyonları yükler
7. **Short Pozisyonları Kontrol Et**: Her pozisyon için spread ve ucuzluk kontrolü
8. **Uygun Pozisyonları Filtrele**: Koşullara uyan pozisyonları seçer
9. **Lot Hesapla**: %10 hesaplama ve yuvarlama
10. **Emir Gönder**: Bid Buy emirleri gönderir (Short pozisyonları kapatmak için)

### 9.5. CROPLIT'in Kullanım Senaryoları

CROPLIT, şu durumlarda kullanılır:

1. **Yüksek Spread Fırsatları**: Piyasada yüksek spread'ler olduğunda
2. **Likidite Düşüklüğü**: Likidite düşük olduğunda spread'ler artar
3. **Kar Realizasyonu**: Yüksek spread'den faydalanarak kar almak
4. **Pozisyon Optimizasyonu**: Pozisyonları optimize etmek

---

## 10. KURALLAR SİSTEMİ

PSFALGO, **eşik bazlı kurallar sistemi** kullanır. Her kural, **pozisyonun portföy içindeki yüzdesine** göre farklı limitler belirler.

### 10.1. KARBOTU/REDUCEMORE Kuralları

KARBOTU ve REDUCEMORE, **reduce_rules** kullanır:

```python
reduce_rules = {
    3: (None, None),    # < %3: Sınırsız (ama ters poz. yasak)
    5: (0.75, 0.75),    # %3-4.99: MAXALW×0.75, BefQty×0.75
    7: (0.60, 0.60),    # %5-6.99: MAXALW×0.60, BefQty×0.60
    10: (0.50, 0.50),   # %7-9.99: MAXALW×0.50, BefQty×0.50
    100: (0.40, 0.40)   # >= %10: MAXALW×0.40, BefQty×0.40
}
```

**Açıklama:**
- **Eşik Yüzdesi**: Mevcut pozisyonun portföy içindeki yüzdesi
- **MAXALW Çarpanı**: MAXALW değerinin çarpanı (ne kadar lot azaltılabilir)
- **BefQty Çarpanı**: BEFDAY (gün başı pozisyon) çarpanı

**Örnek:**
- Bir hisse portföyün %6'sını oluşturuyorsa → Eşik: 7
- MAXALW = 1000 lot → Maksimum azaltma = 1000 × 0.60 = 600 lot
- BEFDAY = 800 lot → Maksimum azaltma = 800 × 0.60 = 480 lot
- **Sonuç**: Minimum(600, 480) = 480 lot azaltılabilir

**ÖNEMLİ**: < %3 için sınırsız, ancak **ters pozisyon yasak** (Long → Short veya Short → Long geçiş yasak).

### 10.2. ADDNEWPOS Kuralları

ADDNEWPOS, **addnewpos_rules** kullanır (yukarıda detaylı açıklandı).

### 10.3. Kuralların Mantığı

Kurallar sistemi, **risk yönetimi** için kritiktir:

1. **Küçük Pozisyonlar**: Küçük pozisyonlar için daha esnek limitler
2. **Büyük Pozisyonlar**: Büyük pozisyonlar için daha sıkı limitler
3. **Konsantrasyon Önleme**: Tek bir hisseye çok fazla exposure önlenir
4. **Diversifikasyon**: Portföyün farklı hisselere dağıtılması sağlanır

---

## 11. FBTOT, GORT, SMA63CHG VE DİĞER METRİKLER

PSFALGO, **skor bazlı filtreleme** için çeşitli metrikler kullanır. Bu metrikler, her hisse için hesaplanır ve pozisyon kararlarında kullanılır.

### 11.1. FBTOT (Front Buy Total)

**FBTOT**, "Front Buy Total" anlamına gelir. **Long pozisyonlar için** kullanılan bir skordur.

#### **FBTOT'un Hesaplanması:**

FBTOT, şu skorların toplamıdır:

1. **Final_BB_skor**: Bid Buy final skoru
2. **Final_FB_skor**: Front Buy final skoru
3. **Final_AB_skor**: Ask Buy final skoru

**Formül:**
```
FBTOT = Final_BB_skor + Final_FB_skor + Final_AB_skor
```

#### **FBTOT'un Anlamı:**

- **FBTOT > 1.0**: Pozitif skor, Long pozisyon için uygun
- **FBTOT < 1.0**: Negatif skor, Long pozisyon için uygun değil
- **FBTOT Yüksek**: Daha güçlü Long sinyali
- **FBTOT Düşük**: Daha zayıf Long sinyali

#### **FBTOT'un Kullanımı:**

- **KARBOTU**: Fbtot < 1.10, 1.11-1.45, 1.46-1.85, 1.86-2.10 aralıklarına göre filtreleme
- **ADDNEWPOS**: Fbtot yüksek olan hisseler için Long pozisyon açma
- **Pozisyon Yönetimi**: Mevcut Long pozisyonların skorlarını takip etme

### 11.2. SFSTOT (Short Front Sell Total)

**SFSTOT**, "Short Front Sell Total" anlamına gelir. **Short pozisyonlar için** kullanılan bir skordur.

#### **SFSTOT'un Hesaplanması:**

SFSTOT, şu skorların toplamıdır:

1. **Final_AS_skor**: Ask Sell final skoru
2. **Final_FS_skor**: Front Sell final skoru
3. **Final_BS_skor**: Bid Sell final skoru

**Formül:**
```
SFSTOT = Final_AS_skor + Final_FS_skor + Final_BS_skor
```

#### **SFSTOT'un Anlamı:**

- **SFSTOT > 1.0**: Pozitif skor, Short pozisyon için uygun
- **SFSTOT < 1.0**: Negatif skor, Short pozisyon için uygun değil
- **SFSTOT Yüksek**: Daha güçlü Short sinyali
- **SFSTOT Düşük**: Daha zayıf Short sinyali

#### **SFSTOT'un Kullanımı:**

- **KARBOTU**: SFStot > 1.70, 1.40-1.69, 1.20-1.39 aralıklarına göre filtreleme
- **ADDNEWPOS**: SFStot yüksek olan hisseler için Short pozisyon açma
- **Pozisyon Yönetimi**: Mevcut Short pozisyonların skorlarını takip etme

### 11.3. GORT (Grup Ortalaması Relative Değer)

**GORT**, "Group Relative" anlamına gelir. **Grup ortalamasına göre relative değer skoru**dur.

#### **GORT'un Hesaplanması:**

GORT, şu şekilde hesaplanır:

1. **Grup Belirleme**: Hissenin hangi gruba ait olduğunu belirle (heldff, heldkuponlu, vs.)
2. **CGRUP Belirleme**: Eğer heldkuponlu grubu ise, CGRUP'u belirle (C400, C450, vs.)
3. **Grup Ortalaması Hesapla**: Grup içindeki tüm hisselerin SMA63 chg ortalamasını hesapla
4. **Relative Değer Hesapla**: Hissenin SMA63 chg'si - Grup ortalaması

**Formül:**
```
GORT = Hissenin_SMA63_chg - Grup_Ortalaması_SMA63_chg
```

#### **GORT'un Anlamı:**

- **GORT > 0**: Hisse, grubundan daha iyi performans gösteriyor (relative olarak pahalı)
- **GORT < 0**: Hisse, grubundan daha kötü performans gösteriyor (relative olarak ucuz)
- **GORT Yüksek**: Grubuna göre daha pahalı, satış fırsatı
- **GORT Düşük**: Grubuna göre daha ucuz, alış fırsatı

#### **GORT'un Kullanımı:**

- **KARBOTU (Longs)**: Gort > -1 ve Ask Sell pahalılık > -0.05 → Satış fırsatı
- **KARBOTU (Shorts)**: Gort < 1 ve Bid Buy ucuzluk < +0.08 → Kapatma fırsatı
- **REDUCEMORE (Longs)**: Gort > -1 ve Ask Sell pahalılık > -0.08 → Satış fırsatı
- **REDUCEMORE (Shorts)**: Gort < 1 ve Bid Buy ucuzluk < +0.08 → Kapatma fırsatı
- **ADDNEWPOS**: Gort düşük olan hisseler için Long, Gort yüksek olan hisseler için Short

### 11.4. SMA63 CHG (63 Günlük Hareketli Ortalama Değişimi)

**SMA63 CHG**, "63 Günlük Simple Moving Average Change" anlamına gelir. **Orta vadeli trend göstergesi**dir.

#### **SMA63 CHG'un Hesaplanması:**

SMA63 CHG, şu şekilde hesaplanır:

1. **SMA63 Hesapla**: Son 63 günün kapanış fiyatlarının ortalaması
2. **Önceki SMA63 Hesapla**: Bir önceki günün SMA63 değeri
3. **Değişim Hesapla**: SMA63 - Önceki SMA63

**Formül:**
```
SMA63_CHG = SMA63(today) - SMA63(yesterday)
```

#### **SMA63 CHG'un Anlamı:**

- **SMA63 CHG > 0**: Orta vadeli yükseliş trendi
- **SMA63 CHG < 0**: Orta vadeli düşüş trendi
- **SMA63 CHG Yüksek**: Güçlü yükseliş trendi
- **SMA63 CHG Düşük**: Güçlü düşüş trendi

#### **SMA63 CHG'un Kullanımı:**

- **Filtreleme**: Long pozisyonlar için SMA63 CHG < -1.6 gibi filtreler
- **GORT Hesaplama**: GORT hesaplamasında kullanılır
- **Trend Analizi**: Orta vadeli trend analizi için kullanılır

### 11.5. Ask Sell Pahalılık / Bid Buy Ucuzluk

**Ask Sell Pahalılık** ve **Bid Buy Ucuzluk**, **fiyat skorları**dır.

#### **Ask Sell Pahalılık:**

Ask Sell Pahalılık, **Long pozisyonları satarken** ne kadar pahalı satıldığını gösterir.

**Hesaplama:**
```
Ask_Sell_Pahalılık = Ask_Fiyatı - Prev_Close - Benchmark_Change
```

**Anlamı:**
- **Pahalılık > 0**: Ask fiyatından satış yapıldığında kar var
- **Pahalılık < 0**: Ask fiyatından satış yapıldığında zarar var
- **Pahalılık Yüksek**: Daha iyi satış fırsatı

#### **Bid Buy Ucuzluk:**

Bid Buy Ucuzluk, **Short pozisyonları kapatırken** ne kadar ucuz alındığını gösterir.

**Hesaplama:**
```
Bid_Buy_Ucuzluk = Bid_Fiyatı - Prev_Close - Benchmark_Change
```

**Anlamı:**
- **Ucuzluk < 0**: Bid fiyatından alış yapıldığında kar var (Short kapatma)
- **Ucuzluk > 0**: Bid fiyatından alış yapıldığında zarar var
- **Ucuzluk Düşük**: Daha iyi alış fırsatı (Short kapatma)

### 11.6. Diğer Metrikler

#### **SMA246 CHG:**
- **246 Günlük Hareketli Ortalama Değişimi**
- **Uzun vadeli trend göstergesi**
- GORT hesaplamasında kullanılabilir

#### **Final Skorlar:**
- **Final_BB_skor**: Bid Buy final skoru
- **Final_FB_skor**: Front Buy final skoru
- **Final_AB_skor**: Ask Buy final skoru
- **Final_AS_skor**: Ask Sell final skoru
- **Final_FS_skor**: Front Sell final skoru
- **Final_BS_skor**: Bid Sell final skoru
- **Final_SAS_skor**: Short Ask Sell final skoru
- **Final_SFS_skor**: Short Front Sell final skoru
- **Final_SBS_skor**: Short Bid Sell final skoru

Bu skorlar, **benchmark-aware ucuzluk/pahalılık skorları**dır ve FBTOT/SFSTOT hesaplamalarında kullanılır.

---

## 📊 ÖZET TABLO

| Modül | Amaç | Kullanım | Mod |
|-------|------|----------|-----|
| **KARBOTU** | Long pozisyonları kar realizasyonu için azalt | OFANSIF | Pozisyon Azaltma |
| **REDUCEMORE** | Long/Short pozisyonları risk azaltma için azalt | DEFANSIF/GEÇİŞ | Pozisyon Azaltma |
| **ADDNEWPOS** | Yeni pozisyonlar aç veya mevcut pozisyonlara ekle | OFANSIF | Pozisyon Artırma |
| **CROPLIT6/9** | Yüksek spread'li pozisyonlarda kar realizasyonu | Manuel/Otomatik | Kar Realizasyonu |
| **RUNALL** | Tüm sistemleri sırayla çalıştıran master döngü | Otomatik | Tam Otomasyon |
| **Port Adjuster** | Portföy exposure ve lot dağılımını ayarla | ADDNEWPOS ile | Risk Yönetimi |

---

## 🎯 SONUÇ

PSFALGO sistemi, **çok katmanlı risk yönetimi** ve **skor bazlı filtreleme** ile çalışan sofistike bir otomatik trading sistemidir. Sistem, **7/24 çalışabilen, risk kontrollü, kar garantili** bir yapıya sahiptir.

**Temel Prensipler:**
1. **Risk Öncelikli**: Her işlemde risk kontrolü yapılır
2. **Skor Bazlı**: Tüm kararlar skor bazlı filtreleme ile alınır
3. **Limit Kontrollü**: Çoklu limit kontrolleri ile risk minimize edilir
4. **Otomatik**: Manuel müdahale minimum seviyede
5. **Esnek**: Farklı modlar ve kurallar ile esnek yapı

Bu sistem, **preferred stock trading** için özel olarak tasarlanmış ve **Janall uygulamasının kalbi** olarak çalışmaktadır.






