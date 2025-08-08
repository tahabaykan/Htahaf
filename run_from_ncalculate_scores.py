import subprocess
import sys

scripts = [
    "nfill_missing_solidity_data.py",
    "nmarket_risk_analyzer.py", 
    "ncalculate_thebest.py",
    "nget_short_fee_rates.py",
    "noptimize_shorts.py",
    "npreviousadd.py",
]

for script in scripts:
    print(f"Çalıştırılıyor: {script}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        print(f"Hata oluştu, script durdu: {script}")
        break
    print(f"Bitti: {script}\n")
print("Tüm işlemler tamamlandı.") 