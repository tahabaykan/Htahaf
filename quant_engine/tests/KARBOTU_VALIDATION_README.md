# KARBOTU v1 Validation Harness

## 📋 GENEL BAKIŞ

Bu validation harness, KARBOTU v1 decision engine'inin Janall'daki davranışı birebir üretip üretmediğini test eder.

**Amaç:**
- KARBOTU v1'in doğruluğunu validate etmek
- Janall ile farkları tespit etmek
- Human-readable rapor üretmek

---

## 1. KULLANIM

### 1.1. Validation Çalıştırma

```bash
# Option 1: Python module olarak
python -m quant_engine.tests.karbotu_validation_runner

# Option 2: Script olarak
python quant_engine/tests/karbotu_validation_runner.py

# Option 3: Test file'ı direkt
python quant_engine/tests/test_karbotu_validation.py
```

### 1.2. Output

Validation çalıştırıldığında:
1. **Console Output**: Test sonuçları console'a yazdırılır
2. **Report File**: `quant_engine/tests/karbotu_validation_report.txt` dosyasına kaydedilir

---

## 2. TEST CASE'LER

### 2.1. Test Case 1: Cooldown Filter
**Senaryo**: Position tüm filtreleri geçer ama cooldown aktif.

**Input:**
- WFC PRY, 400 lots
- Fbtot: 1.05 ✅
- Ask Sell Pahalılık: 0.02 ✅
- GORT: 0.5 ✅
- Cooldown: 2 dakika önce decision var ❌

**Expected**: FILTERED (cooldown)
**Janall**: SELL (cooldown yok)

**Fark**: Quant_Engine'de cooldown var, Janall'da yok.

---

### 2.2. Test Case 2: Threshold Edge Case
**Senaryo**: Ask Sell Pahalılık = -0.08 (edge case).

**Input:**
- BAC PRM, 300 lots
- Fbtot: 1.08 ✅
- Ask Sell Pahalılık: -0.08 (threshold: > -0.10) ✅
- GORT: 0.3 ✅

**Expected**: SELL (-0.08 > -0.10)
**Janall**: FILTERED (threshold farkı olabilir)

**Fark**: Threshold'ları kontrol et!

---

### 2.3. Test Case 3: Missing Metrics
**Senaryo**: Metrics eksik (fbtot, ask_sell_pahalilik, gort).

**Input:**
- JPM PRL, 500 lots
- Fbtot: None ❌
- Ask Sell Pahalılık: None ❌
- GORT: None ❌

**Expected**: FILTERED (metrics not available)
**Janall**: FILTERED (metrics not available)

**Fark**: Yok (aynı davranış).

---

### 2.4. Test Case 4: Perfect SELL Case
**Senaryo**: Tüm filtreleri geçen perfect case.

**Input:**
- MS PRK, 600 lots
- Fbtot: 1.05 ✅
- Ask Sell Pahalılık: 0.05 ✅
- GORT: 0.8 ✅
- Qty: 600 ✅
- No cooldown ✅

**Expected**: SELL (50% lot, 300 lots)
**Janall**: SELL (50% lot, 300 lots)

**Fark**: Yok (aynı davranış).

---

### 2.5. Test Case 5: GORT Filter Fail
**Senaryo**: GORT filter başarısız (Step 1).

**Input:**
- C PRJ, 400 lots
- Fbtot: 1.05 ✅
- Ask Sell Pahalılık: 0.02 ✅
- GORT: -1.5 (NOT > -1) ❌

**Expected**: FILTERED (GORT <= -1.0)
**Janall**: FILTERED (GORT <= -1)

**Fark**: Yok (aynı davranış).

---

### 2.6. Test Case 6: Fbtot Filter Fail
**Senaryo**: Fbtot filter başarısız (Step 2).

**Input:**
- GS PRA, 500 lots
- Fbtot: 1.15 (NOT < 1.10) ❌
- Ask Sell Pahalılık: 0.05 ✅
- GORT: 0.6 ✅

**Expected**: FILTERED (Fbtot >= 1.10)
**Janall**: FILTERED (Fbtot >= 1.10)

**Fark**: Yok (aynı davranış).

---

### 2.7. Test Case 7: Qty Filter Fail
**Senaryo**: Quantity filter başarısız (Step 2).

**Input:**
- PNC PRP, 50 lots
- Fbtot: 1.05 ✅
- Ask Sell Pahalılık: 0.05 ✅
- GORT: 0.4 ✅
- Qty: 50 (NOT >= 100) ❌

**Expected**: FILTERED (Qty < 100)
**Janall**: FILTERED (Qty < 100)

**Fark**: Yok (aynı davranış).

---

### 2.8. Test Case 8: Multiple Positions
**Senaryo**: Birden fazla position, mixed outcomes.

