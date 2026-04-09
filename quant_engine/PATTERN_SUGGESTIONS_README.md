# Pattern Suggestions — PATADD Engine Güncelleme Rehberi

## Genel Bakış

PATADD engine, ex-div (temettü) tarihlerindeki fiyat pattern'lerini kullanarak
otomatik LONG/SHORT pozisyon açma kararları verir. İki katmandan oluşur:

1. **Pipeline (Offline)**: Geçmiş verileri analiz eder → `v5_summary.csv` üretir
2. **Engine (Online)**: Her XNL döngüsünde `v5_summary.csv`'den bugünün sinyallerini hesaplar

## Dosya Yapısı

```
quant_engine/
├── run_pipeline_v51.py                   # ← BU DOSYA ÇALIŞTIRILIR (güncelleme için)
├── output/exdiv_v5/
│   ├── v5_summary.csv                    # Pipeline sonuçları (pattern skorları)
│   └── v5_exdiv_dates.csv                # Tüm projekte edilen ex-div tarihleri
├── app/
│   ├── api/pattern_suggestions_routes.py # FastAPI endpoint + signal builder
│   ├── psfalgo/patadd_engine.py          # PATADD engine (XNL tarafından çağrılır)
│   └── agent/exdiv_pipeline.py           # Pattern hesaplama core fonksiyonları
├── full_pipeline_results_v51.txt         # Detaylı pipeline log
└── pipeline_v51_log.txt                  # Pipeline çalıştırma logu
```

## Ne Zaman Güncelleme Gerekir?

| Durum | Güncelleme? | Komut |
|-------|-------------|-------|
| Günlük trade sinyalleri | ❌ HAYIR — otomatik çalışır | — |
| Yeni ex-div verisi (janalldata.csv güncellendi) | ✅ EVET | `python run_pipeline_v51.py` |
| Yeni hisse eklendi | ✅ EVET | `python run_pipeline_v51.py` |
| Pattern model iyileştirmesi | ✅ EVET | `python run_pipeline_v51.py` |
| 3-6 ayda bir (rutin bakım) | ⚠️ ÖNERİLİR | `python run_pipeline_v51.py` |

## Güncelleme Nasıl Yapılır?

### Adım 1: Pipeline'ı Çalıştır
```bash
cd C:\StockTracker\quant_engine
python run_pipeline_v51.py
```

Bu komut:
1. `janalldata.csv`'den baz ex-div tarihlerini yükler
2. 3'er ay ekleyerek tüm ex-div tarihlerini projekte eder (±20 çeyrek)
3. Her ticker için fiyat pattern'lerini hesaplar (entry/exit günleri, return, sharpe, win rate)
4. Sonuçları `output/exdiv_v5/v5_summary.csv`'ye kaydeder

**Çalışma süresi:** ~2-5 dakika (tüm hisseler için)

### Adım 2: Doğrulama
```bash
# Pipeline sonuçlarını kontrol et
type full_pipeline_results_v51.txt | more

# v5_summary.csv kontrol et
python -c "import pandas as pd; df = pd.read_csv('output/exdiv_v5/v5_summary.csv'); print(f'Toplam: {len(df)} hisse'); print(df[['ticker','best_long_sharpe','best_short_sharpe']].head(10))"
```

### Adım 3: Yeniden başlatma gerekmez!
Quant Engine (`run_daily_n.py`) çalışırken pipeline güncellenirse,
PATADD engine bir sonraki döngüde yeni `v5_summary.csv`'yi otomatik okur.
Yeniden başlatma gerekmez.

## Otomatik Çalışma Mantığı

Her XNL döngüsünde (her ~2 saniye):

```
PATADD Engine
    ↓
_fetch_active_signals()
    ↓
_build_suggestions(today)
    ↓
v5_summary.csv'yi okur
    ↓
janalldata.csv'den baz ex-div tarihlerini alır
    ↓
_next_exdiv(): Baz tarihten 3'er ay ekleyerek bugünkü ex-div'i bulur
    ↓
Entry penceresi kontrolü (entry_date ±1 gün)
    ↓
BUY_NOW veya SHORT_NOW sinyal üretir
    ↓
XNL Engine → MinMax validation → Emir gönder
```

### Süre Limiti
- `_next_exdiv()` **30 çeyrek (7.5 yıl)** ileriye kadar projekte eder
- Pipeline baz tarihinden itibaren **±20 çeyrek** analiz yapar
- **2033'e kadar** sorunsuz çalışır (şu anki ayarlarla)

### DRIFT_TOLERANCE
- Ex-div tarihi ±4 gün kayabilir (şirket takvim değişikliği)
- Bu tolerans `_next_exdiv()` ve pipeline'da tanımlı

## Signal Filtreleri

`v5_summary.csv`'den sinyal seçimi kriterleri:

### LONG Entry
- `best_long_sharpe > 0.3`
- `best_long_pval <= 0.15`
- Entry penceresi: `entry_date ± 1 gün` = BUY_NOW
- Geçmiş entry ama exit'e 2+ gün var = hâlâ BUY_NOW

### SHORT Entry
- `best_short_sharpe > 0.3`
- `best_short_pval <= 0.15`
- Entry penceresi: `entry_date ± 1 gün` = SHORT_NOW

### Conflict Resolution
- Aynı ticker hem LONG hem SHORT sinyali verirse, yüksek skorlu kazanır

## Bağımlılıklar

- `janalldata.csv` → Baz ex-div tarihleri + `PREF IBKR` symbol mapping
- `ekheld*.csv` dosyaları → Fallback ex-div tarihleri
- Fiyat verisi dosyaları → `load_stock_df()` ile yüklenen günlük OHLC
- `quant_engine/app/agent/exdiv_pipeline.py` → Core pattern hesaplama

## Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| "Pipeline sonuclari yok" | `python run_pipeline_v51.py` çalıştır |
| PATADD sinyal üretmiyor | `v5_summary.csv` dosyasını kontrol et — boş mu? |
| Yanlış ex-div tarihi | `janalldata.csv`'deki `EX-DIV DATE` sütununu güncelle |
| Hisse pattern'i değişti | Pipeline'ı yeniden çalıştır |
| 7.5 yıl sonra çalışmaz | `_next_exdiv`'deki `range(1, 30)`'u artır |
