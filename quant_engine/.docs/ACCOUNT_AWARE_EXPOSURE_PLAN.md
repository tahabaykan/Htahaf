# 🎯 ACCOUNT-AWARE EXPOSURE SYSTEM - İMPLEMENTASYON PLANI

## ŞU ANKİ DURUM

### ✅ ZATEN ACCOUNT-AWARE OLANLAR:
1. **Exposure Calculator** - `calculate_exposure_for_account(account_id)` ✅
2. **Position Snapshots** - Her hesap için ayrı positions ✅
3. **ADDNEWPOS Settings** - Account-specific (방금 yaptık) ✅

### ❌ ACCOUNT-AWARE OLMAYLANLAR:
1. **Exposure Thresholds** - Tek global pot_max ❌
2. **Exposure Adjuster UI** - Tek global adjuster ❌

---

## EXPOSURE THRESHOLD SERVICE - ACCOUNT-AWARE

### Şu Anki Yapı:
```python
# exposure_threshold_service.py
class ExposureThresholdService:
    def __init__(self):
        self.thresholds = {
            'current_threshold': 90.0,
            'potential_threshold': 95.0,
            'pot_max': 1200000.0  # GLOBAL!
        }
```

### Yeni Yapı (Account-Aware):
```python
class ExposureThresholdService:
    def __init__(self):
        self.accounts_thresholds = {
            'HAMPRO': {
                'current_threshold': 90.0,
                'potential_threshold': 95.0,
                'pot_max': 1200000.0
            },
            'IBKR_PED': {
                'current_threshold': 92.0,
                'potential_threshold': 96.0,
                'pot_max': 800000.0
            },
            'IBKR_GUN': {
                'current_threshold': 88.0,
                'potential_threshold': 94.0,
                'pot_max': 600000.0
            }
        }
```

---

## DEĞİŞTİRİLECEK DOSYALAR

### 1. **exposure_threshold_service.py** ✅ 
- Account-aware storage
- get_thresholds(account_id)
- save_thresholds(account_id, ...)
- CSV: `exposure_thresholds_v2.json`

### 2. **API Routes** ✅
- GET /api/exposure/thresholds → account_id inject
- POST /api/exposure/thresholds → account_id inject

### 3. **RUNALL/XNL Engines** ✅
- Exposure hesaplarken account-specific pot_max kullan

### 4. **Frontend - Exposure Adjuster** ✅
- Account selector ile sync
- Her hesap için ayrı adjuster göster

---

## IMPLEMENTATION ORDER

1. ✅ exposure_threshold_service_v2.py (account-aware)
2. ✅ API routes update (account injection)
3. ✅ RUNALL/XNL engine exposure calls
4. ✅ Frontend ExposureAdjuster component

---

## MIGRATION PLAN

**V1 → V2:**
- Eski `exposure_thresholds.csv` varsa → Tüm hesaplara aynı değerleri kopyala
- Yeni `exposure_thresholds_v2.json` kullan

**Backward Compatibility:**
- Eski API calls → Default account (from context)
- Yeni API calls → Explicit account_id

---

## SONRAKİ ADIMLAR

1. exposure_threshold_service_v2.py yaz
2. API routes güncelle
3. Frontend güncelle
4. Test et!

BAŞLIYORUM! 🚀