**Input:**
- WFC PRY: Perfect SELL ✅
- BAC PRM: GORT filter fail ❌
- JPM PRL: Missing metrics ❌
- MS PRK: Perfect SELL ✅

**Expected**: 2 SELL, 2 FILTERED
**Janall**: 2 SELL, 2 FILTERED

**Fark**: Yok (aynı davranış).

---

## 3. REPORT FORMAT

### 3.1. Report Structure

```
================================================================================
KARBOTU v1 VALIDATION REPORT
================================================================================

Total Tests: 8
Passed: 7
Failed: 1

--------------------------------------------------------------------------------
Test 1: Test Case 1: Cooldown Filter - ❌ FAIL
Category: COOLDOWN
Description: Position passes all filters but cooldown is active
Janall Behavior: SELL (cooldown yok)

Actual Results:
  Decisions: 0
  Filtered: 1

  FILTERED Positions:
    WFC PRY:
      Step: 2
      Reasons: Cooldown active (2.0 minutes)

  Differences:
    ❌ WFC PRY: Action mismatch - Expected FILTERED, Got SELL

  Step Summary:
    Step 1 (GORT Filter):
      Total: 1
      Eligible: 1
      Filtered: 0
    Step 2 (Fbtot < 1.10):
      Total: 1
      Decisions: 0
      Filtered: 1

...
```

### 3.2. Report Interpretation

- ✅ **PASS**: Actual result matches expected outcome
- ❌ **FAIL**: Actual result differs from expected outcome
- **Differences**: Detaylı fark listesi
- **Step Summary**: Her step için istatistikler

---

## 4. YENİ TEST CASE EKLEME

### 4.1. Test Case Oluşturma

```python
def create_test_fixture_X() -> ValidationTestCase:
    """Test Case X: Description"""
    positions = [
        PositionSnapshot(
            symbol="SYMBOL",
            qty=400.0,
            avg_price=24.00,
            current_price=24.50,
            ...
        )
    ]
    
    metrics = {
        "SYMBOL": SymbolMetrics(
            symbol="SYMBOL",
            fbtot=1.05,
            ask_sell_pahalilik=0.02,
            ...
        )
    }
    
    request = DecisionRequest(
        positions=positions,
        metrics=metrics,
        ...
    )
    
    return ValidationTestCase(
        name="Test Case X: Name",
        description="Description",
        input_request=request,
        expected_outcome={
            'decisions_count': 1,
            'filtered_count': 0,
            'symbols': {
                'SYMBOL': {
                    'action': 'SELL',
                    'reason': 'Fbtot < 1.10'
                }
            }
        },
        janall_behavior="SELL",
        category="CATEGORY"
    )
```

### 4.2. Test Case Ekleme

```python
# test_karbotu_validation.py içinde
harness.add_test_case(create_test_fixture_X())
```

---

## 5. FARK ANALİZİ

### 5.1. Beklenen Farklar

1. **Cooldown**: Quant_Engine'de cooldown var, Janall'da yok
2. **Confidence**: Quant_Engine'de confidence score var, Janall'da yok
3. **Threshold Precision**: Float comparison'lar farklı olabilir

### 5.2. Beklenmeyen Farklar

1. **Filter Logic**: Filtreleme mantığı farklıysa → BUG
2. **Lot Calculation**: Lot hesaplama farklıysa → BUG
3. **Step Order**: Step sırası farklıysa → BUG

---

## 6. TROUBLESHOOTING

### 6.1. Test Case Fail Ediyor

**Kontrol Et:**
1. Config dosyası doğru mu? (`psfalgo_rules.yaml`)
2. Threshold'lar doğru mu?
3. Cooldown manager initialized mı?
4. Metrics format doğru mu?

### 6.2. Cooldown Test Fail Ediyor

**Çözüm:**
```python
# Test case'de cooldown'u aktif et:
from app.psfalgo.decision_cooldown import get_decision_cooldown_manager
from datetime import timedelta

cooldown_manager = get_decision_cooldown_manager()
if cooldown_manager:
    cooldown_ts = datetime.now() - timedelta(minutes=2)
    cooldown_manager.set_decision_ts("SYMBOL", cooldown_ts)
```

### 6.3. Metrics Missing

**Kontrol Et:**
- `SymbolMetrics` object'inde tüm required fields var mı?
- `None` değerler doğru mu?

---

## 7. SONUÇ

Bu validation harness:
- ✅ KARBOTU v1'in doğruluğunu validate eder
- ✅ Janall ile farkları tespit eder
- ✅ Human-readable rapor üretir
- ✅ Yeni test case'ler eklenebilir

**Kullanım**: Validation çalıştır → Raporu oku → Farkları analiz et → Gerekirse düzelt.






