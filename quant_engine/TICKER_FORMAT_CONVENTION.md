# 🔑 TICKER FORMAT CONVENTION — ZORUNLU KURAL

## İki Farklı Ticker Formatı Vardır

| Format | Örnek | Kullanım Alanı |
|--------|-------|----------------|
| **Hammer (IBKR Gateway)** | `WBS-F`, `CIM-B`, `MFA-C` | Market Data + Hammer emirleri |
| **PREF_IBKR (Display)** | `WBS PRF`, `CIM PRB`, `MFA PRC` | IBKR Gateway emirleri/pozisyonları + UI |

### Dönüşüm Kuralı
```
PREF_IBKR → Hammer:   "WBS PRF"  →  "WBS-F"    (PR → -, F değişmez)
Hammer → PREF_IBKR:   "WBS-F"   →  "WBS PRF"   (- → PR, F değişmez)
```

Dönüşüm `SymbolMapper` sınıfı ile yapılır: `app/live/symbol_mapper.py`

---

## KESİN KURALLAR

### 1. MARKET DATA — HER ZAMAN HAMMER FORMAT

**L1, L2, Truth Tick** verileri **HER ZAMAN** Hammer Pro üzerinden alınır.
Bu veriler her iki hesap için de (HAMPRO + IBKR_PED) aynı kaynaktan gelir.

```
✅ Redis Key:  market:l1:WBS-F       (Hammer format)
✅ Redis Key:  tt:ticks:WBS-F        (Hammer format)
✅ Redis Key:  truthtick:latest:WBS-F (Hammer format)

❌ YANLIŞ:     market:l1:WBS PRF     (PREF_IBKR format — KULLANMA!)
❌ YANLIŞ:     tt:ticks:WBS PRF      (PREF_IBKR format — KULLANMA!)
```

**Neden?** Market data Hammer Pro'dan geliyor. Hammer `WBS-F` formatıyla çalışır.
Hangi hesapta olursa olsun (HAMPRO veya IBKR_PED), market data aynı kaynaktan gelir.

### 2. EMİR ve POZİSYON — HESABA GÖRE DEĞİŞİR

| Hesap | Emir/Pozisyon Formatı | Bağlantı |
|-------|----------------------|----------|
| **HAMPRO** | `WBS-F` (Hammer format) | Hammer Pro API |
| **IBKR_PED** | `WBS PRF` (PREF_IBKR format) | IBKR Gateway |

```
✅ HAMPRO emri:    place_order("WBS-F", SELL, 200)   → Hammer Pro
✅ IBKR_PED emri:  place_order("WBS PRF", SELL, 200) → IBKR Gateway

❌ YANLIŞ:         IBKR'ye "WBS-F" göndermek
❌ YANLIŞ:         Hammer'a "WBS PRF" göndermek
```

### 3. REDİS KEY FORMATI

```
# Market Data (HER ZAMAN Hammer format)
market:l1:{HAMMER}              → market:l1:WBS-F
market_data:snapshot:{HAMMER}   → market_data:snapshot:WBS-F
tt:ticks:{HAMMER}               → tt:ticks:WBS-F
truthtick:latest:{HAMMER}       → truthtick:latest:WBS-F

# Pozisyonlar (HESAP_ID ile birlikte)
psfalgo:positions:{ACCOUNT_ID}  → dict içinde PREF_IBKR format (WBS PRF)

# Engine Verileri (PREF_IBKR format — çünkü janalldata.csv böyle)
befday:{symbol}                 → befday:WBS PRF
minmax:{symbol}                 → minmax:WBS PRF
```

---

## SymbolMapper Kullanımı

```python
from app.live.symbol_mapper import SymbolMapper

# PREF_IBKR → Hammer
SymbolMapper.to_hammer_symbol("WBS PRF")   # → "WBS-F"
SymbolMapper.to_hammer_symbol("CIM PRB")   # → "CIM-B"
SymbolMapper.to_hammer_symbol("SPY")       # → "SPY" (ETF, değişmez)

# Hammer → PREF_IBKR
SymbolMapper.to_display_symbol("WBS-F")    # → "WBS PRF"
SymbolMapper.to_display_symbol("CIM-B")    # → "CIM PRB"
SymbolMapper.to_display_symbol("SPY")      # → "SPY" (ETF, değişmez)
```

---

## ⚠️ YAYGIN HATA

**L1 lookup'ta PREF_IBKR format kullanmak:**
```python
# ❌ YANLIŞ — L1 key PREF_IBKR formatında aranıyor
redis.get(f"market:l1:{symbol}")  # symbol = "WBS PRF" → BULAMAZ!

# ✅ DOĞRU — Önce Hammer formatına çevir
from app.live.symbol_mapper import SymbolMapper
hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
redis.get(f"market:l1:{hammer_sym}")  # hammer_sym = "WBS-F" → BULUR!
```

**Fill'den gelen sembol adını L1'de aramak:**
```python
# Fill'den gelen sembol zaten Hammer formatında olabilir (WBS-F)
# Ama Redis key eğer PREF_IBKR formatında yazılmışsa BULAMAZ!
# Bu durumda her iki formatı da dene.
```

---

## SONUÇ

1. **Market data Redis key'leri** → Hammer format (`WBS-F`)
2. **L1 lookup** → Her zaman Hammer format kullan
3. **IBKR emir/pozisyon** → PREF_IBKR format (`WBS PRF`)
4. **Hammer emir/pozisyon** → Hammer format (`WBS-F`)
5. **SymbolMapper** → Format dönüşümü için TEK kaynak
