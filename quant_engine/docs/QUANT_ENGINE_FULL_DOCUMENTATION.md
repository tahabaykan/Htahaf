# QUANT ENGINE - TAM TEKNİK DOKÜMANTASYON
## Version 2.0 - Comprehensive System Architecture

---

# İÇİNDEKİLER

1. [GENEL MİMARİ](#1-genel-mimari)
2. [EXPOSURE HESAPLAMA VE MODLAR](#2-exposure-hesaplama-ve-modlar)
3. [BEFDAY TRACKER VE POZİSYON TRİAD'I](#3-befday-tracker-ve-pozisyon-triadi)
4. [8'Lİ POZİSYON TAKSONOMİSİ](#4-8li-pozisyon-taksonomisi)
5. [GENOBS - GORT, FBTOT, SFSTOT HESAPLAMA](#5-genobs---gort-fbtot-sfstot-hesaplama)
6. [UCUZLUK/PAHALILIK SKORLAMA](#6-ucuzlukpahalilik-skorlama)
7. [QEBENCH - BENCHMARK HESAPLAMA](#7-qebench---benchmark-hesaplama)
8. [KARBOTU DECISION ENGINE](#8-karbotu-decision-engine)
9. [ADDNEWPOS DECISION ENGINE](#9-addnewpos-decision-engine)
10. [REDUCEMORE RISK ENGINE](#10-reducemore-risk-engine)
11. [LT TRIM EXECUTION ENGINE](#11-lt-trim-execution-engine)
12. [MM CHURN ENGINE](#12-mm-churn-engine)
13. [JFIN TRANSFORMER](#13-jfin-transformer)
14. [TRUTH TICKS VE VOLAV](#14-truth-ticks-ve-volav)
15. [REV ORDER VE REVNBOOK MEKANİZMASI](#15-rev-order-ve-revnbook-mekanizmasi)
16. [ORDER LIFECYCLE VE TTL](#16-order-lifecycle-ve-ttl)
17. [MENTAL MODEL V1 - INTENT MATH](#17-mental-model-v1---intent-math)
18. [DATA FABRIC - FAST/SLOW PATH](#18-data-fabric---fastslow-path)
19. [RUNALL ORCHESTRATOR](#19-runall-orchestrator)
20. [SAYISAL PARAMETRELER TAM LİSTESİ](#20-sayisal-parametreler-tam-listesi)

---

# 1. GENEL MİMARİ

## 1.1 Sistem Yapısı

Quant Engine, aşağıdaki katmanlardan oluşur:

```
┌─────────────────────────────────────────────────────────────┐
│                     RUNALL ORCHESTRATOR                      │
│        (Central Conductor - 240 saniye cycle)               │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   ANALYZERS   │    │   EXECUTIVE   │    │    SUPPORT    │
│               │    │               │    │               │
│ - Karbotu     │    │ - LT Trim     │    │ - QeBench     │
│ - AddNewPos   │    │ - MM Churn    │    │ - Port Adj    │
│ - ReduceMore  │    │ - JFIN        │    │ - Data Fabric │
│ - Greatest MM │    │               │    │ - Truth Ticks │
└───────────────┘    └───────────────┘    └───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    EXECUTION LAYER                           │
│  Intent → Decision → Proposal → Order → Execution            │
│  (Deduplication, TTL, Selective Cancel)                     │
└─────────────────────────────────────────────────────────────┘
```

## 1.2 Engine Rolleri

| Engine | Tip | Çıktı | Açıklama |
|--------|-----|-------|----------|
| **Karbotu** | Analyzer | SIGNALS + INTENTS | Makro karar ve sinyal üretici |
| **AddNewPos** | Analyzer | INTENTS | Yeni pozisyon açma |
| **ReduceMore** | Analyzer | MULTIPLIERS + INTENTS | Risk çarpanı üretici |
| **Greatest MM** | Analyzer | SIGNALS | MM fırsat tarayıcı |
| **LT Trim** | Executive | INTENTS | Long-term pozisyon azaltma |
| **MM Churn** | Executive | ORDERS | Market making emirleri |
| **JFIN** | Transformer | INTENTIONS | Deterministic lot dağıtımı |

## 1.3 Veri Akışı

```
Hammer L1 Data ───┐
                  │
Static CSV Data ──┼──▶ DataFabric ──▶ FastScoreCalculator ──▶ Engines
                  │
Redis Cache ──────┘

                        ┌─────────────────────────────┐
                        │     JanallMetricsEngine     │
                        │ (Group stats: GORT, Fbtot)  │
                        └─────────────────────────────┘
```

---

# 2. EXPOSURE HESAPLAMA VE MODLAR

## 2.1 Exposure Hesaplama Formülleri

```python
# ExposureCalculator - exposure_calculator.py

# Temel hesaplamalar
pot_total = Σ(|position_qty| × current_price)  # Toplam dolar exposure
long_lots = Σ(position_qty > 0 ? position_qty : 0)
short_lots = Σ(position_qty < 0 ? |position_qty| : 0)
net_exposure = long_lots - short_lots

# Exposure ratio
exposure_ratio = pot_total / pot_expo_limit
```

## 2.2 Exposure Thresholds (Config)

```yaml
# exposure_thresholds.csv
exposure_limit: 5,000,000      # Maksimum dolar exposure
pot_expo_limit: 6,363,600      # Portfolio exposure limiti
defensive_pct: 0.955           # %95.5 - DEFANSIF eşiği
offensive_pct: 0.927           # %92.7 - OFANSIF eşiği

# psfalgo_rules.yaml
defensive_threshold_percent: 95.5
offensive_threshold_percent: 92.7
default_exposure_limit: 1,200,000
default_avg_price: 100
pot_expo_limit: 1,400,000
```

## 2.3 Exposure Modları

| Mod | Koşul | Davranış |
|-----|-------|----------|
| **OFANSIF** | exposure_ratio < offensive_pct (92.7%) | AddNewPos AKTİF |
| **GECIS** | offensive_pct ≤ ratio < defensive_pct | Geçiş modu |
| **DEFANSIF** | exposure_ratio ≥ defensive_pct (95.5%) | Sadece azaltma |

```python
def determine_exposure_mode(self, pot_total: float, pot_max: float) -> str:
    if pot_max <= 0:
        return 'OFANSIF'
    
    ratio = pot_total / pot_max
    
    if ratio >= self.defensive_threshold:  # 0.955
        return 'DEFANSIF'
    elif ratio >= self.offensive_threshold:  # 0.927
        return 'GECIS'
    else:
        return 'OFANSIF'
```

## 2.4 Risk Rejimleri (Yeni V2)

```yaml
# psfalgo_rules.yaml - risk_regimes

soft_derisk:
  threshold_pct: 120.0           # %120'de başlar
  addnewpos_step_multiplier: 0.25  # ADDNEWPOS %25'e düşer
  
hard_derisk:
  threshold_pct: 130.0           # %130'da başlar
  cancel_risk_increasing: true   # Risk artıran emirleri iptal
  only_reduce_positions: true    # Sadece pozisyon azaltma
```

---

# 3. BEFDAY TRACKER VE POZİSYON TRİAD'I

## 3.1 Triad Kavramı

Her pozisyon için 3 kritik değer tutulur:

```
┌─────────────────────────────────────────────────────────────┐
│                     POZİSYON TRİAD'I                        │
├─────────────────────────────────────────────────────────────┤
│  BEFDAY_QTY      │  Gün başı pozisyon (sabit, kayıt anı)   │
│  CURRENT_QTY     │  Şu anki pozisyon (broker'dan)          │
│  POTENTIAL_QTY   │  Current + Open Orders (gelecek durum)  │
└─────────────────────────────────────────────────────────────┘
```

## 3.2 Befday Tracker Mantığı

```python
# befday_tracker.py

class BefDayTracker:
    """
    Günlük pozisyon snapshot'ı - Piyasa açılışında kaydedilir.
    3 farklı hesap için 3 farklı CSV:
    - befham.csv      (HAMPRO)
    - befibgun.csv    (IBKR_GUN)
    - befibped.csv    (IBKR_PED)
    """
    
    TRACK_WINDOWS = [
        ('09:10', '09:35'),  # Ana pencere
        ('09:35', '09:40'),  # Geç pencere (fallback)
    ]
    
    def track_positions(self, positions: List[Dict]) -> None:
        """
        Pozisyonları CSV'ye yaz ve JSON snapshot oluştur.
        Her pozisyon için 8'li taksonomi de belirlenir.
        """
        for pos in positions:
            # Taksonomi belirleme
            strategy = 'LT' if abs(pos['qty']) >= 400 else 'MM'
            origin = 'OV' if pos.get('overnight', True) else 'INT'
            direction = 'Long' if pos['qty'] > 0 else 'Short'
            
            full_taxonomy = f"{strategy}_{origin}_{direction}"
            # Örnek: LT_OV_Long, MM_INT_Short
```

## 3.3 Potential Qty Hesaplama

```python
# position_snapshot_api.py

# Potential = Current + Net Open Orders
net_open = open_qty_map.get(symbol, 0.0)
# Açık emirler için:
# - BUY emri → +qty
# - SELL emri → -qty

potential_qty = current_qty + net_open
```

## 3.4 Health Equation (RevnBookCheck)

```python
# Sağlık Denklemi
Gap = BEFDAY - POTENTIAL

# Sağlıklı durum:
if abs(Gap) < 200:
    # Pozisyon sağlıklı
    
# Bozuk durum (REV gerekli):
if abs(Gap) >= 200:
    # REV order oluştur
```

---

# 4. 8'Lİ POZİSYON TAKSONOMİSİ

## 4.1 Taksonomi Yapısı

```
┌─────────────────────────────────────────────────────────────┐
│                  8-TİP POZİSYON TAKSONOMİSİ                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   [Strategy]  ×  [Origin]  ×  [Direction]                  │
│                                                             │
│   LT (Long Term)    OV (Overnight)     Long                │
│   MM (Market Maker) INT (Intraday)     Short               │
│                                                             │
│   = 2 × 2 × 2 = 8 kombinasyon                              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  1. LT_OV_Long    │ Uzun vadeli, gece taşınan, long        │
│  2. LT_OV_Short   │ Uzun vadeli, gece taşınan, short       │
│  3. LT_INT_Long   │ Uzun vadeli, gün içi açılan, long      │
│  4. LT_INT_Short  │ Uzun vadeli, gün içi açılan, short     │
│  5. MM_OV_Long    │ Market maker, gece taşınan, long       │
│  6. MM_OV_Short   │ Market maker, gece taşınan, short      │
│  7. MM_INT_Long   │ Market maker, gün içi açılan, long     │
│  8. MM_INT_Short  │ Market maker, gün içi açılan, short    │
└─────────────────────────────────────────────────────────────┘
```

## 4.2 PositionTagManager

```python
# position_tags.py

@dataclass
class PositionTag:
    symbol: str
    strategy: str       # 'LT' veya 'MM'
    origin: str         # 'OV' veya 'INT'
    direction: str      # 'Long' veya 'Short'
    ov_qty: float = 0   # Overnight quantity
    int_qty: float = 0  # Intraday quantity
    total_qty: float = 0
    last_update: datetime = None

class PositionTagManager:
    """
    Singleton - Pozisyon tag'lerini yönetir.
    
    Kurallar:
    1. total_qty >= 1200 → otomatik 'OV' (upgrade rule)
    2. Aksi halde majority-wins: ov_qty > int_qty ? 'OV' : 'INT'
    3. Gün sonu reset: tüm int_qty → ov_qty olur
    """
    
    AUTO_UPGRADE_THRESHOLD = 1200  # Bu üzerinde otomatik OV
    
    def calculate_tag(self, ov_qty: float, int_qty: float) -> str:
        total = ov_qty + int_qty
        
        # Auto-upgrade rule
        if total >= self.AUTO_UPGRADE_THRESHOLD:
            return 'OV'
        
        # Majority-wins rule
        if ov_qty >= int_qty:
            return 'OV'
        return 'INT'
```

## 4.3 Strateji Belirleme (LT vs MM)

```python
def _determine_taxonomy(self, qty: float, befday_qty: float) -> Tuple[str, str, str]:
    """
    Strateji ve Origin belirleme.
    
    LT vs MM:
    - |qty| >= 400 → LT (Long Term)
    - |qty| < 400 → MM (Market Maker)
    
    OV vs INT:
    - BEFDAY'de varsa → OV (Overnight)
    - BEFDAY'de yoksa → INT (Intraday)
    """
    # Strategy
    strategy = 'LT' if abs(qty) >= 400 else 'MM'
    
    # Origin
    origin = 'OV' if abs(befday_qty) > 0 else 'INT'
    
    # Direction
    direction = 'Long' if qty > 0 else 'Short'
    
    full_taxonomy = f"{strategy}_{origin}_{direction}"
    return strategy, origin, full_taxonomy
```

---

# 5. GENOBS - GORT, FBTOT, SFSTOT HESAPLAMA

## 5.1 Genel Bakış

GENOBS (Group-based Observation Scores) sistemi, her hisseyi kendi grubu içinde değerlendirir:

```
┌─────────────────────────────────────────────────────────────┐
│                      GENOBS SKORLARI                        │
├─────────────────────────────────────────────────────────────┤
│  GORT    │ Group Outperform Relative Trend                 │
│          │ Grup benchmark'ına göre performans              │
│          │ > 0: outperform, < 0: underperform              │
├─────────────────────────────────────────────────────────────┤
│  Fbtot   │ Front Buy Total Score                           │
│          │ LONG için kullanılır                            │
│          │ Yüksek = daha iyi alış fırsatı                  │
├─────────────────────────────────────────────────────────────┤
│  SFStot  │ Soft Front Sell Total Score                     │
│          │ SHORT için kullanılır                           │
│          │ Yüksek = daha iyi short kapatma fırsatı         │
└─────────────────────────────────────────────────────────────┘
```

## 5.2 GORT (Group Outperform Relative Trend)

```python
# janall_metrics_engine.py

def compute_gort(self, symbol_metrics: Dict, group_stats: Dict) -> float:
    """
    GORT = Symbol Daily Change - Group Average Daily Change
    
    Örnek:
    - Symbol change: +$0.12
    - Group average: +$0.08
    - GORT = 0.12 - 0.08 = +0.04 (outperform)
    """
    symbol_daily_chg = symbol_metrics.get('daily_chg', 0)
    group_avg_chg = group_stats.get('avg_daily_chg', 0)
    
    gort = symbol_daily_chg - group_avg_chg
    return round(gort, 4)
```

## 5.3 Fbtot (Front Buy Total) Hesaplama

```python
def compute_fbtot(self, symbol_metrics: Dict, group_stats: Dict) -> float:
    """
    Fbtot = Grup içi Final_FB sıralaması + Ratio
    
    1. Tüm sembollerin Final_FB_skor değerlerini sırala (yüksek → düşük)
    2. Sembolün sırasını bul (rank)
    3. Fbtot = rank_normalized + relative_ratio
    
    Değer aralığı: ~0.8 - ~2.5
    """
    final_fb = symbol_metrics.get('final_fb', 0)
    group_final_fbs = group_stats.get('all_final_fb', [])
    
    if not group_final_fbs:
        return 1.0
    
    # Rank hesapla (1 = en iyi)
    sorted_fbs = sorted(group_final_fbs, reverse=True)
    rank = sorted_fbs.index(final_fb) + 1
    
    # Normalize (0-1 arası)
    rank_normalized = rank / len(sorted_fbs)
    
    # Ratio hesapla
    avg_fb = sum(group_final_fbs) / len(group_final_fbs)
    ratio = final_fb / avg_fb if avg_fb != 0 else 1.0
    
    fbtot = rank_normalized + ratio
    return round(fbtot, 2)
```

## 5.4 SFStot (Soft Front Sell Total) Hesaplama

```python
def compute_sfstot(self, symbol_metrics: Dict, group_stats: Dict) -> float:
    """
    SFStot = Grup içi Final_SFS sıralaması + Ratio
    
    1. Tüm sembollerin Final_SFS_skor değerlerini sırala (düşük → yüksek)
    2. Sembolün sırasını bul (rank)
    3. SFStot = rank_normalized + relative_ratio
    
    Değer aralığı: ~0.8 - ~2.5
    """
    # SFS için düşük skor = daha iyi short fırsatı
    # Bu yüzden sıralama ters
    final_sfs = symbol_metrics.get('final_sfs', 0)
    group_final_sfss = group_stats.get('all_final_sfs', [])
    
    if not group_final_sfss:
        return 1.0
    
    # Rank hesapla (1 = en düşük = en iyi short)
    sorted_sfss = sorted(group_final_sfss)  # Ascending
    rank = sorted_sfss.index(final_sfs) + 1
    
    # Normalize
    rank_normalized = rank / len(sorted_sfss)
    
    # Ratio hesapla
    avg_sfs = sum(group_final_sfss) / len(group_final_sfss)
    ratio = final_sfs / avg_sfs if avg_sfs != 0 else 1.0
    
    sfstot = rank_normalized + ratio
    return round(sfstot, 2)
```

## 5.5 Grup Bazlı İşlem Akışı

```
┌─────────────────────────────────────────────────────────────┐
│            JANALL METRICS ENGINE AKIŞI                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. compute_symbol_metrics()                                │
│     - Her sembol için L1 + static → basic scores            │
│                                                             │
│  2. compute_group_metrics()                                 │
│     - Grupları topla                                        │
│     - Her grup için avg_daily_chg hesapla                   │
│     - Her grup için rank listesi oluştur                    │
│                                                             │
│  3. apply_group_overlays()                                  │
│     - Her sembole GORT, Fbtot, SFStot ekle                  │
│     - Grup benchmark_chg uygula                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

# 6. UCUZLUK/PAHALILIK SKORLAMA

## 6.1 Temel Kavramlar

```
┌─────────────────────────────────────────────────────────────┐
│             UCUZLUK / PAHALILIK SKORLARI                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  UCUZLUK (Cheapness):                                       │
│  - Negatif = Ucuz (alış fırsatı)                           │
│  - Pozitif = Pahalı                                        │
│                                                             │
│  PAHALILIK (Expensiveness):                                 │
│  - Pozitif = Pahalı (satış fırsatı)                        │
│  - Negatif = Ucuz                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 6.2 Pasif Fiyatlar (Janall Formülleri)

```python
# fast_score_calculator.py

# ALIŞ FİYATLARI
pf_bid_buy = bid + (spread * 0.15)    # Bid Buy: Spread'in %15'i kadar içeri
pf_front_buy = last + 0.01            # Front Buy: Last + 1 cent
pf_ask_buy = ask + 0.01               # Ask Buy: Ask + 1 cent (agresif)

# SATIŞ FİYATLARI
pf_ask_sell = ask - (spread * 0.15)   # Ask Sell: Spread'in %15'i kadar içeri
pf_front_sell = last - 0.01           # Front Sell: Last - 1 cent
pf_bid_sell = bid - 0.01              # Bid Sell: Bid - 1 cent (agresif)
```

## 6.3 Değişim Hesaplama

```python
# Pasif fiyatların prev_close'a göre değişimi
pf_bid_buy_chg = pf_bid_buy - prev_close
pf_front_buy_chg = pf_front_buy - prev_close
pf_ask_sell_chg = pf_ask_sell - prev_close
pf_front_sell_chg = pf_front_sell - prev_close
```

## 6.4 Ucuzluk/Pahalılık Formülleri

```python
# Benchmark düşüldükten sonra:
bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
front_sell_pahalilik = pf_front_sell_chg - benchmark_chg

# Örnek:
# pf_bid_buy_chg = -0.03 (3 cent aşağıda)
# benchmark_chg = -0.01 (benchmark 1 cent düştü)
# bid_buy_ucuzluk = -0.03 - (-0.01) = -0.02
# → 2 cent ucuz (grup göre)
```

## 6.5 Final Skorlar

```python
# LONG Skorları (FINAL_THG kullanır)
# Multiplier: 1000

Final_BB_skor = FINAL_THG - 1000 * bid_buy_ucuzluk
Final_FB_skor = FINAL_THG - 1000 * front_buy_ucuzluk
Final_AB_skor = FINAL_THG - 1000 * ask_buy_ucuzluk

# SHORT Skorları (SHORT_FINAL kullanır)
Final_SAS_skor = SHORT_FINAL - 1000 * ask_sell_pahalilik
Final_SFS_skor = SHORT_FINAL - 1000 * front_sell_pahalilik
Final_SBS_skor = SHORT_FINAL - 1000 * bid_sell_pahalilik

# Örnek:
# FINAL_THG = 120
# bid_buy_ucuzluk = -0.05 (ucuz)
# Final_BB_skor = 120 - 1000 * (-0.05) = 120 + 50 = 170 (yüksek = iyi)
```

---

# 7. QEBENCH - BENCHMARK HESAPLAMA

## 7.1 Benchmark Engine Yapısı

```python
# benchmark_engine.py / qebench/benchmark.py

class BenchmarkEngine:
    """
    DOS Group ortalamasını hesaplar.
    Her grup için ETF ağırlıklı benchmark kullanır.
    """
    
    # Benchmark kaynakları:
    # 1. Redis: bench:dos_group:{group_key}:current_avg
    # 2. Hesaplama: Grup içi tüm sembollerin ortalaması
```

## 7.2 Grup Bazlı Benchmark

```python
def get_current_benchmark_price(self, symbol: str) -> Optional[float]:
    """
    1. Symbol → group_key bul (janall:metrics:{symbol})
    2. Group → benchmark fiyatı getir (bench:dos_group:{group_key}:current_avg)
    """
    # Redis'ten group_key al
    metrics = self.redis.get(f"janall:metrics:{symbol}")
    group_key = metrics.get('group_key')
    
    # Benchmark fiyatı al
    bench_key = f"bench:dos_group:{group_key}:current_avg"
    return float(self.redis.get(bench_key))
```

## 7.3 Benchmark Formülleri (ETF Ağırlıklı)

```yaml
# group_benchmark.yaml

# Her grup için ETF kombinasyonu
HELDKUPONLU:
  formula:
    PFF: 0.4    # %40 PFF
    VRP: 0.3    # %30 VRP
    JNK: 0.3    # %30 JNK

HELDFF:
  formula:
    PFF: 0.6
    PFFD: 0.4

DEZNFF:
  formula:
    PFF: 0.5
    JNK: 0.5
```

## 7.4 QeBench Calculator

```python
# qebench/calculator.py

def calculate_weighted_average(prices: List[float], weights: List[float]) -> float:
    """Ağırlıklı ortalama hesapla"""
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    
    weighted_sum = sum(p * w for p, w in zip(prices, weights))
    return weighted_sum / total_weight

def calculate_outperform(symbol_change: float, bench_change: float) -> float:
    """Benchmark'a göre outperformance"""
    return symbol_change - bench_change

def merge_position_with_fill(
    existing_qty: float,
    existing_avg: float,
    fill_qty: float,
    fill_price: float
) -> Tuple[float, float]:
    """Mevcut pozisyon ile fill'i birleştir (ağırlıklı ortalama)"""
    new_qty = existing_qty + fill_qty
    if new_qty == 0:
        return 0, 0
    
    new_avg = (existing_qty * existing_avg + fill_qty * fill_price) / new_qty
    return new_qty, new_avg
```

---

# 8. KARBOTU DECISION ENGINE

## 8.1 Karbotu Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                    KARBOTU ENGINE                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Macro Decision & Signal Engine                        │
│                                                             │
│  GİRDİ:                                                     │
│  - Pozisyon verisi (LT pozisyonlar)                        │
│  - Fbtot, SFStot, GORT skorları                            │
│  - Ucuzluk/Pahalılık skorları                              │
│                                                             │
│  ÇIKTI:                                                     │
│  - SIGNALS (LT Trim için eligibility, bias, quality)       │
│  - INTENTS (Makro azaltma önerileri)                       │
│                                                             │
│  ÖNEMLİ: Karbotu EMİR AÇMAZ, sadece sinyal/intent üretir   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 8.2 Karbotu Adımları (Steps)

### LONGS için (Steps 2-7):

```yaml
# karbotu_filters.csv / psfalgo_rules.yaml

step_2:
  name: "Fbtot < 1.10"
  filters:
    fbtot_lt: 1.10
    ask_sell_pahalilik_gt: -0.10
  lot_percentage: 50%
  action: SELL

step_3:
  name: "Fbtot 1.11-1.45 Low"
  filters:
    fbtot_gte: 1.11
    fbtot_lte: 1.45
    ask_sell_pahalilik_gte: -0.05
    ask_sell_pahalilik_lte: 0.04
  lot_percentage: 25%
  action: SELL

step_4:
  name: "Fbtot 1.11-1.45 High"
  filters:
    fbtot_gte: 1.11
    fbtot_lte: 1.45
    ask_sell_pahalilik_gt: 0.05
  lot_percentage: 50%
  action: SELL

step_5:
  name: "Fbtot 1.46-1.85 Low"
  filters:
    fbtot_gte: 1.46
    fbtot_lte: 1.85
    ask_sell_pahalilik_gte: 0.05
    ask_sell_pahalilik_lte: 0.10
  lot_percentage: 25%
  action: SELL

step_6:
  name: "Fbtot 1.46-1.85 High"
  filters:
    fbtot_gte: 1.46
    fbtot_lte: 1.85
    ask_sell_pahalilik_gt: 0.10
  lot_percentage: 50%
  action: SELL

step_7:
  name: "Fbtot 1.86-2.10"
  filters:
    fbtot_gte: 1.86
    fbtot_lte: 2.10
    ask_sell_pahalilik_gt: 0.20
  lot_percentage: 25%
  action: SELL
```

### SHORTS için (Steps 9-13):

```yaml
step_9:
  name: "SFStot > 1.70"
  filters:
    sfstot_gt: 1.70
    bid_buy_ucuzluk_lt: 0.10
  lot_percentage: 50%
  action: COVER

step_10:
  name: "SFStot 1.40-1.69 Low"
  filters:
    sfstot_gte: 1.40
    sfstot_lte: 1.69
    bid_buy_ucuzluk_gte: -0.04
    bid_buy_ucuzluk_lte: 0.05
  lot_percentage: 25%
  action: COVER

step_11:
  name: "SFStot 1.40-1.69 High"
  filters:
    sfstot_gte: 1.40
    sfstot_lte: 1.69
    bid_buy_ucuzluk_lt: -0.05
  lot_percentage: 50%
  action: COVER

step_12:
  name: "SFStot 1.10-1.39 Low"
  filters:
    sfstot_gte: 1.10
    sfstot_lte: 1.39
    bid_buy_ucuzluk_gte: -0.04
    bid_buy_ucuzluk_lte: 0.05
  lot_percentage: 25%
  action: COVER

step_13:
  name: "SFStot 1.10-1.39 High"
  filters:
    sfstot_gte: 1.10
    sfstot_lte: 1.39
    bid_buy_ucuzluk_lt: -0.05
  lot_percentage: 50%
  action: COVER
```

## 8.3 Karbotu Filter Mantığı

```python
# karbotu_engine_v2.py

def _passes_step_filters(
    self, 
    metrics: Dict, 
    step_config: Dict,
    side: str  # 'LONGS' veya 'SHORTS'
) -> bool:
    """
    Bir sembolün belirli bir step'in filtrelerini geçip geçmediğini kontrol eder.
    """
    filters = step_config.get('filters', {})
    
    # Fbtot filtreleri (LONGS için)
    if side == 'LONGS':
        fbtot = metrics.get('fbtot', 0)
        
        if 'fbtot_lt' in filters and fbtot >= filters['fbtot_lt']:
            return False
        if 'fbtot_lte' in filters and fbtot > filters['fbtot_lte']:
            return False
        if 'fbtot_gte' in filters and fbtot < filters['fbtot_gte']:
            return False
            
        # Ask Sell Pahalılık filtreleri
        pahalilik = metrics.get('ask_sell_pahalilik', 0)
        if 'ask_sell_pahalilik_gt' in filters and pahalilik <= filters['ask_sell_pahalilik_gt']:
            return False
        if 'ask_sell_pahalilik_gte' in filters and pahalilik < filters['ask_sell_pahalilik_gte']:
            return False
        if 'ask_sell_pahalilik_lte' in filters and pahalilik > filters['ask_sell_pahalilik_lte']:
            return False
    
    # SFStot filtreleri (SHORTS için)
    elif side == 'SHORTS':
        sfstot = metrics.get('sfstot', 0)
        
        if 'sfstot_gt' in filters and sfstot <= filters['sfstot_gt']:
            return False
        if 'sfstot_gte' in filters and sfstot < filters['sfstot_gte']:
            return False
        if 'sfstot_lte' in filters and sfstot > filters['sfstot_lte']:
            return False
        
        # Bid Buy Ucuzluk filtreleri
        ucuzluk = metrics.get('bid_buy_ucuzluk', 0)
        if 'bid_buy_ucuzluk_lt' in filters and ucuzluk >= filters['bid_buy_ucuzluk_lt']:
            return False
        if 'bid_buy_ucuzluk_gte' in filters and ucuzluk < filters['bid_buy_ucuzluk_gte']:
            return False
        if 'bid_buy_ucuzluk_lte' in filters and ucuzluk > filters['bid_buy_ucuzluk_lte']:
            return False
    
    return True
```

## 8.4 Lot Hesaplama (potential_qty Bazlı)

```python
def _calculate_lot(
    self,
    position: PositionSnapshot,
    step_config: Dict
) -> int:
    """
    potential_qty üzerinden lot hesapla.
    BEFDAY değil, POTENTIAL kullanılır.
    """
    lot_percentage = step_config.get('lot_percentage', 25)
    
    # potential_qty kullan (current + open orders)
    base_qty = abs(position.potential_qty)
    
    # Yüzde hesapla
    raw_lot = base_qty * (lot_percentage / 100)
    
    # 100'e yuvarla
    rounded_lot = int(raw_lot // 100) * 100
    
    # Minimum 100
    return max(100, rounded_lot)
```

## 8.5 Sweep Logic (Küçük Kalan Pozisyonlar)

```python
def _analyze_long(self, position: PositionSnapshot, metrics: Dict) -> Optional[Intent]:
    """
    Sweep Logic: Küçük kalan pozisyonları temizle.
    """
    abs_qty = abs(position.potential_qty)
    
    # Sweep Logic: < 400 lot kaldıysa, tamamını sat
    if abs_qty < 400 and abs_qty >= 100:
        return Intent(
            symbol=position.symbol,
            action=IntentAction.SELL,
            qty=abs_qty,  # Tamamı
            reason="SWEEP_SMALL_RESIDUAL",
            priority=80,
            category='KARBOTU'
        )
    
    # Normal step işleme...
```

---

# 9. ADDNEWPOS DECISION ENGINE

## 9.1 AddNewPos Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                   ADDNEWPOS ENGINE                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Position Opening Engine                               │
│                                                             │
│  AMAÇ: Yeni long ve short pozisyon açma                    │
│                                                             │
│  KOŞUL: Sadece OFANSIF modda çalışır                       │
│         (pot_total < pot_max)                               │
│                                                             │
│  ÖZEL: Mental Model V1 kullanır (Intent + Goodness)        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 9.2 Eligibility Kontrolü

```python
# addnewpos_engine.py

def is_eligible(self, exposure: ExposureSnapshot) -> bool:
    """
    AddNewPos sadece şu durumlarda çalışır:
    1. pot_total < pot_max
    2. exposure_mode == OFANSIF
    """
    if exposure.mode != 'OFANSIF':
        return False
    
    if exposure.pot_total >= exposure.pot_max:
        return False
    
    return True
```

## 9.3 Filtreler (Opsiyonel)

```yaml
# psfalgo_rules.yaml - addnewpos

addlong:
  enabled: true
  order_type: BID_BUY
  filters_disabled: true  # Kullanıcı isteğiyle devre dışı
  # filters:
  #   bid_buy_ucuzluk_lt: -0.06    # En az 6 cent ucuz
  #   fbtot_gt: 1.10               # Fbtot > 1.10
  #   spread_lt: 0.25              # Spread < 25 cent
  #   avg_adv_gt: 500              # Günlük hacim > 500

addshort:
  enabled: true
  order_type: ASK_SELL
  filters_disabled: true
  # filters:
  #   ask_sell_pahalilik_gt: 0.06  # En az 6 cent pahalı
  #   sfstot_gt: 1.10              # SFStot > 1.10
  #   spread_lt: 0.25
  #   avg_adv_gt: 500
```

## 9.4 Portfolio Rules (Lot Limitleri)

```yaml
# psfalgo_rules.yaml - addnewpos.rules.thresholds

# Portfolio yüzdesi bazlı MAXALW çarpanları
thresholds:
  - max_portfolio_percent: 1
    maxalw_multiplier: 0.50    # < %1 → MAXALW × 0.50
    portfolio_percent: 5

  - max_portfolio_percent: 3
    maxalw_multiplier: 0.40    # < %3 → MAXALW × 0.40
    portfolio_percent: 4

  - max_portfolio_percent: 5
    maxalw_multiplier: 0.30    # < %5 → MAXALW × 0.30
    portfolio_percent: 3

  - max_portfolio_percent: 7
    maxalw_multiplier: 0.20    # < %7 → MAXALW × 0.20
    portfolio_percent: 2

  - max_portfolio_percent: 10
    maxalw_multiplier: 0.10    # < %10 → MAXALW × 0.10
    portfolio_percent: 1.5

  - max_portfolio_percent: 100
    maxalw_multiplier: 0.05    # Genel → MAXALW × 0.05
    portfolio_percent: 1

exposure_usage_percent: 60  # Maksimum exposure kullanımı
```

## 9.5 Mental Model V1 Entegrasyonu

```python
def _calculate_lot_mental_model(
    self,
    symbol: str,
    direction: str,  # 'long' veya 'short'
    exposure: ExposureSnapshot,
    metrics: Dict
) -> int:
    """
    Mental Model V1:
    1. AddIntent hesapla (exposure bazlı)
    2. Goodness hesapla (skor bazlı)
    3. Desire = Intent × Goodness
    4. Lot = Desire × base_lot × k
    """
    from app.psfalgo.intent_math import compute_intents, compute_desire, calculate_rounded_lot
    
    # 1. Intent hesapla
    add_intent, reduce_intent = compute_intents(
        exposure_pct=exposure.ratio * 100,
        hard_threshold=130.0,
        soft_ratio=(12, 13)
    )
    
    # 2. Goodness hesapla
    if direction == 'long':
        goodness = self.compute_lt_goodness(metrics, 'BUY')
    else:
        goodness = self.compute_lt_goodness(metrics, 'SELL')
    
    # 3. Desire hesapla
    desire = compute_desire(add_intent, goodness)
    
    # 4. Lot hesapla
    base_lot = 1000
    k = 1.0
    raw_lot = desire * base_lot * k / 100
    
    # 5. Yuvarlama (200 minimum, 100'ün katı)
    final_lot = calculate_rounded_lot(raw_lot, 'BUY')
    
    return final_lot
```

## 9.6 Goodness Hesaplama

```python
def compute_lt_goodness(self, metrics: Dict, action: str) -> float:
    """
    LT Goodness skoru (0-100 arası).
    
    BUY için:
    - bid_buy_ucuzluk ne kadar negatif → o kadar iyi
    - fbtot ne kadar yüksek → o kadar iyi
    
    SELL için:
    - ask_sell_pahalilik ne kadar pozitif → o kadar iyi
    - sfstot ne kadar yüksek → o kadar iyi
    """
    if action == 'BUY':
        ucuzluk = metrics.get('bid_buy_ucuzluk', 0)
        fbtot = metrics.get('fbtot', 1.0)
        
        # Ucuzluk skoru: -0.10 = 100, 0 = 50, +0.10 = 0
        ucuzluk_score = max(0, min(100, 50 - ucuzluk * 500))
        
        # Fbtot skoru: 2.0 = 100, 1.0 = 50, 0.5 = 25
        fbtot_score = max(0, min(100, fbtot * 50))
        
        return (ucuzluk_score * 0.6 + fbtot_score * 0.4)
    
    else:  # SELL
        pahalilik = metrics.get('ask_sell_pahalilik', 0)
        sfstot = metrics.get('sfstot', 1.0)
        
        pahalilik_score = max(0, min(100, 50 + pahalilik * 500))
        sfstot_score = max(0, min(100, sfstot * 50))
        
        return (pahalilik_score * 0.6 + sfstot_score * 0.4)
```

---

# 10. REDUCEMORE RISK ENGINE

## 10.1 ReduceMore Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                   REDUCEMORE ENGINE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Risk & Multiplier Engine                              │
│                                                             │
│  AMAÇ:                                                      │
│  1. Global exposure'a göre REGIME belirle                   │
│  2. LT Trim için MULTIPLIER üret                            │
│  3. Acil durumlarda INTENT üret                             │
│                                                             │
│  ÇALIŞMA KOŞULU:                                            │
│  - exposure_mode == DEFANSIF veya GECIS                     │
│  - pot_total >= pot_max × 0.9                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 10.2 Regime Belirleme

```python
# reducemore_engine_v2.py

def _determine_regime(self, exposure: ExposureSnapshot) -> str:
    """
    Exposure'a göre regime belirle:
    - NORMAL: < %80
    - DEFENSIVE: %80-95
    - AGGRESSIVE: >= %95
    """
    ratio = exposure.ratio * 100  # Yüzde olarak
    
    if ratio >= 95:
        return 'AGGRESSIVE'
    elif ratio >= 80:
        return 'DEFENSIVE'
    else:
        return 'NORMAL'
```

## 10.3 Multiplier Üretimi

```python
def _generate_multiplier(self, regime: str) -> float:
    """
    LT Trim için multiplier üret.
    
    NORMAL: 1.0 (değişiklik yok)
    DEFENSIVE: 1.5 (lot'ları %50 artır)
    AGGRESSIVE: 2.0 (lot'ları 2 katına çıkar)
    """
    multipliers = {
        'NORMAL': 1.0,
        'DEFENSIVE': 1.5,
        'AGGRESSIVE': 2.0
    }
    return multipliers.get(regime, 1.0)
```

## 10.4 ReduceMore Adımları (Agresif Versiyonlar)

```yaml
# psfalgo_rules.yaml - reducemore

# LONGS için (daha agresif yüzdeler)
step_2:
  lot_percentage: 75%  # Normal: 50% → Agresif: 75%

step_3:
  lot_percentage: 50%  # Normal: 25% → Agresif: 50%

step_4:
  lot_percentage: 75%  # Normal: 50% → Agresif: 75%

# ... benzer şekilde diğer adımlar

# SHORTS için
step_9:
  lot_percentage: 75%  # Normal: 50% → Agresif: 75%

step_10:
  lot_percentage: 50%  # Normal: 25% → Agresif: 50%
```

---

# 11. LT TRIM EXECUTION ENGINE

## 11.1 LT Trim Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                    LT TRIM ENGINE                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Executive Execution Engine                            │
│                                                             │
│  GİRDİ:                                                     │
│  - SIGNALS (Karbotu'dan)                                    │
│  - MULTIPLIERS (ReduceMore'dan)                             │
│  - RUNTIME CONTROLS                                         │
│                                                             │
│  ÇIKTI:                                                     │
│  - INTENTS (order önerileri)                                │
│                                                             │
│  MANTIK:                                                    │
│  - Ladder (kademeli satış)                                  │
│  - Spread Gating (spread kontrolü)                          │
│  - Hidden Price hesaplama                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 11.2 Small vs Standard Positions

```python
# lt_trim_engine.py

SMALL_POSITION_THRESHOLD = 400  # lots

def _evaluate_trim(self, position: PositionSnapshot, signal: AnalysisSignal) -> Optional[Intent]:
    abs_qty = abs(position.potential_qty)
    abs_befday = abs(position.befday_qty)
    
    if abs_qty < self.SMALL_POSITION_THRESHOLD:
        # Small Position Logic (< 400 lots)
        return self._evaluate_small_position(position, signal)
    else:
        # Standard Position Logic (>= 400 lots)
        return self._evaluate_standard_position(position, signal)
```

## 11.3 Ladder Stages (Kademeli Satış)

```python
def _evaluate_standard_position(self, position, signal) -> Optional[Intent]:
    """
    Standard Position Ladder:
    
    Stage 1: SPREAD_GATING
    - Spread kontrolü, geniş spread'de bekle
    
    Stage 2: LADDER_1
    - İlk kademe satış (%25)
    
    Stage 3: LADDER_2
    - İkinci kademe satış (%50)
    
    Stage 4: LADDER_3
    - Son kademe satış (kalan)
    """
    score = signal.score
    spread = signal.spread
    
    # Spread Gating
    if spread > self.SPREAD_WIDE_THRESHOLD:  # 0.15
        if score < self.SPREAD_GATING_SCORE:  # 70
            return None  # Spread geniş, skor düşük → bekle
    
    # Ladder hesaplama
    if score >= 90:
        stage = 'LADDER_3'
        lot_pct = 100  # Tamamını sat
    elif score >= 70:
        stage = 'LADDER_2'
        lot_pct = 50
    elif score >= 50:
        stage = 'LADDER_1'
        lot_pct = 25
    else:
        return None  # Skor çok düşük
    
    lot = int(abs(position.potential_qty) * lot_pct / 100)
    return self._create_intent(position, lot, stage)
```

## 11.4 Hidden Price Hesaplama

```python
def _calculate_hidden_price(
    self, 
    action: str, 
    bid: float, 
    ask: float,
    spread: float
) -> float:
    """
    Hidden (pasif) fiyat hesapla.
    
    SELL: ask - (spread × 0.15)
    BUY:  bid + (spread × 0.15)
    """
    SPREAD_FACTOR = 0.15
    
    if action == 'SELL':
        return round(ask - (spread * SPREAD_FACTOR), 2)
    else:  # BUY (cover short)
        return round(bid + (spread * SPREAD_FACTOR), 2)
```

---

# 12. MM CHURN ENGINE

## 12.1 MM Churn Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                    MM CHURN ENGINE                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Market Making Engine                                  │
│                                                             │
│  AMAÇ:                                                      │
│  - Truth Price etrafında iki taraflı quote                  │
│  - Inventory yönetimi                                       │
│  - Spread yakalama                                          │
│                                                             │
│  KURALLAR:                                                  │
│  - Tick yuvarlama                                           │
│  - Anchor spacing (min mesafe)                              │
│  - Throttle & min interval                                  │
│  - Stale data gating                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 12.2 Pricing Logic

```python
# mm_churn_engine.py

def plan_churn(self, symbol: str, l1: Dict, truth_price: float) -> List[Dict]:
    """
    Truth Price etrafında BID ve ASK emirleri planla.
    """
    bid = l1.get('bid', 0)
    ask = l1.get('ask', 0)
    spread = ask - bid
    
    # Spread genişliğine göre pricing
    if spread <= 0.05:  # Tight spread
        # Truth'a yakın yerleş
        buy_price = self._round_price(truth_price - 0.02, 'down')
        sell_price = self._round_price(truth_price + 0.02, 'up')
    else:  # Wide spread
        # Spread'in %15'i kadar içeri gir
        buy_price = self._round_price(bid + (spread * 0.15), 'up')
        sell_price = self._round_price(ask - (spread * 0.15), 'down')
    
    # Anchor Spacing kontrolü
    if abs(sell_price - buy_price) < self.MIN_ANCHOR_SPACING:  # 0.06
        return []  # Çok yakın, skip
    
    return [
        {'action': 'BUY', 'price': buy_price, 'qty': self.DEFAULT_LOT},
        {'action': 'SELL', 'price': sell_price, 'qty': self.DEFAULT_LOT}
    ]
```

## 12.3 Throttle & Replace Kontrolü

```python
def _update_tokens(self):
    """
    Token bucket throttling.
    Her saniye 1 token eklenir, max 10.
    """
    now = time.time()
    elapsed = now - self._last_token_update
    tokens_to_add = int(elapsed)
    
    self._tokens = min(10, self._tokens + tokens_to_add)
    self._last_token_update = now

def _consume_token(self) -> bool:
    """
    Emir göndermek için token harca.
    Token yoksa False döner (throttled).
    """
    self._update_tokens()
    if self._tokens > 0:
        self._tokens -= 1
        return True
    return False

# No Change Logic
MIN_REPLACE_INTERVAL = 2.5  # saniye

def should_replace(self, old_price: float, new_price: float, last_replace_ts: float) -> bool:
    """
    Sadece şu durumlarda replace:
    1. Fiyat değişimi >= 1 tick (0.01)
    2. Son replace'den bu yana >= 2.5 saniye
    """
    now = time.time()
    
    # Min interval kontrolü
    if (now - last_replace_ts) < self.MIN_REPLACE_INTERVAL:
        return False
    
    # Fiyat değişimi kontrolü
    if abs(new_price - old_price) < 0.01:
        return False
    
    return True
```

---

# 13. JFIN TRANSFORMER

## 13.1 JFIN Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                    JFIN TRANSFORMER                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Deterministic Lot Distribution Transformer            │
│                                                             │
│  ⚠️ JFIN karar motoru DEĞİLDİR!                            │
│  ADDNEWPOS kararlarını lot'lara dönüştürür.                │
│                                                             │
│  AKIŞ:                                                      │
│  ADDNEWPOS Decision → JFIN → Intentions → User Approval    │
│                                                             │
│  4 AYRI HAVUZ (Pool):                                       │
│  - BB_LONG (Bid Buy Long)                                   │
│  - FB_LONG (Front Buy Long)                                 │
│  - SAS_SHORT (Ask Sell Short)                               │
│  - SFS_SHORT (Soft Front Sell Short)                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 13.2 JFIN Config Parametreleri

```yaml
# psfalgo_rules.yaml - jfin

tumcsv:
  selection_percent: 0.10        # %10 TUMCSV seçimi
  min_selection: 2               # Minimum 2 sembol/grup
  heldkuponlu_pair_count: 16     # HELDKUPONLU özel sayısı

  # Janall Selection Criteria
  long_percent: 25.0             # Top %25 LONG için
  long_multiplier: 1.5           # Ortalama × 1.5 LONG için
  short_percent: 25.0            # Bottom %25 SHORT için
  short_multiplier: 0.7          # Ortalama × 0.7 SHORT için
  max_short: 3                   # Grup başına max SHORT

  # Company Limit
  company_limit_enabled: true
  company_limit_divisor: 1.6     # max = total / 1.6

lot_distribution:
  alpha: 3                       # Lot dağıtım ağırlığı
  total_long_rights: 28000       # Toplam long lot hakkı
  total_short_rights: 12000      # Toplam short lot hakkı
  lot_rounding: 100              # 100'e yuvarla

percentage:
  default: 50                    # %50 default
  options: [25, 50, 75, 100]     # Seçenekler

lot_controls:
  min_lot_per_order: 200         # Minimum 200 lot
  max_lot_per_order: 5000        # Maximum 5000 lot
```

## 13.3 Two-Step Intersection Logic (Janall)

```python
# jfin_engine.py

def _select_stocks_janall_logic(
    self,
    candidates: List[Dict],
    primary_score: str,
    direction: str,  # 'LONG' veya 'SHORT'
    group_name: str
) -> List[Dict]:
    """
    Janall'ın tam seçim mantığı:
    
    1. Criterion 1: Average × Multiplier
       - LONG: score >= avg × 1.5
       - SHORT: score <= avg × 0.7
    
    2. Criterion 2: Top/Bottom %X
       - LONG: Top %25
       - SHORT: Bottom %25
    
    3. Intersection: İKİ kriteri de geçenler
    
    4. Company Limit: max = total / 1.6
    """
    # Ortalama hesapla
    score_values = [c.get(primary_score, 0) for c in candidates]
    avg_score = sum(score_values) / len(score_values)
    
    # Criterion 1: Threshold
    if direction == 'LONG':
        threshold = avg_score * self.config.long_multiplier  # × 1.5
        criterion1 = [c for c in candidates if c.get(primary_score, 0) >= threshold]
    else:
        threshold = avg_score * self.config.short_multiplier  # × 0.7
        criterion1 = [c for c in candidates if c.get(primary_score, 0) <= threshold]
    
    # Criterion 2: Rank
    if direction == 'LONG':
        sorted_candidates = sorted(candidates, key=lambda x: x.get(primary_score, 0), reverse=True)
        top_count = int(len(candidates) * self.config.long_percent / 100)
        criterion2 = sorted_candidates[:top_count]
    else:
        sorted_candidates = sorted(candidates, key=lambda x: x.get(primary_score, 0))
        bottom_count = int(len(candidates) * self.config.short_percent / 100)
        criterion2 = sorted_candidates[:bottom_count]
    
    # Intersection
    c1_symbols = {c['symbol'] for c in criterion1}
    c2_symbols = {c['symbol'] for c in criterion2}
    intersection_symbols = c1_symbols & c2_symbols
    
    selected = [c for c in candidates if c['symbol'] in intersection_symbols]
    
    # Company Limit
    selected = self._apply_company_limit(selected, direction)
    
    return selected
```

## 13.4 Alpha-Weighted Lot Distribution

```python
def _distribute_lots(
    self,
    stocks: List[JFINStock],
    direction: str  # 'long' veya 'short'
) -> List[JFINStock]:
    """
    Alpha-weighted lot dağıtımı:
    
    Group Lot = Total Rights × (Group Weight / 100) × Alpha
    Stock Lot = Group Lot × (Stock Score / Group Total Score)
    """
    total_rights = (
        self.config.total_long_rights if direction == 'long'  # 28000
        else self.config.total_short_rights  # 12000
    )
    
    for group_name, group_stocks in groups.items():
        weight = self._group_weights[direction].get(group_name, 0)
        if weight <= 0:
            continue
        
        # Grup lot hakkı
        group_lot = total_rights * (weight / 100) * self.config.alpha  # × 3
        
        # Toplam skor
        total_score = sum(abs(self._get_primary_score(s)) for s in group_stocks)
        
        # Skor-ağırlıklı dağıtım
        for stock in group_stocks:
            score_ratio = abs(self._get_primary_score(stock)) / total_score
            lot = group_lot * score_ratio
            stock.calculated_lot = int(lot // 100) * 100  # 100'e yuvarla
    
    return stocks
```

## 13.5 JFIN Price Formulas

```python
# Order Type → Price Formula
BB:   price = bid + (spread × 0.15)   # Bid Buy
FB:   price = last + 0.01             # Front Buy
SAS:  price = ask - (spread × 0.15)   # Ask Sell
SFS:  price = last - 0.01             # Front Sell
```

---

# 14. TRUTH TICKS VE VOLAV

## 14.1 Truth Ticks Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                    TRUTH TICKS ENGINE                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AMAÇ: İllikid hisseler için GERÇEK fiyat hareketini bul   │
│                                                             │
│  PROBLEM:                                                   │
│  - Son işlem fiyatı yanıltıcı olabilir                     │
│  - Küçük lotlar (1-10) manipülatif olabilir                │
│  - FNRA/dark pool verileri güvenilmez                      │
│                                                             │
│  ÇÖZÜM:                                                     │
│  - Ağırlıklı işlem realizmi (Weighted Print Realism)       │
│  - Volume-konzentrasyon seviyeleri (Volav)                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 14.2 Print Weight Hesaplama

```python
# truth_ticks_engine.py

def calculate_print_weight(self, size: float, venue: str) -> float:
    """
    İşlem ağırlığı hesapla (Binary: 1.0 veya 0.0)
    
    KURALLAR:
    1. size < 15 → REDDİT (0.0)
    2. FNRA/ADFN için SADECE 100 veya 200 lot → KABUL (1.0)
    3. Non-FNRA (NYSE, ARCA) size >= 15 → KABUL (1.0)
    """
    # Global min size
    if size < 15:
        return 0.0
    
    venue_upper = str(venue).upper()
    
    # FNRA/ADFN özel kuralı
    if venue_upper in ['FNRA', 'ADFN', 'FINRA', 'OTC', 'DARK']:
        # SADECE 100 veya 200 kabul
        if size == 100 or size == 200:
            return 1.0
        else:
            return 0.0
    
    # Non-FNRA
    return 1.0
```

## 14.3 Volav (Volume-Averaged Levels)

```python
def compute_volav_levels(
    self,
    truth_ticks: List[Dict],
    top_n: int = 4,
    avg_adv: float = 0.0
) -> Tuple[List[Dict], List[Dict]]:
    """
    Volume-ağırlıklı fiyat seviyeleri hesapla.
    
    1. Bucket aggregation (fiyat gruplandırma)
    2. VWAP hesapla (her bucket için)
    3. En yüksek hacimli N seviyeyi döndür
    """
    # Dinamik bucket size (ADV'ye göre)
    bucket_size = self.bucket_size(avg_adv)
    
    # Bucket'lara böl
    bucket_volume = defaultdict(float)
    bucket_price_sum = defaultdict(float)
    
    for tick in truth_ticks:
        price = tick['price']
        size = tick['size']
        weight = self.calculate_print_weight(size, tick.get('exch', ''))
        
        if weight <= 0:
            continue
        
        # Bucket key
        bucket_key = round(price / bucket_size) * bucket_size
        
        # Ağırlıklı hacim
        weighted_size = size * weight
        bucket_volume[bucket_key] += weighted_size
        bucket_price_sum[bucket_key] += price * weighted_size
    
    # VWAP hesapla
    bucket_vwap = {}
    for key, vol in bucket_volume.items():
        bucket_vwap[key] = bucket_price_sum[key] / vol
    
    # En yüksek hacimli N seviye
    sorted_buckets = sorted(bucket_volume.items(), key=lambda x: x[1], reverse=True)
    top_levels = sorted_buckets[:top_n]
    
    return [{'price': bucket_vwap[k], 'volume': v} for k, v in top_levels]
```

## 14.4 Bucket Size (ADV Bazlı)

```python
def bucket_size(self, avg_adv: float) -> float:
    """
    Günlük hacme göre bucket boyutu:
    - Yüksek hacim → Dar bucket (hassas)
    - Düşük hacim → Geniş bucket (toleranslı)
    """
    if avg_adv >= 100000:
        return 0.03  # 3 cent
    elif avg_adv >= 50000:
        return 0.05  # 5 cent
    elif avg_adv >= 10000:
        return 0.07  # 7 cent
    else:
        return 0.09  # 9 cent

def min_volav_gap(self, avg_adv: float) -> float:
    """
    Volav seviyeleri arası minimum mesafe:
    """
    if avg_adv >= 100000:
        return 0.03
    elif avg_adv >= 50000:
        return 0.05
    elif avg_adv >= 10000:
        return 0.09
    else:
        return 0.15
```

## 14.5 Microstructure Rules

```yaml
# microstructure_rules.yaml

print_realism:
  min_lot_ignore: 20           # 20'den küçük ignore

  weights:
    lot_100_200: 1.0           # 100/200 lot = tam ağırlık
    round_large: 0.4           # 300, 400, 500... = %40 ağırlık
    irregular: 0.2             # Düzensiz lotlar = %20 ağırlık

slippage:
  adv_thresholds:
    - { adv: 100000, bad_slip: 0.03 }
    - { adv: 40000,  bad_slip: 0.05 }
    - { adv: 10000,  bad_slip: 0.07 }
    - { adv: 2000,   bad_slip: 0.10 }
  
  spread_floor_multiplier: 0.25  # max(base, spread × 0.25)
```

---

# 15. REV ORDER VE REVNBOOK MEKANİZMASI

## 15.1 REV Order Nedir?

```
┌─────────────────────────────────────────────────────────────┐
│                    REV ORDER ENGINE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  REV = Reverse Order                                        │
│                                                             │
│  AMAÇ:                                                      │
│  - INCREASE Fill sonrası: Take Profit ($0.04)               │
│  - DECREASE Fill sonrası: Reload Save ($0.06)               │
│                                                             │
│  TÜM REV emirleri HIDDEN!                                   │
│                                                             │
│  4-QUADRANT LOGIC:                                          │
│  1. Long Increase → SELL @ fill + $0.04 (TP)                │
│  2. Long Decrease → BUY @ fill - $0.06 (Reload)             │
│  3. Short Increase → BUY @ fill - $0.04 (TP)                │
│  4. Short Decrease → SELL @ fill + $0.06 (Reload)           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 15.2 REV Order Hesaplama

```python
# revorder_engine.py

def calculate_rev_order(self, fill_event: Dict, l1_data: Dict) -> Optional[Dict]:
    """
    Fill event'e göre REV order hesapla.
    """
    action = fill_event['action']  # BUY veya SELL
    fill_price = fill_event['price']
    tag = fill_event.get('tag', '').upper()
    
    bid = l1_data.get('bid', 0)
    ask = l1_data.get('ask', 0)
    spread = l1_data.get('spread', 0)
    
    is_increase = "INCREASE" in tag
    is_decrease = "DECREASE" in tag
    
    rev_action = 'SELL' if action == 'BUY' else 'BUY'
    
    if is_increase:
        # PROFIT TARGET: $0.04
        profit_target = 0.04
        
        if action == 'BUY':  # Long Increase → SELL
            min_price = fill_price + profit_target
            
            # L1 Priority: Ask - 15% of spread
            ideal_price = ask - (spread * 0.15)
            
            if ideal_price >= min_price:
                rev_price = ideal_price
                method = "L1_SPREAD_15_OFF"
            else:
                # Orderbook'tan uygun seviye bul
                suitable_ask = self.ob_fetcher.find_suitable_ask(symbol, min_price)
                if suitable_ask:
                    rev_price = suitable_ask - 0.01  # Front
                    method = "DEPTH_FRONT"
                else:
                    rev_price = min_price
                    method = "HARD_TARGET_0.04"
        
        else:  # Short Increase → BUY
            max_price = fill_price - profit_target
            ideal_price = bid + (spread * 0.15)
            # ... benzer mantık
    
    else:  # DECREASE
        # SAVE TARGET: $0.06 (Reload)
        save_target = 0.06
        
        if action == 'SELL':  # Long Decrease → RELOAD BUY
            max_price = fill_price - save_target
            # ... hesaplama
        else:  # Short Decrease → RELOAD SELL
            min_price = fill_price + save_target
            # ... hesaplama
    
    return {
        'symbol': fill_event['symbol'],
        'action': rev_action,
        'qty': fill_event['qty'],
        'price': round(rev_price, 2),
        'hidden': True,  # TÜM REV'LER HIDDEN!
        'tag': f"REV_{tag}",
        'method': method
    }
```

## 15.3 RevnBookCheck Terminal

```python
# revnbookcheck.py

class RevnBookCheckTerminal:
    """
    REV Order otomatik üretici.
    
    İşlem Akışı:
    1. Redis Stream'den fill event'leri dinle
    2. Health Equation kontrolü
    3. Gap >= 200 ise REV oluştur
    4. REV order'ı API üzerinden gönder
    """
    
    async def _process_fill(self, fill: Dict):
        # Position Snapshot al
        snapshots = await pos_api.get_position_snapshot(account_id, [symbol])
        snap = snapshots[0]
        
        befday = snap.befday_qty
        potential = snap.potential_qty
        current = snap.qty
        
        # Health Equation Check
        gap = befday - potential
        
        # Tolerance check
        if abs(gap) < 200:
            return  # Sağlıklı, REV gerekli değil
        
        # Triple Equality check
        if befday == current or befday == potential:
            return  # Hedef tutturulmuş
        
        # REV gerekli!
        rev_action = 'BUY' if gap > 0 else 'SELL'
        
        # REV order hesapla ve gönder
        rev_order = self.rev_engine.calculate_rev_order(pseudo_fill, l1_data)
        await self._place_rev_order(rev_order)
```

## 15.4 REV Recovery Service

```python
# rev_recovery_service.py

class RevRecoveryService:
    """
    2 dakikada bir Health Equation kontrolü.
    Eksik REV'leri oluşturur.
    """
    
    async def start_periodic_check(self, interval_seconds: int = 120):
        while self.running:
            await self._run_recovery_check()
            await asyncio.sleep(interval_seconds)
    
    async def _run_recovery_check(self):
        """
        Tüm pozisyonlar için Health Equation kontrol et.
        """
        snapshots = await pos_api.get_position_snapshot(account_id)
        
        for snap in snapshots:
            gap = snap.befday_qty - snap.potential_qty
            
            # Health check
            is_healthy = abs(gap) < 200 or snap.befday_qty == snap.qty
            
            if not is_healthy:
                # Eksik REV oluştur
                await self._create_missing_rev_from_gap(snap, gap)
```

---

# 16. ORDER LIFECYCLE VE TTL

## 16.1 Order Lifecycle Policy

```
┌─────────────────────────────────────────────────────────────┐
│                  ORDER LIFECYCLE POLICY                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PRENSIPLER:                                                │
│  1. Mass cancel YOK - Selective cancel                      │
│  2. TTL per intent category                                 │
│  3. Replace only if price changed >= 1 tick                 │
│  4. Min 2.5s between replaces                               │
│  5. Stale data > 90s → freeze                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 16.2 TTL by Category

```yaml
# psfalgo_rules.yaml - order_lifecycle

ttl_by_category:
  LT_TRIM: 120       # 2 dakika
  MM_CHURN: 60       # 1 dakika
  ADDNEWPOS: 180     # 3 dakika
  KARBOTU: 120       # 2 dakika
  REDUCEMORE: 90     # 1.5 dakika
  HARD_DERISK: 30    # 30 saniye (acil)
  CLOSE_EXIT: 15     # 15 saniye (çok acil)
  DEFAULT: 90        # Fallback

min_replace_interval_seconds: 2.5
price_change_threshold_cents: 1    # 1 tick
stale_data_threshold_seconds: 90
selective_cancel_enabled: true
```

## 16.3 Order Decision Logic

```python
# order_lifecycle.py

class OrderAction(Enum):
    KEEP = "KEEP"
    REPLACE = "REPLACE"
    CANCEL = "CANCEL"

def evaluate_orders(self, active_orders, symbol_states, regime, excluded_symbols):
    """
    Her aktif emir için KEEP/REPLACE/CANCEL kararı ver.
    """
    decisions = []
    
    for order in active_orders:
        order_id = order['order_id']
        symbol = order['symbol']
        intent_category = order.get('intent_category', 'DEFAULT')
        created_ts = order['created_ts']
        
        state = symbol_states.get(symbol, {})
        truth_age = state.get('truth_age', 999)
        
        # 1. Excluded symbol → CANCEL
        if symbol in excluded_symbols:
            decisions.append(OrderDecision(order_id, symbol, OrderAction.CANCEL, "EXCLUDED"))
            continue
        
        # 2. TTL expired → CANCEL
        ttl = self.get_ttl(intent_category)
        if (time.time() - created_ts) > ttl:
            decisions.append(OrderDecision(order_id, symbol, OrderAction.CANCEL, f"TTL_EXPIRED_{ttl}s"))
            continue
        
        # 3. Stale data → FREEZE (keep if still valid)
        if truth_age > self.STALE_DATA_THRESHOLD:  # 90s
            is_valid, reason = self.is_order_valid(order, state, regime)
            if not is_valid:
                decisions.append(OrderDecision(order_id, symbol, OrderAction.CANCEL, f"STALE_AND_INVALID:{reason}"))
            else:
                decisions.append(OrderDecision(order_id, symbol, OrderAction.KEEP, "STALE_BUT_VALID_FROZEN"))
            continue
        
        # 4. Regime validation
        is_valid, reason = self.is_order_valid(order, state, regime)
        if not is_valid:
            decisions.append(OrderDecision(order_id, symbol, OrderAction.CANCEL, reason))
            continue
        
        # 5. All good → KEEP
        decisions.append(OrderDecision(order_id, symbol, OrderAction.KEEP, "VALID"))
    
    return decisions
```

---

# 17. MENTAL MODEL V1 - INTENT MATH

## 17.1 Intent Model Yapısı

```
┌─────────────────────────────────────────────────────────────┐
│                    MENTAL MODEL V1                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  KAVRAMLAR:                                                 │
│  - Intent: Ekleme/Azaltma isteği (0-100)                   │
│  - Goodness: Fırsat kalitesi (0-100)                       │
│  - Desire: Intent × Goodness                                │
│                                                             │
│  FORMÜL:                                                    │
│  Lot = (Desire / 100) × base_lot × k                       │
│                                                             │
│  YUVARLAMA:                                                 │
│  - 200 minimum trade (100-199 → 200)                       │
│  - 100'den küçük raw → 0                                   │
│  - Post-trade holding min 200                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 17.2 Piecewise Intent Model

```python
# intent_math.py

def compute_intents(
    exposure_pct: float,
    hard_threshold: float = 130.0,
    soft_ratio: Tuple[int, int] = (12, 13),
    Amax: float = 100.0,
    Asoft: float = 20.0,
    pn: float = 1.25,
    q: float = 2.14,
    ps: float = 1.50
) -> Tuple[float, float]:
    """
    Exposure'a göre Add/Reduce Intent hesapla.
    
    Piecewise Model C:
    - Normal Zone (0 to Soft): AddIntent yüksek, yavaşça düşer
    - Soft Zone (Soft to Hard): AddIntent hızla düşer, ReduceIntent başlar
    - Hard Zone (> Hard): AddIntent = 0, ReduceIntent maksimum
    """
    # Soft threshold otomatik hesapla
    soft_threshold = hard_threshold * (soft_ratio[0] / soft_ratio[1])
    # 130 × (12/13) = 120
    
    if exposure_pct <= 0:
        return (Amax, 0.0)  # Add: 100, Reduce: 0
    
    if exposure_pct < soft_threshold:  # Normal Zone
        # Add Intent: Yavaşça düşer
        x = exposure_pct / soft_threshold  # Normalize to 0-1
        add_intent = Amax - (Amax - Asoft) * (x ** q) ** pn
        reduce_intent = 0.0
        
    elif exposure_pct < hard_threshold:  # Soft Zone
        # Add Intent: Hızla düşer
        x = (exposure_pct - soft_threshold) / (hard_threshold - soft_threshold)
        add_intent = Asoft * (1 - x ** ps)
        # Reduce Intent: Başlar
        reduce_intent = x * 50  # 0-50 arası
        
    else:  # Hard Zone
        add_intent = 0.0
        reduce_intent = 100.0  # Maksimum reduce
    
    return (max(0, add_intent), min(100, reduce_intent))
```

## 17.3 Desire Hesaplama

```python
def compute_desire(intent: float, goodness: float) -> float:
    """
    Desire = Intent × Goodness / 100
    
    Örnek:
    - Intent = 70 (ekleme isteği)
    - Goodness = 80 (iyi fırsat)
    - Desire = 70 × 80 / 100 = 56
    """
    return intent * goodness / 100
```

## 17.4 Lot Rounding Rules

```python
def calculate_rounded_lot(raw_lot: float, action: str) -> int:
    """
    Lot yuvarlama kuralları:
    
    1. raw < 100 → 0 (işlem yok)
    2. 100 ≤ raw < 200 → 200 (minimum trade)
    3. raw ≥ 200 → 100'e yuvarla (BUY: up, SELL: down)
    """
    if raw_lot < 100:
        return 0
    
    if raw_lot < 200:
        return 200  # Minimum trade
    
    # 100'e yuvarla
    if action == 'BUY':
        # Buy için yukarı yuvarla (daha fazla al)
        return int(math.ceil(raw_lot / 100)) * 100
    else:
        # Sell için aşağı yuvarla (daha az sat)
        return int(math.floor(raw_lot / 100)) * 100

def clamp_post_trade_hold(current_qty: float, trade_qty: int, action: str) -> int:
    """
    Trade sonrası minimum 200 lot holding olmalı.
    
    Örnek:
    - Current: 500
    - SELL 400 isteniyor
    - Kalan: 100 (< 200)
    - Düzeltme: SELL 300 (kalan 200)
    """
    if action == 'SELL':
        post_trade = current_qty - trade_qty
        if 0 < post_trade < 200:
            # Minimum 200 bırak
            return int(current_qty - 200)
    
    elif action == 'BUY':
        post_trade = current_qty + trade_qty
        # Short kapatma için benzer mantık
        if post_trade < 0 and abs(post_trade) < 200:
            return int(abs(current_qty) - 200)
    
    return trade_qty
```

## 17.5 Pick Policy

```yaml
# psfalgo_rules.yaml - pick_policy

# AddIntent'e göre kaç aday seçilecek
add_intent_ge_70: 5    # Intent >= 70 → 5 aday
add_intent_ge_40: 3    # Intent >= 40 → 3 aday
add_intent_ge_20: 3    # Intent >= 20 → 3 aday
add_intent_lt_20: 3    # Intent < 20 → 3 aday (kullanıcı isteğiyle aktif)

# MM override: Intent düşük ama goodness yüksekse devam et
mm_override_goodness: 90
```

---

# 18. DATA FABRIC - FAST/SLOW PATH

## 18.1 Data Fabric Yapısı

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA FABRIC                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Central In-Memory Data Store                               │
│  Single Source of Truth                                     │
│                                                             │
│  TWO-PATH ARCHITECTURE:                                     │
│                                                             │
│  🟢 FAST PATH (UI & Algo):                                  │
│  - L1 Data (bid, ask, last)                                │
│  - Static Data (prev_close, FINAL_THG)                     │
│  - Fast Scores (Fbtot, SFStot, GORT, ucuzluk/pahalilik)   │
│  - benchmark_chg, daily_change                             │
│                                                             │
│  🔴 SLOW PATH (Deep Analysis):                              │
│  - GOD, ROD, GRPAN (tick-by-tick)                          │
│  - Truth Ticks, Volav                                      │
│  - Historical analysis                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 18.2 Veri Katmanları

```python
# data_fabric.py

class DataFabric:
    """
    Central In-Memory Data Fabric
    """
    
    def __init__(self):
        # Static data (CSV'den yüklenir)
        self._static: Dict[str, Dict[str, Any]] = {}
        
        # Live data (Hammer L1)
        self._live: Dict[str, Dict[str, Any]] = {}
        
        # Derived data (hesaplanan skorlar)
        self._derived: Dict[str, Dict[str, Any]] = {}
        
        # ETF data
        self._etf_live: Dict[str, Dict[str, Any]] = {}
        self._etf_prev_close: Dict[str, float] = {}
        
        # Dirty tracking (değişen semboller)
        self._dirty_symbols: Set[str] = set()
    
    def get_fast_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Tek sembol için tüm FAST PATH verisini döndür.
        """
        static = self._static.get(symbol)
        live = self._live.get(symbol)
        derived = self._derived.get(symbol)
        
        if not static or not live:
            return None
        
        return {
            # Static
            'prev_close': static.get('prev_close'),
            'FINAL_THG': static.get('FINAL_THG'),
            'SHORT_FINAL': static.get('SHORT_FINAL'),
            'GROUP': static.get('GROUP'),
            'CGRUP': static.get('CGRUP'),
            'MAXALW': static.get('MAXALW'),
            'AVG_ADV': static.get('AVG_ADV'),
            
            # Live
            'bid': live.get('bid'),
            'ask': live.get('ask'),
            'last': live.get('last'),
            'spread': live.get('spread'),
            
            # Derived
            **(derived or {})
        }
```

## 18.3 Lifeless Mode (Simulation)

```python
def set_lifeless_mode(self, enabled: bool):
    """
    Simulation modu - gerçek market verisi yerine sentetik veri kullan.
    """
    self._lifeless_mode = enabled
    if enabled:
        logger.info("🔴 LIFELESS MODE ACTIVATED - Using synthetic data")
        self._load_lifeless_data()

def shuffle_lifeless_data(self):
    """
    Sentetik verileri karıştır (test için).
    prev_close etrafında simüle edilmiş bid/ask/last.
    """
    for symbol, static in self._static.items():
        prev_close = static.get('prev_close', 25.0)
        
        # Simüle edilmiş fiyat hareketi
        change_pct = random.uniform(-0.02, 0.02)  # ±%2
        last = prev_close * (1 + change_pct)
        
        # Simüle edilmiş spread
        spread = random.uniform(0.02, 0.10)
        bid = last - spread / 2
        ask = last + spread / 2
        
        self._live[symbol] = {
            'bid': round(bid, 2),
            'ask': round(ask, 2),
            'last': round(last, 2),
            'spread': round(spread, 2)
        }
```

---

# 19. RUNALL ORCHESTRATOR

## 19.1 RunAll Yapısı

```
┌─────────────────────────────────────────────────────────────┐
│                   RUNALL ORCHESTRATOR                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TİP: Central Conductor                                     │
│  CYCLE: 240 saniye (4 dakika)                              │
│                                                             │
│  AKIŞ:                                                      │
│  1. State yükle (positions, exposure, market data)         │
│  2. Analyzer'ları çalıştır (Karbotu, ReduceMore, AddNewPos)│
│  3. Executive'i çalıştır (LT Trim)                         │
│  4. Conflict resolution                                     │
│  5. Intent → Decision → Proposal/Execution                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 19.2 Cycle Loop

```python
# runall_engine_v2.py

async def _cycle_loop(self):
    """
    Ana döngü - her 240 saniyede bir çalışır.
    """
    while self._running:
        try:
            await self.run_single_cycle()
            await asyncio.sleep(self._cycle_interval)  # 240s
        except Exception as e:
            logger.error(f"Cycle error: {e}")
            await asyncio.sleep(30)  # Hata sonrası kısa bekle

async def run_single_cycle(self):
    """
    Tek bir cycle:
    1. Prepare request (state yükle)
    2. Run analyzers
    3. Run executive
    4. Resolve conflicts
    5. Submit intents
    """
    # 1. State hazırla
    request = await self._prepare_request()
    
    # 2. Analyzer'ları çalıştır
    karbotu_result = await self.karbotu.run(request)
    reducemore_result = await self.reducemore.run(request)
    addnewpos_result = await self.addnewpos.run(request)
    
    # 3. Executive'i çalıştır (Karbotu sinyalleri ile)
    lt_trim_result = await self.lt_trim.run(request, karbotu_result.signals)
    
    # 4. Tüm intent'leri topla
    all_intents = []
    all_intents.extend(karbotu_result.intents)
    all_intents.extend(reducemore_result.intents)
    all_intents.extend(addnewpos_result.intents)
    all_intents.extend(lt_trim_result.intents)
    
    # 5. Conflict resolution
    resolved_intents = self._resolve_conflicts(all_intents)
    
    # 6. Intent → Decision → Execution
    for intent in resolved_intents:
        decision = self._adapt_intents_to_decisions([intent])[0]
        await self._submit_decision(decision)
```

## 19.3 Conflict Resolution

```python
def _resolve_conflicts(self, intents: List[Intent]) -> List[Intent]:
    """
    Aynı sembol için çakışan intent'leri çöz.
    
    Öncelik sırası:
    1. HARD_DERISK (en yüksek)
    2. CLOSE_EXIT
    3. REDUCEMORE
    4. KARBOTU
    5. LT_TRIM
    6. ADDNEWPOS (en düşük)
    """
    PRIORITY_ORDER = {
        'HARD_DERISK': 100,
        'CLOSE_EXIT': 90,
        'REDUCEMORE': 80,
        'KARBOTU': 70,
        'LT_TRIM': 60,
        'MM_CHURN': 50,
        'ADDNEWPOS': 40
    }
    
    # Sembol bazında grupla
    by_symbol: Dict[str, List[Intent]] = {}
    for intent in intents:
        symbol = intent.symbol
        if symbol not in by_symbol:
            by_symbol[symbol] = []
        by_symbol[symbol].append(intent)
    
    resolved = []
    for symbol, symbol_intents in by_symbol.items():
        if len(symbol_intents) == 1:
            resolved.append(symbol_intents[0])
            continue
        
        # En yüksek öncelikli intent'i seç
        sorted_intents = sorted(
            symbol_intents,
            key=lambda x: PRIORITY_ORDER.get(x.category, 0),
            reverse=True
        )
        
        winner = sorted_intents[0]
        
        # Residual check: Kalan lot varsa secondary intent'i de çalıştır
        for intent in sorted_intents[1:]:
            if intent.action == winner.action:
                # Aynı yönde → lot'ları birleştir
                winner.qty += intent.qty
        
        resolved.append(winner)
    
    return resolved
```

---

# 20. SAYISAL PARAMETRELER TAM LİSTESİ

## 20.1 Exposure Parametreleri

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| `exposure_limit` | 5,000,000 | Maksimum dolar exposure |
| `pot_expo_limit` | 6,363,600 | Portfolio exposure limiti |
| `defensive_pct` | 95.5% | DEFANSIF eşiği |
| `offensive_pct` | 92.7% | OFANSIF eşiği |
| `soft_derisk_threshold` | 120% | Soft de-risk başlangıcı |
| `hard_derisk_threshold` | 130% | Hard de-risk başlangıcı |

## 20.2 Karbotu Filtreleri

### LONGS:

| Step | Fbtot Range | Pahalılık Filter | Lot % |
|------|-------------|------------------|-------|
| 2 | < 1.10 | > -0.10 | 50% |
| 3 | 1.11 - 1.45 | -0.05 to +0.04 | 25% |
| 4 | 1.11 - 1.45 | > +0.05 | 50% |
| 5 | 1.46 - 1.85 | +0.05 to +0.10 | 25% |
| 6 | 1.46 - 1.85 | > +0.10 | 50% |
| 7 | 1.86 - 2.10 | > +0.20 | 25% |

### SHORTS:

| Step | SFStot Range | Ucuzluk Filter | Lot % |
|------|--------------|----------------|-------|
| 9 | > 1.70 | < +0.10 | 50% |
| 10 | 1.40 - 1.69 | -0.04 to +0.05 | 25% |
| 11 | 1.40 - 1.69 | < -0.05 | 50% |
| 12 | 1.10 - 1.39 | -0.04 to +0.05 | 25% |
| 13 | 1.10 - 1.39 | < -0.05 | 50% |

## 20.3 JFIN Parametreleri

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| `selection_percent` | 10% | TUMCSV seçim yüzdesi |
| `min_selection` | 2 | Minimum sembol/grup |
| `heldkuponlu_pair_count` | 16 | HELDKUPONLU özel sayısı |
| `long_percent` | 25% | Top %X LONG için |
| `long_multiplier` | 1.5 | Ortalama × çarpanı |
| `short_percent` | 25% | Bottom %X SHORT için |
| `short_multiplier` | 0.7 | Ortalama × çarpanı |
| `max_short` | 3 | Grup başına max SHORT |
| `company_limit_divisor` | 1.6 | max = total / 1.6 |
| `alpha` | 3 | Lot dağıtım ağırlığı |
| `total_long_rights` | 28,000 | Toplam long lot hakkı |
| `total_short_rights` | 12,000 | Toplam short lot hakkı |

## 20.4 AddNewPos Thresholds

| Portfolio % | MAXALW × | Portfolio % |
|-------------|----------|-------------|
| < 1% | 0.50 | 5% |
| < 3% | 0.40 | 4% |
| < 5% | 0.30 | 3% |
| < 7% | 0.20 | 2% |
| < 10% | 0.10 | 1.5% |
| ≥ 10% | 0.05 | 1% |

## 20.5 Order Lifecycle TTL

| Category | TTL (saniye) |
|----------|--------------|
| `LT_TRIM` | 120 |
| `MM_CHURN` | 60 |
| `ADDNEWPOS` | 180 |
| `KARBOTU` | 120 |
| `REDUCEMORE` | 90 |
| `HARD_DERISK` | 30 |
| `CLOSE_EXIT` | 15 |
| `DEFAULT` | 90 |

## 20.6 REV Order Targets

| Senaryo | Target | Açıklama |
|---------|--------|----------|
| INCREASE | $0.04 | Take Profit |
| DECREASE | $0.06 | Reload Save |

## 20.7 Truth Tick Filtreleri

| Parametre | Değer |
|-----------|-------|
| `min_lot_ignore` | 15 |
| `fnra_allowed_sizes` | 100, 200 only |
| `bucket_size (ADV ≥ 100k)` | $0.03 |
| `bucket_size (ADV ≥ 50k)` | $0.05 |
| `bucket_size (ADV ≥ 10k)` | $0.07 |
| `bucket_size (ADV < 10k)` | $0.09 |

## 20.8 Mental Model V1

| Parametre | Değer |
|-----------|-------|
| `hard_threshold_pct` | 130% |
| `soft_ratio` | 12/13 (≈92.3%) |
| `Amax` | 100 |
| `Asoft` | 20 |
| `pn` | 1.25 |
| `q` | 2.14 |
| `ps` | 1.50 |
| `min_trade_lot` | 200 |
| `no_trade_below_raw` | 100 |
| `post_trade_hold_min` | 200 |

## 20.9 Pricing Formulas

| Order Type | Formula |
|------------|---------|
| BB (Bid Buy) | `bid + (spread × 0.15)` |
| FB (Front Buy) | `last + $0.01` |
| AB (Ask Buy) | `ask + $0.01` |
| SAS (Ask Sell) | `ask - (spread × 0.15)` |
| SFS (Front Sell) | `last - $0.01` |
| BS (Bid Sell) | `bid - $0.01` |

## 20.10 Final Score Formulas

| Score | Formula |
|-------|---------|
| `Final_BB_skor` | `FINAL_THG - 1000 × bid_buy_ucuzluk` |
| `Final_FB_skor` | `FINAL_THG - 1000 × front_buy_ucuzluk` |
| `Final_SAS_skor` | `SHORT_FINAL - 1000 × ask_sell_pahalilik` |
| `Final_SFS_skor` | `SHORT_FINAL - 1000 × front_sell_pahalilik` |

---

# SONUÇ

Bu doküman, Quant Engine'in tüm mekanizmalarını, sayısal değerlerini ve işleyiş mantığını detaylı olarak açıklamaktadır. Her bölüm, ilgili kod dosyalarından ve config dosyalarından doğrudan alınan bilgilerle desteklenmektedir.

Sistemin ana bileşenleri:
1. **Exposure Management**: OFANSIF/DEFANSIF modlar ile risk kontrolü
2. **Position Tracking**: Befday/Current/Potential Triad ve 8'li taksonomi
3. **Scoring**: GORT, Fbtot, SFStot, Ucuzluk/Pahalılık hesaplamaları
4. **Decision Engines**: Karbotu, AddNewPos, ReduceMore, LT Trim, MM Churn
5. **Order Management**: REV orders, lifecycle, TTL, selective cancel
6. **Data Infrastructure**: DataFabric, Truth Ticks, QeBench

Her bileşen, birbirleriyle entegre çalışarak otomatik trading kararları üretir ve uygular.

---

*Doküman Tarihi: 2026-01-25*
*Version: 2.0*

