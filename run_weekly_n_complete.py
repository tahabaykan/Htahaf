import subprocess
import sys

scripts = [
    "nibkrtry.py",                    # 1. ek*.csv → sek*.csv (IBKR'den güncel veriler)
    "nnormalize_data.py",             # 2. sek*.csv → nek*.csv (Normalize işlemleri)
    "nmaster_processor.py",           # 3. nek*.csv → yek*.csv (Cally kolonları + Treasury)
    "nbefore_common_adv.py",          # 4. yek*.csv → advek*.csv (ADV verileri)
    "ncommon_stocks.py",              # 5. advek*.csv → comek*.csv (Common stocks)
    "ncalculate_scores.py",           # 6. comek*.csv → allcomek.csv (Skor hesaplamaları)
    "calculate_allcomek_solidity.py", # 7. allcomek.csv → allcomek_sld.csv (Solidity hesaplamaları)
    "create_sldek_files.py",          # 8. allcomek_sld.csv → sldek*.csv (Sldek dosyaları)
    "nfill_missing_solidity_data.py", # 9. sldek*.csv → sldfek*.csv (Solidity verileri)
    "nmarket_risk_analyzer.py",       # 10. Market risk analizi
    "ncalculate_thebest.py",          # 11. advek*.csv → finek*.csv (FINAL THG hesaplamaları)
    "create_ssfinek_files.py",        # 12. finek*.csv → ssfinek*.csv (SSFINEK dosyaları)
    "nget_short_fee_rates.py",        # 13. Short fee rate verileri
    "noptimize_shorts.py",            # 14. Short optimizasyonu
]

for script in scripts:
    print(f"Çalıştırılıyor: {script}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        print(f"Hata oluştu, script durdu: {script}")
        break
    print(f"Bitti: {script}\n")
print("Tüm işlemler tamamlandı.") 