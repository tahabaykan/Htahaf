# BACKTEST - PORT ADJUSTER UYUMLU SİSTEM

## 🎯 Genel Bakış

Bu backtest sistemi, **janall Port Adjuster** mantığına uygun şekilde çalışır ve gerçek portföy dağılımını simüle eder.

## 📊 Port Adjuster Ayarları

### Temel Parametreler:
- **Total Exposure**: $1,000,000
- **Long Ratio**: %85 ($850,000)
- **Short Ratio**: %15 ($150,000)
- **Avg Pref Price**: $25
- **Hedef Hisse Sayısı**: 30-40 hisse

### RECSIZE Hesaplama Mantığı:

RECSIZE, her hisse için önerilen pozisyon büyüklüğüdür (lot cinsinden).

**Formül**:
```
RECSIZE = round((KUME_PREM * 8 + AVG_ADV / 25) / 4 / 100) * 100
```

**HELDFF için özel**:
```
RECSIZE = round((KUME_PREM * 12 + AVG_ADV / 25) / 4 / 100) * 100
```

**Sınırlamalar**:
- Normal gruplar: `max_recsize = AVG_ADV / 6`
- HELDFF: `max_recsize = AVG_ADV / 4`
- RECSIZE = `min(recsize, max_recsize)`

**KUME_PREM Hesaplama**:
- LONG için: `KUME_PREM = Final FB - ORTALAMA_FINAL_FB`
- SHORT için: `KUME_PREM = ORTALAMA_FINAL_SFS - Final SFS`

## 🔄 Backtest'te RECSIZE Kullanımı

### Pozisyon Büyüklüğü Hesaplama:

1. **RECSIZE Varsa**:
   - Her hisse için RECSIZE oranı hesaplanır
   - Portföy sermayesi (LONG veya SHORT) RECSIZE oranlarına göre dağıtılır
   - Formül: `position_size = capital * (recsize / total_recsize)`

2. **RECSIZE Yoksa**:
   - Sermaye eşit olarak dağıtılır
   - Formül: `position_size = capital / num_stocks`

### Örnek Hesaplama:

**LONG Portföy**: $850,000
**3 LONG Hisse**:
- Hisse A: RECSIZE = 200 lot
- Hisse B: RECSIZE = 300 lot
- Hisse C: RECSIZE = 500 lot
**Toplam RECSIZE**: 1000 lot

**Dağılım**:
- Hisse A: $850,000 * (200/1000) = $170,000
- Hisse B: $850,000 * (300/1000) = $255,000
- Hisse C: $850,000 * (500/1000) = $425,000

## 📈 Backtest Parametreleri

```python
INITIAL_CAPITAL = 1_000_000      # 1 milyon dolar
LONG_PERCENTAGE = 0.85           # %85 LONG
SHORT_PERCENTAGE = 0.15          # %15 SHORT
AVG_PREF_PRICE = 25.0            # Ortalama preferred stock fiyatı
MIN_STOCKS = 30                  # Minimum hisse sayısı
MAX_STOCKS = 40                  # Maksimum hisse sayısı (hedef)
REBALANCE_FREQUENCY = 'monthly'  # Aylık yeniden dengeleme
TRANSACTION_COST = 0.001         # %0.1 işlem maliyeti
SHORT_MARGIN_COST = 0.05         # %5 yıllık short margin maliyeti
SLIPPAGE = 0.0005               # %0.05 slippage
```

## 🚀 Kullanım

### Adım 1: LONG/SHORT Seçimlerini Yapın

```bash
python ntumcsvport.py
```

Bu komut şu dosyaları oluşturur:
- `tumcsvlong.csv`: LONG hisseler (RECSIZE dahil)
- `tumcsvshort.csv`: SHORT hisseler (RECSIZE dahil)

### Adım 2: Backtest'i Çalıştırın

```bash
python backtest_portfolio.py
```

## 📊 Backtest Nasıl Çalışır?

### 1. Her Rebalance Tarihinde:

1. **Mevcut LONG/SHORT seçimlerini kullanır**
   - `tumcsvlong.csv` ve `tumcsvshort.csv` dosyalarından okur
   - Her hisse için RECSIZE değerini kullanır

