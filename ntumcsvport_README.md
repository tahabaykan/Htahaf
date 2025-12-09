# 📊 ntumcsvport.py - SSFINEK Dosyalarından LONG/SHORT Hisse Seçimi

## 🎯 **Genel Amaç**
Bu script, SSFINEK CSV dosyalarından belirli kriterlere göre LONG ve SHORT hisseleri seçer ve `tumcsvlong.csv` ile `tumcsvshort.csv` dosyalarını oluşturur.

## 📁 **Giriş Dosyaları**
- `ssfinek*.csv` dosyaları (proje kök dizininde bulunmalı)
- Her dosya şu kolonları içermeli: `PREF IBKR`, `FINAL_THG`, `SHORT_FINAL`, `CMON`, `AVG_ADV`, `SMI`, `CGRUP`

## 🚀 **Çalıştırma**
```bash
python ntumcsvport.py
```

## 📋 **Çıkış Dosyaları**
- **`tumcsvlong.csv`**: Seçilen LONG hisseler
- **`tumcsvshort.csv`**: Seçilen SHORT hisseler

## 🔧 **Temel Kurallar ve Kriterler**

### 📊 **LONG Hisse Seçim Kriterleri**
Her dosya için iki kriterin **kesişimi** alınır:
1. **Top X%**: Dosyadaki en yüksek FINAL_THG'ya sahip hisselerin %X'i
2. **Çarpan Kriteri**: FINAL_THG ≥ (Ortalama FINAL_THG × Çarpan)

### 📉 **SHORT Hisse Seçim Kriterleri**
Her dosya için iki kriterin **kesişimi** alınır:
1. **Bottom X%**: Dosyadaki en düşük SHORT_FINAL'a sahip hisselerin %X'i
2. **Çarpan Kriteri**: SHORT_FINAL ≤ (Ortalama SHORT_FINAL × Çarpan)

## 🎯 **Dosya Bazlı Özel Kurallar**

### 📈 **HELDSOLIDBIG Grubu**
```python
'long_percent': 25, 'long_multiplier': 1.5
'short_percent': 20, 'short_multiplier': 0.6
'max_short': 2
```
- **LONG**: Top 25% + 1.5x ortalama
- **SHORT**: Bottom 20% + 0.6x ortalama
- **Maksimum SHORT**: 2 hisse

### 🏦 **HELDKUPONLU Grubu**
```python
'long_percent': 35, 'long_multiplier': 1.3
'short_percent': 40, 'short_multiplier': 0.80
'max_short': 999  # Sınırsız
```
- **LONG**: Top 35% + 1.3x ortalama
- **SHORT**: Bottom 40% + 0.8x ortalama
- **Maksimum SHORT**: Sınırsız

### 🏢 **HELDFF Grubu**
```python
'long_percent': 30, 'long_multiplier': 1.4
'short_percent': 20, 'short_multiplier': 0.5
'max_short': 2
```
- **LONG**: Top 30% + 1.4x ortalama
- **SHORT**: Bottom 20% + 0.5x ortalama
- **Maksimum SHORT**: 2 hisse
- **ÖZEL RECSIZE KURALLARI**: KUME_PREM×12, AVG_ADV/4

### 🏗️ **HELDDEZNFF Grubu**
```python
'long_percent': 25, 'long_multiplier': 1.4
'short_percent': 30, 'short_multiplier': 0.7
'max_short': 2
```
- **LONG**: Top 25% + 1.4x ortalama
- **SHORT**: Bottom 30% + 0.7x ortalama
- **Maksimum SHORT**: 2 hisse

### 📅 **HIGHMATUR Grubu**
```python
'long_percent': 35, 'long_multiplier': 1.35
'short_percent': 7, 'short_multiplier': 0.25
'max_short': 2
```
- **LONG**: Top 35% + 1.35x ortalama
- **SHORT**: Bottom 7% + 0.25x ortalama
- **Maksimum SHORT**: 2 hisse

### 🏪 **HELDKUPONLU Özel İşleme**
`ssfinekheldkuponlu.csv` için özel algoritma:
- **C600 ve C625 hariç** her CGRUP'tan **zorunlu** LONG ve SHORT seçimi
- **CMON sınırlaması**: Her şirketin toplam hisse sayısı / 1.6 (normal yuvarlama)
- **Maksimum**: CGRUP başına 3 LONG + 3 SHORT

## 🔒 **Sınırlamalar ve Filtreler**

### 🏢 **CMON (Şirket) Sınırlaması**
- **Genel Kural**: Her şirketin toplam hisse sayısı / 1.6 (normal yuvarlama)
- **Minimum**: 1 hisse seçilebilir
- **Uygulama**: LONG ve SHORT ayrı ayrı değerlendirilir

### 📊 **CGRUP Sınırlaması**
- **Genel Kural**: CGRUP başına maksimum 3 hisse
- **HELDKUPONLU**: Zorunlu seçimler + ek hisseler toplam 3'ü geçemez

### 📈 **SHORT Maksimum Sınırı**
Her dosya için `max_short` parametresi ile belirlenir (2-999 arası)

## 💰 **RECSIZE Hesaplama Formülü**

### 🔢 **Genel Formül (HELDFF hariç)**
```
RECSIZE = (KUME_PREM × 8 + AVG_ADV/25) / 4
```

### 🏦 **HELDFF Özel Formülü**
```
RECSIZE = (KUME_PREM × 12 + AVG_ADV/25) / 4
```

