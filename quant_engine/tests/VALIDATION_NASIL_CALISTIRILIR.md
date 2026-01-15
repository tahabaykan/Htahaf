# KARBOTU Validation - Nasıl Çalıştırılır?

## 🚀 HIZLI BAŞLANGIÇ

### Adım 1: Terminal'de Quant_Engine Dizinine Git

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine
```

### Adım 2: Validation'ı Çalıştır

```bash
python -m tests.karbotu_validation_runner
```

VEYA

```bash
python tests/karbotu_validation_runner.py
```

VEYA (eğer yukarıdakiler çalışmazsa)

```bash
python tests/test_karbotu_validation.py
```

---

## 📋 DETAYLI ADIMLAR

### 1. Terminal Aç

Windows'ta:
- `Win + R` → `cmd` veya `powershell`
- Veya VS Code'da terminal aç (`Ctrl + ``)

### 2. Dizine Git

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine
```

### 3. Python Çalıştır

```bash
python -m tests.karbotu_validation_runner
```

---

## 📊 NE OLACAK?

### Console'da Göreceğin:

```
================================================================================
KARBOTU v1 VALIDATION RUNNER
================================================================================

Starting KARBOTU v1 validation...
Running test case: Test Case 1: Cooldown Filter
Running test case: Test Case 2: Threshold Edge Case
...

================================================================================
KARBOTU v1 VALIDATION REPORT
================================================================================

Total Tests: 8
Passed: 7
Failed: 1

--------------------------------------------------------------------------------
Test 1: Test Case 1: Cooldown Filter - ❌ FAIL
...
```

### Dosya Oluşacak:

`quant_engine/tests/karbotu_validation_report.txt`

Bu dosyayı açıp okuyabilirsin.

---

## 🔧 SORUN GİDERME

### Sorun 1: "Module not found"

**Hata:**
```
ModuleNotFoundError: No module named 'tests'
```

**Çözüm:**
```bash
# Proje root dizinine git
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker

# Sonra çalıştır
python -m quant_engine.tests.karbotu_validation_runner
```

### Sorun 2: "Import error"

**Hata:**
```
ImportError: cannot import name 'DecisionRequest'
```

**Çözüm:**
```bash
# PYTHONPATH ekle
set PYTHONPATH=C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker

# Sonra çalıştır
python -m quant_engine.tests.karbotu_validation_runner
```

### Sorun 3: "Config file not found"

**Hata:**
```
KARBOTU rules file not found
```

**Çözüm:**
- `quant_engine/app/config/psfalgo_rules.yaml` dosyasının var olduğundan emin ol
- Dosya yoksa, önceki adımlarda oluşturulmuş olmalı

---

## 📝 ALTERNATİF YÖNTEMLER

### Yöntem 1: Python Script Olarak

```python
# validation_run.py dosyası oluştur
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from quant_engine.tests.test_karbotu_validation import run_validation

if __name__ == "__main__":
    asyncio.run(run_validation())
```

Sonra:
```bash
python validation_run.py
```

### Yöntem 2: VS Code'da Run

1. `test_karbotu_validation.py` dosyasını aç
2. `run_validation()` fonksiyonunu bul
3. Sağ tık → "Run Python File in Terminal"

### Yöntem 3: Jupyter Notebook

```python
import asyncio
from quant_engine.tests.test_karbotu_validation import run_validation

await run_validation()
```

---

## 🎯 EN BASİT YÖNTEM

**Tek komut:**

```bash
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine && python -m tests.karbotu_validation_runner
```

VEYA PowerShell'de:

```powershell
cd C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine; python -m tests.karbotu_validation_runner
```

---

## 📄 RAPORU OKUMA

Validation çalıştıktan sonra:

1. Console'da rapor görünecek
2. `quant_engine/tests/karbotu_validation_report.txt` dosyası oluşacak
3. Bu dosyayı herhangi bir text editor'de açabilirsin

**Rapor Formatı:**
- ✅ PASS: Test geçti
- ❌ FAIL: Test başarısız
- Differences: Farklar listelenir
- Step Summary: Her step için istatistikler

---

## 💡 ÖRNEK ÇIKTI

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

================================================================================
END OF REPORT
================================================================================
```

---

## ✅ BAŞARILI ÇALIŞTI MI?

Eğer şunu görüyorsan **BAŞARILI**:

```
✅ All validation tests passed!
```

Eğer şunu görüyorsan **BAZILARI BAŞARISIZ**:

```
❌ Some validation tests failed. Check report for details.
```

Bu durumda `karbotu_validation_report.txt` dosyasını aç ve farkları incele.




