# Final jdata Sekmesi - Kullanım Kılavuzu

## 🎯 Ne İşe Yarar?

"Final jdata" sekmesi, her unique hisse için ağırlıklı ortalama hesaplamalarını yapar:

1. **Average Stock Cost** - Ağırlıklı ortalama maliyet
2. **Average Fill Time** - Ağırlıklı ortalama fill zamanı  
3. **Average Benchmark Cost** - Ağırlıklı ortalama benchmark maliyeti

## 📊 Nasıl Çalışır?

### Örnek Senaryo:
- **24.08.2025 saat 20:00**: F PRC hissesinden 1000 lot @ $21.80 (Benchmark: $28.20)
- **25.08.2025 saat 18:00**: F PRC hissesinden 2000 lot @ $22.10 (Benchmark: $29.10)

### Hesaplama:
- **Average Cost**: (1000 × $21.80 + 2000 × $22.10) ÷ 3000 = $22.00
- **Average Benchmark**: (1000 × $28.20 + 2000 × $29.10) ÷ 3000 = $28.80
- **Average Fill Time**: Ağırlıklı ortalama zaman (2000 lot daha fazla olduğu için 25.08'e daha yakın)

## 🚀 Kullanım:

1. **jdata Analiz** penceresini aç
2. **"Final jdata"** sekmesine tıkla
3. Sistem otomatik olarak hesaplamaları yapar
4. **"Final jdata Hesapla"** butonu ile yenile
5. **"CSV Export"** butonu ile verileri dışa aktar

## 📋 Kolonlar:

| Kolon | Açıklama |
|-------|----------|
| Symbol | Hisse sembolü (PREF IBKR formatı) |
| Total Qty | Toplam lot miktarı |
| Avg Cost | Ağırlıklı ortalama maliyet |
| Avg Fill Time | Ağırlıklı ortalama fill zamanı |
| Avg Bench Cost | Ağırlıklı ortalama benchmark maliyeti |
| Current Price | Güncel hisse fiyatı |
| Current Bench | Güncel benchmark değeri |
| Total PnL | Toplam kar/zarar |
| Outperf | Benchmark'e göre outperformans |

## ⚠️ Önemli Notlar:

- **Benchmark Cost** ve **Benchmark Last** artık aynı formülleri kullanıyor
- Fill zamanındaki benchmark hesaplaması main window'daki formülleri kullanıyor
- Her unique hisse için ayrı satır oluşturuluyor
- CSV export otomatik timestamp ile kaydediliyor

## 🔧 Teknik Detaylar:

- Ağırlıklı ortalama: `Σ(qty × value) ÷ Σ(qty)`
- Zaman hesaplaması: Timestamp'ler üzerinden ağırlıklı ortalama
- Benchmark formülleri: Main window'daki `benchmark_formulas` kullanılıyor
- Fallback: Eski formüller yedek olarak mevcut