### 🔒 **Sınırlama Kuralları**
- **Genel**: RECSIZE ≤ AVG_ADV/6 (100'lük yuvarlama)
- **HELDFF**: RECSIZE ≤ AVG_ADV/4 (100'lük yuvarlama)

### 📊 **Yuvarlama**
Tüm RECSIZE değerleri 100'lük tam sayıya yuvarlanır:
- 340 → 300
- 480 → 500
- 1,250 → 1,300

## 📊 **KUME_ORT ve KUME_PREM Hesaplama**

### 🟢 **LONG Hisseler için**
- **KUME_ORT**: Aynı CMON'daki tüm hisselerin FINAL_THG ortalaması
- **KUME_PREM**: Hisse FINAL_THG - KUME_ORT

### 🔴 **SHORT Hisseler için**
- **KUME_ORT**: Aynı CMON'daki tüm hisselerin SHORT_FINAL ortalaması
- **KUME_PREM**: KUME_ORT - Hisse SHORT_FINAL

## 📋 **Çıkış Dosyası Kolonları**

### 🔹 **Temel Bilgiler**
- `DOSYA`: Kaynak CSV dosyası
- `PREF_IBKR`: Hisse sembolü
- `FINAL_THG`: LONG skor
- `SHORT_FINAL`: SHORT skor
- `SMI`: SMI değeri
- `CGRUP`: Grup bilgisi
- `CMON`: Şirket kodu
- `TİP`: LONG veya SHORT

### 🔹 **Hesaplanan Değerler**
- `ORTALAMA_FINAL_THG`: Dosyadaki FINAL_THG ortalaması
- `ORTALAMA_SHORT_FINAL`: Dosyadaki SHORT_FINAL ortalaması
- `LONG_KURAL`: Uygulanan LONG kuralı
- `SHORT_KURAL`: Uygulanan SHORT kuralı
- `KUME_ORT`: CMON bazında ortalama
- `KUME_PREM`: CMON ortalamasından fark
- `AVG_ADV`: Ortalama günlük hacim
- `RECSIZE`: Hesaplanan lot büyüklüğü

## 🔍 **Örnek Hesaplamalar**

### 📊 **CIM PRD (HELDFF - LONG)**
- **FINAL_THG**: 1,271.18
- **KUME_ORT**: 644.48 (CIM şirketi ortalaması)
- **KUME_PREM**: 626.70 (1,271.18 - 644.48)
- **AVG_ADV**: 18,794
- **RECSIZE**: (626.70 × 12 + 18,794/25) / 4 = 2,100
- **Sınır**: min(2,100, 18,794/4) = 2,100

### 📊 **CUBB (NOTBESMATURLU - SHORT)**
- **SHORT_FINAL**: 395.95
- **KUME_ORT**: 1,660.39 (CUBI şirketi ortalaması)
- **KUME_PREM**: 1,264.44 (1,660.39 - 395.95)
- **AVG_ADV**: 1,927
- **RECSIZE**: (1,264.44 × 8 + 1,927/25) / 4 = 2,500
- **Sınır**: min(2,500, 1,927/6) = 300

## ⚠️ **Önemli Notlar**

1. **CMON Sınırlaması**: Aynı şirketten çok fazla hisse seçilmesini önler
2. **CGRUP Sınırlaması**: Belirli gruplarda aşırı yoğunlaşmayı engeller
3. **RECSIZE Sınırlaması**: AVG_ADV'ye göre gerçekçi lot büyüklükleri sağlar
4. **HELDFF Özel Kuralları**: Bu grup için daha agresif RECSIZE hesaplaması
5. **100'lük Yuvarlama**: Tüm RECSIZE değerleri pratik lot büyüklüklerine yuvarlanır

## 🔧 **Teknik Detaylar**

### 📊 **Veri İşleme Sırası**
1. Dosya okuma ve validasyon
2. Ortalama değerlerin hesaplanması
3. Kriterlere uygun hisselerin belirlenmesi
4. CMON ve CGRUP sınırlamalarının uygulanması
5. KUME_ORT ve KUME_PREM hesaplanması
6. RECSIZE hesaplanması ve sınırlamalar
7. Sonuçların CSV dosyalarına yazılması

### 🐍 **Kullanılan Python Kütüphaneleri**
- `pandas`: Veri manipülasyonu
- `numpy`: Matematiksel işlemler
- `glob`: Dosya bulma
- `os`: Dosya yolu işlemleri
- `math`: Matematiksel fonksiyonlar

## 📝 **Son Güncellemeler**

### 🔄 **Son Değişiklikler**
- HELDSOLIDBIG: Top 30% + 1.45x → Top 25% + 1.5x
- HELDKUPONLU: Top 30% + 1.35x → Top 35% + 1.3x
- HELDDEZNFF: Top 20% + 1.45x → Top 25% + 1.4x
- HIGHMATUR: Top 30% + 1.4x → Top 35% + 1.35x
- HELDFF: Özel RECSIZE kuralları (KUME_PREM×12, AVG_ADV/4)
- CMON limit: /2.5 → /1.6
- RECSIZE formülü: (KUME_PREM×8 + AVG_ADV/25)/4
- 100'lük yuvarlama ve AVG_ADV/6 sınırlaması

Bu README dosyası, `ntumcsvport.py` scriptinin tüm özelliklerini, kurallarını ve mantığını detaylı bir şekilde açıklar. Yeni geliştiriciler bu dosyayı inceleyerek scriptin nasıl çalıştığını kolayca anlayabilir.
