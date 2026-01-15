# BACKTEST KILAVUZU - 2 Yıllık Geriye Dönük Test

## 📋 Genel Bakış

Bu backtest sistemi, sizin LONG/SHORT seçim sisteminizin geçmiş performansını test eder. 1 milyon dolarlık bir portföyde %70 LONG ve %30 SHORT pozisyonlarla 2 yıllık geriye dönük simülasyon yapar.

## 🎯 Backtest Nasıl Çalışır?

### 1. **Veri Toplama**
- Geçmiş 2 yıl boyunca her rebalance tarihinde (aylık/haftalık) hangi hisselerin LONG/SHORT olduğunu belirler
- IBKR'den geçmiş fiyat verilerini çeker
- Her pozisyonun giriş ve çıkış fiyatlarını kaydeder

### 2. **Portföy Simülasyonu**
- **Başlangıç Sermayesi**: $1,000,000
- **LONG Dağılımı**: %70 ($700,000)
- **SHORT Dağılımı**: %30 ($300,000)
- Her rebalance tarihinde pozisyonlar yeniden dengelenir

### 3. **Maliyetler**
- **Transaction Cost**: %0.1 (giriş ve çıkış)
- **Slippage**: %0.05 (giriş ve çıkış)
- **Short Margin Cost**: %5 yıllık (SHORT pozisyonlar için)

### 4. **Performans Hesaplama**
- Her trade'in PnL'i hesaplanır
- Portföy değeri zaman içinde takip edilir
- Detaylı istatistikler oluşturulur

## 🚀 Kullanım

### Adım 1: Gerekli Dosyaları Hazırlayın

Backtest'i çalıştırmadan önce şu dosyaların mevcut olması gerekir:

```bash
# LONG ve SHORT hisseleri seçin
python ntumcsvport.py

# Bu komut şu dosyaları oluşturur:
# - tumcsvlong.csv
# - tumcsvshort.csv
```

### Adım 2: Backtest Parametrelerini Ayarlayın

`backtest_portfolio.py` dosyasının başındaki parametreleri düzenleyin:

```python
INITIAL_CAPITAL = 1_000_000  # Başlangıç sermayesi
LONG_PERCENTAGE = 0.70       # %70 LONG
SHORT_PERCENTAGE = 0.30      # %30 SHORT
BACKTEST_YEARS = 2           # 2 yıl geriye dönük
REBALANCE_FREQUENCY = 'monthly'  # 'daily', 'weekly', 'monthly', 'quarterly'
TRANSACTION_COST = 0.001     # %0.1 işlem maliyeti
SHORT_MARGIN_COST = 0.05     # %5 yıllık short margin maliyeti
SLIPPAGE = 0.0005           # %0.05 slippage
```

### Adım 3: IBKR Bağlantısını Kontrol Edin

IBKR TWS veya Gateway'in çalıştığından emin olun:
- TWS: Port 7496
- Gateway: Port 4001

### Adım 4: Backtest'i Çalıştırın

```bash
python backtest_portfolio.py
```

## 📊 Çıktılar

Backtest tamamlandığında şu dosyalar oluşturulur:

### 1. **backtest_trades.csv**
Her trade'in detaylı bilgileri:
- Symbol
- Type (LONG/SHORT)
- Entry/Exit tarihleri ve fiyatları
- PnL ve getiri yüzdesi
- Transaction costs, slippage, margin costs

### 2. **backtest_portfolio_history.csv**
Portföy değerinin zaman içindeki değişimi:
- Tarih
- Portföy değeri
- LONG ve SHORT PnL'leri
- Toplam getiri yüzdesi

### 3. **backtest_results.png**
Görsel grafikler:
- Portföy değeri zaman serisi
- Getiri yüzdesi grafiği
- LONG vs SHORT performans karşılaştırması
- Aylık getiri dağılımı

### 4. **Konsol Çıktısı**
Detaylı performans raporu:
- Genel performans metrikleri
- Trade istatistikleri
- Win rate'ler
- En iyi ve en kötü trades
- Sharpe ratio

## 📈 Performans Metrikleri

Backtest sonuçlarında şu metrikler hesaplanır:

### Genel Metrikler
- **Toplam Getiri**: Başlangıç sermayesinden final sermayesine kadar olan değişim
- **Yıllık Getiri**: Yıllık bazda getiri oranı
- **Maksimum Drawdown**: En yüksek noktadan en düşük noktaya kadar olan düşüş

### Trade Metrikleri
- **Win Rate**: Kazanan trade'lerin yüzdesi
- **Ortalama Getiri**: Trade başına ortalama getiri
- **En İyi/Kötü Trades**: En yüksek ve en düşük performanslı trades

### Risk Metrikleri
- **Sharpe Ratio**: Risk ayarlı getiri oranı
- **Volatilite**: Getiri değişkenliği

## ⚠️ Önemli Notlar

### 1. **Geçmiş Seçimler**
Mevcut script, geçmiş tarihlerde hangi hisselerin seçileceğini tam olarak bilmiyor. İki yaklaşım var:

**Yaklaşım A: Mevcut Seçimleri Kullan**
- Şu anki LONG/SHORT seçimlerini geçmiş 2 yıl boyunca tutar
- Daha basit ama gerçekçi değil

