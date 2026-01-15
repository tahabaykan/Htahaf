# Two-Tier Grouping System - Detaylı Dokümantasyon

## 📋 GENEL BAKIŞ

Quant Engine'de **iki katmanlı gruplama sistemi** kullanılır. Bu sistem, preferred stock'ların doğal davranış rejimlerini korurken, heldkuponlu grubu için özel coupon-band bazlı alt-gruplamayı sağlar.

---

## 🎯 İKİ KATMANLI YAPI

### 1️⃣ PRIMARY GROUP = FILE_GROUP (Ana Strateji Rejimi)

**Ne Yapar?**
- Ana davranış karakteristiklerini belirler
- Strategy regime'i tanımlar
- Mean-reversion ve sensitivity rejimini belirler

**Örnekler (Janall'dan birebir):**
- `heldkuponlu` - Fixed coupon, no maturity
- `heldff` - Fixed-to-floating
- `helddeznff` - Dezenflasyon, no fixed-to-floating
- `heldnff` - No fixed-to-floating
- `heldflr` - Floating rate (NOT "flr", it's "heldflr")
- `heldgarabetaltiyedi` - Garantili, altı yedi yıl
- `heldkuponlukreciliz` - Kuponlu, kredi riski düşük
- `heldkuponlukreorta` - Kuponlu, kredi riski orta
- `heldotelremorta` - Overnight repo, medium term
- `heldsolidbig` - Solid, big issuers
- `heldtitrekhc` - Titrek, high credit
- `heldbesmaturlu` - Beş yıl maturiteli
- `heldcilizyeniyedi` - Ciliz, yeni yedi
- `heldcommonsuz` - Common stock yok
- `highmatur` - High maturity
- `notcefilliquid` - Not çok filliquid
- `notbesmaturlu` - Not beş yıl maturiteli
- `nottitrekhc` - Not titrek, high credit
- `salakilliquid` - Salak, illiquid
- `shitremhc` - Shit, rem, high credit
- `rumoreddanger` - Rumored/dangerous

**Toplam:** ~22 ana grup

**Belirlediği Özellikler:**
- Maturity yapısı (fixed maturity vs perpetual)
- Coupon tipi (fixed vs floating)
- Issuer kalitesi
- Sektörel risk
- Likidite profili

---

### 2️⃣ SECONDARY GROUP = CGRUP (SADECE kuponlu gruplar için)

**Ne Yapar?**
- Kupon bandını temsil eder
- **SADECE** kuponlu gruplar için kullanılır: `heldkuponlu`, `heldkuponlukreciliz`, `heldkuponlukreorta`
- Diğer tüm gruplar CGRUP'u **ignore eder**

**Janall'dan:**
```python
kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
```

**Örnekler:**
- `C400` - 4.00% coupon band
- `C425` - 4.25% coupon band
- `C450` - 4.50% coupon band
- `C475` - 4.75% coupon band
- `C500` - 5.00% coupon band
- `C525` - 5.25% coupon band
- `C550` - 5.50% coupon band
- `C575` - 5.75% coupon band
- `C600` - 6.00% coupon band

**Neden Sadece Kuponlu Gruplar?**
- Fixed coupon
- Maturity yok
- Duration ve rate sensitivity tamamen coupon'a bağlı
- C400 ≠ C550 (farklı benchmark, farklı davranış)
- Janall'da bu 3 grup (`heldkuponlu`, `heldkuponlukreciliz`, `heldkuponlukreorta`) CGRUP'a göre split edilir

---

## 🔧 KOD YAPISI

### grouping.py

```python
# PRIMARY GROUP çözümleme
def resolve_primary_group(static_row: Dict[str, Any]) -> Optional[str]:
    """
    PRIMARY GROUP'u çözümler (file_group veya GROUP kolonundan).
    """
    # Priority: GROUP > file_group > group
    # Returns: "heldff", "heldkuponlu", "heldsolidbig", etc.
```

```python
# SECONDARY GROUP çözümleme
def resolve_secondary_group(static_row: Dict[str, Any], primary_group: str) -> Optional[str]:
    """
    SECONDARY GROUP'u çözümler (CGRUP).
    SADECE heldkuponlu için kullanılır, diğerleri için None döner.
    """
    if primary_group != "heldkuponlu":
        return None  # CGRUP ignored for other groups
    # Returns: "c400", "c425", etc. or None
```

```python
# Full group key çözümleme
def resolve_group_key(static_row: Dict[str, Any]) -> Optional[str]:
    """
    Full group key'i çözümler.
    - heldkuponlu + CGRUP → "heldkuponlu:c400"
    - Other groups → "heldff", "heldsolidbig", etc.
    """
```

---

### benchmark_engine.py

```python
def get_benchmark_formula(
    static_data: Optional[Dict[str, Any]] = None,
    primary_group: Optional[str] = None,
    secondary_group: Optional[str] = None
) -> Dict[str, float]:
    """
    Benchmark formülünü iki katmanlı gruplamaya göre döndürür.
    
    Logic:
    1. PRIMARY GROUP = heldkuponlu?
       → SECONDARY GROUP (CGRUP) kullan → C400, C425, C450, etc. formülleri
    2. PRIMARY GROUP != heldkuponlu?
       → PRIMARY GROUP formülü kullan (CGRUP ignored)
    3. Fallback → default formula (PFF: 1.0)
    """
```

**Örnek Kullanım:**
```python
# heldkuponlu + C400
formula = benchmark_engine.get_benchmark_formula(
    static_data={'GROUP': 'heldkuponlu', 'CGRUP': 'C400'}
)
# Returns: {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08, 'IEI': 0.0}

# heldff (CGRUP ignored)
formula = benchmark_engine.get_benchmark_formula(
    static_data={'GROUP': 'heldff', 'CGRUP': 'C400'}  # CGRUP ignored!
)
# Returns: {'PFF': 1.0} (heldff formula from config)
```

---

### group_benchmark.yaml

**Yapı:**
```yaml
# Default (fallback)
default:
  formula:
    PFF: 1.0

# heldkuponlu: CGRUP-based formulas
heldkuponlu:
  c400:
    formula:
      PFF: 0.36
      TLT: 0.36
      IEF: 0.08
      IEI: 0.0
  c425:
    formula:
      PFF: 0.368
      TLT: 0.34
      IEF: 0.092
      IEI: 0.0
  # ... other CGRUP values
  default:  # Fallback for heldkuponlu without CGRUP
    formula:
      PFF: 1.0

# Other primary groups: group-specific formulas
heldff:
  formula:
    PFF: 1.0
# ... other groups
```

---

## 📊 BENCHMARK HESAPLAMA

### Composite Benchmark

Benchmark değeri, formüldeki ETF'lerin ağırlıklı toplamıdır:

```
benchmark_value = Σ(ETF_price * coefficient)
```

**Örnek (heldkuponlu:C400):**
```
benchmark_last = (PFF_last * 0.36) + (TLT_last * 0.36) + (IEF_last * 0.08)
benchmark_prev_close = (PFF_prev_close * 0.36) + (TLT_prev_close * 0.36) + (IEF_prev_close * 0.08)
benchmark_chg = benchmark_last - benchmark_prev_close
```

---

## 🔄 KULLANIM AKIŞI

### 1. Static Data Yükleme
```python
static_data = static_store.get_static_data(symbol)
# Contains: GROUP (primary), CGRUP (secondary, only for heldkuponlu)
```

### 2. Group Key Çözümleme
```python
from app.market_data.grouping import resolve_group_key

group_key = resolve_group_key(static_data)
# heldkuponlu:C400 → primary="heldkuponlu", secondary="c400"
# heldff → primary="heldff", secondary=None
```

### 3. Benchmark Formülü Al
```python
from app.market_data.benchmark_engine import BenchmarkEngine

benchmark_engine = BenchmarkEngine()
formula = benchmark_engine.get_benchmark_formula(static_data=static_data)
# Returns: {ETF: coefficient} dict
```

### 4. Benchmark Hesapla
```python
benchmark_result = benchmark_engine.compute_benchmark_change(
    etf_data_store=etf_data_store,
    static_data=static_data
)
# Returns: {
#   'benchmark_chg': float,
#   'benchmark_chg_percent': float,
#   'benchmark_symbol': 'PFF',
#   'benchmark_formula': {ETF: coefficient},
#   'benchmark_last': float,
#   'benchmark_prev_close': float
# }
```

---

## ✅ DOĞRU KULLANIM KURALLARI

### ✅ DOĞRU
```python
# heldkuponlu için CGRUP kullan
if primary_group == "heldkuponlu":
    secondary_group = resolve_secondary_group(static_data, primary_group)
    # secondary_group = "c400", "c425", etc.
    formula = benchmark_engine.get_benchmark_formula(
        primary_group=primary_group,
        secondary_group=secondary_group
    )

# Diğer gruplar için CGRUP ignore
else:
    formula = benchmark_engine.get_benchmark_formula(
        primary_group=primary_group,
        secondary_group=None  # CGRUP ignored!
    )
```

### ❌ YANLIŞ
```python
# CGRUP'u global grup gibi kullanma!
if cgrup:  # ❌ YANLIŞ - CGRUP sadece heldkuponlu için!
    formula = get_formula_by_cgrup(cgrup)

# Tüm gruplar için CGRUP'a göre split yapma!
for cgrup in all_cgrups:  # ❌ YANLIŞ - CGRUP sadece heldkuponlu için!
    group_symbols = filter_by_cgrup(symbols, cgrup)
```

---

## 🎯 GORT UYUMLULUĞU

GORT (Group Relative Trend) hesaplaması zaten bu yapıyı doğru kullanıyor:

```python
# gorter.py mantığı
if group == "heldkuponlu":
    # CGRUP'a göre gruplama
    for cgrup, group_df in heldkuponlu_data.groupby('CGRUP'):
        # GORT hesapla (CGRUP bazlı ortalama)
else:
    # Grup bazlı gruplama (CGRUP ignored)
    for group_name, group_df in other_groups_data.groupby('GROUP'):
        # GORT hesapla (grup bazlı ortalama)
```

Quant Engine'deki grouping.py ve benchmark_engine.py bu mantığı aynen takip eder.

---

## 📝 STATIC DATA KOLONLARI

`janalldata.csv` dosyasında:
- **GROUP**: PRIMARY GROUP (file_group) - Zorunlu
- **CGRUP**: SECONDARY GROUP - Sadece heldkuponlu için anlamlı, diğerleri için ignore edilir

**Örnek:**
```csv
PREF IBKR,GROUP,CGRUP,...
KEY PRL,heldff,,  # CGRUP ignored
METCZ,heldkuponlu,C400,  # CGRUP used
BAC PRN,heldkuponlu,C500,  # CGRUP used
```

---

## 🔍 DEBUGGING

### Group Key Kontrolü
```python
from app.market_data.grouping import resolve_primary_group, resolve_secondary_group, resolve_group_key

static_data = static_store.get_static_data(symbol)
primary = resolve_primary_group(static_data)
secondary = resolve_secondary_group(static_data, primary)
group_key = resolve_group_key(static_data)

print(f"Symbol: {symbol}")
print(f"Primary Group: {primary}")
print(f"Secondary Group: {secondary}")
print(f"Full Group Key: {group_key}")
```

### Benchmark Formülü Kontrolü
```python
formula = benchmark_engine.get_benchmark_formula(static_data=static_data)
print(f"Benchmark Formula: {formula}")
```

---

## 🎯 SONUÇ

Bu iki katmanlı yapı sayesinde:

✅ **22 ana dosya grubu** korunur
✅ **heldkuponlu özel durumu** doğru modellenir
✅ **CGRUP global grup karmaşası** biter
✅ **Janall'daki fixed-income sezgisi** engine'e taşınır
✅ **Benchmark & sensitivity hataları** engellenir
✅ **GORT mantığı ile birebir uyumlu**

---

*Son Güncelleme: 2025-01-XX*