2. **Portföy Dağılımını Hesaplar**:
   - LONG: $850,000 (veya mevcut sermayenin %85'i)
   - SHORT: $150,000 (veya mevcut sermayenin %15'i)
   - RECSIZE'lara göre her hisseye ne kadar para ayrılacağını belirler

3. **Geçmiş Fiyat Verilerini Çeker**:
   - IBKR'den giriş fiyatını çeker (rebalance tarihinde)
   - IBKR'den çıkış fiyatını çeker (bir sonraki rebalance tarihinde)

4. **Trade'leri Simüle Eder**:
   - Her trade için PnL hesaplar
   - Transaction costs, slippage, margin costs ekler
   - Net PnL'i hesaplar

5. **Portföy Değerini Günceller**:
   - Tüm trade'lerin net PnL'ini toplar
   - Portföy değerini günceller
   - Bir sonraki rebalance için hazırlar

### 2. Sonuçlar:

Backtest tamamlandığında şu dosyalar oluşturulur:

- **`backtest_trades.csv`**: Her trade'in detayları
  - Symbol, type, entry/exit tarihleri ve fiyatları
  - Position size, shares, PnL, return %
  - Transaction costs, slippage, margin costs
  - Net PnL

- **`backtest_portfolio_history.csv`**: Portföy geçmişi
  - Tarih, portföy değeri
  - LONG ve SHORT PnL'leri
  - Toplam getiri yüzdesi

- **`backtest_results.png`**: Görsel grafikler
  - Portföy değeri zaman serisi
  - Getiri yüzdesi grafiği
  - LONG vs SHORT performans karşılaştırması
  - Aylık getiri dağılımı

## 📈 Performans Metrikleri

### Genel Metrikler:
- **Toplam Getiri**: Başlangıç sermayesinden final sermayesine kadar olan değişim
- **Yıllık Getiri**: Yıllık bazda getiri oranı
- **Maksimum Drawdown**: En yüksek noktadan en düşük noktaya kadar olan düşüş

### Trade Metrikleri:
- **Win Rate**: Kazanan trade'lerin yüzdesi
- **Ortalama Getiri**: Trade başına ortalama getiri
- **En İyi/Kötü Trades**: En yüksek ve en düşük performanslı trades

### Risk Metrikleri:
- **Sharpe Ratio**: Risk ayarlı getiri oranı
- **Volatilite**: Getiri değişkenliği

## ⚠️ Önemli Notlar

### 1. RECSIZE Kullanımı:
- RECSIZE varsa, portföy RECSIZE oranlarına göre dağıtılır
- RECSIZE yoksa, portföy eşit olarak dağıtılır
- RECSIZE lot cinsinden, pozisyon büyüklüğü dolar cinsinden hesaplanır

### 2. Portföy Dağılımı:
- LONG: %85 (Port Adjuster'dan)
- SHORT: %15 (Port Adjuster'dan)
- Hedef: 30-40 hisse toplam

### 3. Geçmiş Seçimler:
- Mevcut script, şu anki LONG/SHORT seçimlerini geçmiş 2 yıl boyunca tutar
- Daha gerçekçi sonuçlar için geçmiş tarihlerde sistemin yeniden çalıştırılması gerekir

### 4. Veri Eksiklikleri:
- Bazı hisseler için geçmiş fiyat verileri bulunamayabilir
- Bu durumda o hisse atlanır ve portföy değeri buna göre ayarlanır

## 🔧 RECSIZE Hesaplama Detayları

### KUME_PREM Hesaplama:

**LONG için**:
```python
KUME_PREM = Final FB - ORTALAMA_FINAL_FB
```

**SHORT için**:
```python
KUME_PREM = ORTALAMA_FINAL_SFS - Final SFS
```

### RECSIZE Hesaplama:

**Normal Gruplar**:
```python
recsize = round((KUME_PREM * 8 + AVG_ADV / 25) / 4 / 100) * 100
max_recsize = round(AVG_ADV / 6 / 100) * 100
recsize = min(recsize, max_recsize)
```

**HELDFF Grubu**:
```python
recsize = round((KUME_PREM * 12 + AVG_ADV / 25) / 4 / 100) * 100
max_recsize = round(AVG_ADV / 4 / 100) * 100
recsize = min(recsize, max_recsize)
```

### Pozisyon Büyüklüğü Hesaplama:

**RECSIZE Varsa**:
```python
total_recsize = sum(all_recsizes)
recsize_ratio = individual_recsize / total_recsize
position_size = capital * recsize_ratio
```

**RECSIZE Yoksa**:
```python
position_size = capital / num_stocks
```

## 📝 Örnek Backtest Çıktısı

```
================================================================================
🚀 Backtest başlatılıyor...
================================================================================
📅 Tarih aralığı: 2022-01-01 - 2024-01-01
💰 Başlangıç sermayesi: $1,000,000.00
📊 Dağılım: %85 LONG ($850,000.00), %15 SHORT ($150,000.00)
📈 Hedef hisse sayısı: 30-40 hisse
🔄 Rebalance sıklığı: monthly
💸 İşlem maliyeti: 0.10%
📉 Short margin maliyeti: 5.00% yıllık
💡 Pozisyon büyüklüğü: RECSIZE kullanılarak hesaplanacak

🔄 Rebalance tarihleri: 24 adet

============================================================
📅 Rebalance #1/24: 2022-01-01
============================================================
💰 Mevcut portföy değeri: $1,000,000.00
📊 LONG pozisyonları: 25 hisse, $850,000.00 toplam, RECSIZE toplam: 25000 lot
📊 SHORT pozisyonları: 8 hisse, $150,000.00 toplam, RECSIZE toplam: 5000 lot
📊 Toplam hisse sayısı: 33 (Hedef: 30-40)

🟢 LONG pozisyonları işleniyor (25 hisse)...
  ✅ AAPL: $150.00 → $155.00, Pozisyon: $34,000.00, RECSIZE: 200 lot, PnL: $1,133.33 (3.33%)
  ✅ MSFT: $300.00 → $310.00, Pozisyon: $51,000.00, RECSIZE: 300 lot, PnL: $1,700.00 (3.33%)
  ...

🔴 SHORT pozisyonları işleniyor (8 hisse)...
  ✅ TSLA: $200.00 → $190.00, Pozisyon: $18,750.00, RECSIZE: 100 lot, PnL: $937.50 (5.00%)
  ...

📊 Rebalance Özeti:
   🟢 LONG: 25 başarılı, 0 başarısız, PnL: $15,000.00
   🔴 SHORT: 8 başarılı, 0 başarısız, PnL: $2,000.00
   📊 Toplam aktif pozisyon: 33 hisse
   💰 Yeni portföy değeri: $1,017,000.00
   📈 Toplam getiri: 1.70%
   💵 Bu dönem getirisi: $17,000.00 (1.70%)
```

## 🎓 Sonuçları Yorumlama

### İyi Performans Göstergeleri:
- ✅ Yıllık getiri > %10
- ✅ Win rate > %55
- ✅ Sharpe ratio > 1.0
- ✅ Maksimum drawdown < %20
- ✅ LONG ve SHORT dengeli performans

### Dikkat Edilmesi Gerekenler:
- ⚠️ Yüksek volatilite
- ⚠️ Düşük win rate (< %50)
- ⚠️ Büyük drawdown'lar
- ⚠️ SHORT pozisyonların sürekli kaybetmesi
- ⚠️ RECSIZE dağılımının çok dengesiz olması

## 🔄 İyileştirme Önerileri

1. **Farklı LONG/SHORT Oranları Test Edin**
   - %80/20, %90/10 gibi farklı dağılımlar deneyin

2. **RECSIZE Ağırlıklarını Ayarlayın**
   - RECSIZE hesaplama formülündeki katsayıları değiştirin
   - AVG_ADV ağırlığını artırın/azaltın

3. **Minimum/Maksimum Pozisyon Büyüklükleri**
   - Çok küçük pozisyonları filtreleyin
   - Çok büyük pozisyonları sınırlayın

4. **Risk Yönetimi Ekleyin**
   - Stop-loss seviyeleri
   - Pozisyon büyüklüğü limitleri
   - Maksimum drawdown limitleri

---

**Not**: Bu backtest geçmiş performansı gösterir ve gelecek performansı garanti etmez. Yatırım kararları vermeden önce profesyonel danışmanlık alın.