**Yaklaşım B: Geçmiş Tarihlerde Yeniden Seçim**
- Her rebalance tarihinde sistemin nasıl çalışacağını simüle eder
- Daha gerçekçi ama daha karmaşık

### 2. **Veri Eksiklikleri**
- Bazı hisseler için geçmiş fiyat verileri bulunamayabilir
- Bu durumda o hisse atlanır ve portföy değeri buna göre ayarlanır

### 3. **Maliyetler**
Backtest'te şu maliyetler dahil edilir:
- Transaction costs (giriş ve çıkış)
- Slippage (piyasa etkisi)
- Short margin costs (SHORT pozisyonlar için)

### 4. **Rebalance Sıklığı**
- **Monthly**: Her ay yeniden dengeleme (önerilen)
- **Weekly**: Her hafta yeniden dengeleme (daha fazla işlem maliyeti)
- **Quarterly**: Her çeyrek yeniden dengeleme (daha az işlem maliyeti)

## 🔧 Gelişmiş Kullanım

### Geçmiş Tarihlerde Yeniden Seçim Yapmak

Daha gerçekçi bir backtest için, her rebalance tarihinde sistemin nasıl çalışacağını simüle etmek gerekir. Bunun için:

1. Her rebalance tarihinde geçmiş verilerle sistemin çalıştırılması
2. O tarihteki LONG/SHORT seçimlerinin yapılması
3. Bu seçimlerle portföyün güncellenmesi

Bu yaklaşım için `backtest_with_rebalancing.py` gibi ayrı bir script gerekir.

### Benchmark Karşılaştırması

Backtest sonuçlarını benchmark'larla karşılaştırmak için:

```python
# SPY (S&P 500) ile karşılaştırma
spy_prices = engine.get_historical_prices('SPY', start_date, end_date)
spy_return = (spy_prices['close'].iloc[-1] / spy_prices['close'].iloc[0] - 1) * 100
portfolio_return = ((final_capital / INITIAL_CAPITAL) - 1) * 100
alpha = portfolio_return - spy_return
```

## 📝 Örnek Çıktı

```
================================================================================
📊 BACKTEST RAPORU
================================================================================

💰 GENEL PERFORMANS:
   Başlangıç Sermayesi: $1,000,000.00
   Final Sermaye: $1,250,000.00
   Toplam Getiri: $250,000.00 (25.00%)
   Yıllık Getiri: 11.80%

📈 TRADE İSTATİSTİKLERİ:
   Toplam Trade: 240
   LONG Trades: 168
   SHORT Trades: 72

🟢 LONG PERFORMANSI:
   Win Rate: 58.33%
   Ortalama Getiri: 2.15%
   Toplam PnL: $180,000.00

🔴 SHORT PERFORMANSI:
   Win Rate: 52.78%
   Ortalama Getiri: 1.85%
   Toplam PnL: $70,000.00

🏆 EN İYİ 5 TRADE:
   AAPL (LONG): $15,000.00 (15.00%)
   MSFT (LONG): $12,500.00 (12.50%)
   ...
```

## 🎓 Sonuçları Yorumlama

### İyi Performans Göstergeleri
- ✅ Yıllık getiri > %10
- ✅ Win rate > %55
- ✅ Sharpe ratio > 1.0
- ✅ Maksimum drawdown < %20

### Dikkat Edilmesi Gerekenler
- ⚠️ Yüksek volatilite
- ⚠️ Düşük win rate (< %50)
- ⚠️ Büyük drawdown'lar
- ⚠️ SHORT pozisyonların sürekli kaybetmesi

## 🔄 İyileştirme Önerileri

1. **Farklı Rebalance Sıklıkları Test Edin**
   - Monthly, weekly, quarterly karşılaştırması yapın

2. **Farklı LONG/SHORT Oranları Test Edin**
   - %60/40, %80/20 gibi farklı dağılımlar deneyin

3. **Risk Yönetimi Ekleyin**
   - Stop-loss seviyeleri
   - Pozisyon büyüklüğü limitleri

4. **Farklı Dönemler Test Edin**
   - Bull market dönemleri
   - Bear market dönemleri
   - Volatil dönemler

## 📞 Sorun Giderme

### IBKR Bağlantı Sorunları
- TWS veya Gateway'in çalıştığından emin olun
- Port numaralarını kontrol edin (7496 veya 4001)
- Firewall ayarlarını kontrol edin

### Veri Eksiklikleri
- Bazı hisseler için fiyat verisi bulunamazsa atlanır
- Bu durumda portföy değeri buna göre ayarlanır

### Performans Sorunları
- Çok fazla hisse varsa backtest uzun sürebilir
- Rate limiting nedeniyle her hisse sonrası bekleme yapılır

## 📚 Ek Kaynaklar

- IBKR API Dokümantasyonu
- Backtest metodolojisi hakkında kitaplar
- Risk yönetimi best practices

---

**Not**: Bu backtest geçmiş performansı gösterir ve gelecek performansı garanti etmez. Yatırım kararları vermeden önce profesyonel danışmanlık alın.










