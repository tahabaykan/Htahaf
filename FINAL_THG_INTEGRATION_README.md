# FINAL THG Lot Dağıtıcı - JANALL Entegrasyonu

## Genel Bakış
Bu özellik, JANALL uygulamasının Port Adjuster'ına entegre edilmiş FINAL THG tabanlı lot dağılımı sistemidir. Port Adjuster'da ayarlanan grup ağırlıklarına göre, her gruptaki hisselerin FINAL THG değerlerine dayalı olarak lot dağılımı yapar.

## Nasıl Kullanılır

### 1. Port Adjuster'da Ayarları Yapın
- JANALL uygulamasını açın
- "Port Adjuster" butonuna tıklayın
- 1. Step'te genel ayarları yapın:
  - Total Exposure (USD)
  - Avg Pref Price (USD)
  - Long/Short Ratio
- 2. Step'te grup ağırlıklarını ayarlayın:
  - Long Groups tab'ında her grup için yüzde belirleyin
  - Toplam oranın %100 olmasına dikkat edin
- "exposureadjuster.csv'ye Kaydet" butonuna tıklayın

### 2. FINAL THG Lot Dağılımını Hesaplayın
- Port Adjuster'da "3. Step - FINAL THG" butonuna tıklayın
- Yeni pencere açılacak
- "Grup Ağırlıklarını Yükle" butonuna tıklayın
- Port Adjuster'dan grup ağırlıkları ve lot hakları yüklenecek
- "Lot Dağılımını Hesapla" butonuna tıklayın

## Özellikler

### FINAL THG Tabanlı Dağılım
- Her grupta sadece TOP 5 en yüksek FINAL THG skoruna sahip hisseler seçilir
- Alpha parametresi ile dağılım hassasiyeti ayarlanabilir (2, 3, 4, 5)
- Lot sayıları 100'lük sayılara yuvarlanır

### MAXALW Limiti
- Her hisse için MAXALW değerinin 2 katı limit uygulanır
- Hesaplanan lot bu limiti aşarsa, lot miktarı limite düşürülür
- Kalan lot hakkı kullanılmaz (verimlilik düşebilir)

### SMI ve MAXALW Kolonları
- Sonuçlarda SMI ve MAXALW değerleri gösterilir
- Bu değerler CSV dosyalarından okunur
- Eğer kolon yoksa "N/A" gösterilir

## Çıktı Formatı

### Sol Panel - Grup Ağırlıkları
- **Grup**: Grup adı
- **Ağırlık (%)**: Port Adjuster'dan gelen yüzde
- **Lot Hakları**: O gruba ayrılan toplam lot miktarı

### Sağ Panel - Lot Dağılımı Sonuçları
- **Grup**: Hisse grubu
- **Sembol**: Hisse sembolü (PREF IBKR)
- **FINAL THG**: FINAL THG skoru
- **SMI**: SMI değeri
- **MAXALW**: MAXALW değeri
- **Hesaplanan Lot**: FINAL THG'ye göre hesaplanan lot
- **Final Lot**: MAXALW limiti uygulandıktan sonraki lot
- **Durum**: Lot dağılım durumu

### Özet Bilgiler
- Toplam hesaplanan lot
- Toplam final lot
- Verimlilik yüzdesi
- Kullanılmayan lot miktarı

## Dosya Gereksinimleri

### Giriş Dosyaları
- `exposureadjuster.csv`: Port Adjuster ayarları
- `ssfinek*.csv`: Her grup için FINAL THG verileri

### Çıkış Dosyaları
- `final_thg_lot_distribution.csv`: Hesaplama sonuçları

## Teknik Detaylar

### Lot Dağılım Formülü
```python
relative_scores = (final_thg_arr / max_score) ** alpha
raw_lot_alloc = relative_scores / relative_scores.sum() * total_lot
```

### Alpha Değerleri
- **Alpha=2**: Varsayılan hassasiyet
- **Alpha=3**: Orta hassasiyet (varsayılan)
- **Alpha=4**: Yüksek hassasiyet
- **Alpha=5**: Çok yüksek hassasiyet

### MAXALW Limit Kontrolü
```python
maxalw_limit = float(maxalw_value) * 2
if calculated_lots > maxalw_limit:
    final_lots = int(maxalw_limit)
```

## Sorun Giderme

### Grup Ağırlıkları Yüklenmiyor
- `exposureadjuster.csv` dosyasının mevcut olduğundan emin olun
- Port Adjuster'da ayarları kaydettiğinizden emin olun

### CSV Dosyaları Bulunamıyor
- `ssfinek*.csv` dosyalarının ana dizinde olduğundan emin olun
- Dosya adlarının doğru formatta olduğundan emin olun

### FINAL THG Verisi Bulunamıyor
- CSV dosyalarında `FINAL_THG` kolonunun mevcut olduğundan emin olun
- `PREF IBKR` kolonunun mevcut olduğundan emin olun

## Örnek Kullanım Senaryosu

1. Port Adjuster'da HELDFF grubuna %40 ağırlık verin
2. 3. Step'e geçin ve grup ağırlıklarını yükleyin
3. HELDFF grubu için 16,000 lot hakkı görünecek (40,000 * 0.4)
4. Lot dağılımını hesaplayın
5. TOP 5 HELDFF hissesi FINAL THG değerlerine göre lot alacak
6. MAXALW limiti varsa uygulanacak
7. Sonuçları CSV olarak kaydedin

## Güncellemeler

### v1.0 (Mevcut)
- Temel FINAL THG lot dağılımı
- MAXALW limit kontrolü
- SMI ve MAXALW kolonları
- 100'lük lot yuvarlama
- Alpha hassasiyet ayarı

### Gelecek Özellikler
- Dinamik alpha optimizasyonu
- Risk bazlı lot dağılımı
- Gerçek zamanlı veri güncelleme
- Çoklu portföy desteği






















