import subprocess
import sys

scripts = [
    "ibkrtry.py",
    "normalize_data.py",
    "extltib.py",
    "normalize_extlt.py",
    "before_common_adv.py",
    "calculate_scores.py",
    "fill_missing_solidity_data.py",
    "market_risk_analyzer.py",
    "calculate_final_thg_dynamic.py",
    "calculate_extlt.py",
    "calculate_finalextlt.py",
    "calculate_splitextlt.py",
    "merge_group_data.py",
    "optimize_portfolio_positions.py"
]

for script in scripts:
    print(f"Çalıştırılıyor: {script}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        print(f"Hata oluştu, script durdu: {script}")
        break
    print(f"Bitti: {script}\n")
print("Tüm işlemler tamamlandı.")

subprocess.run(["C:/Users/User/AppData/Local/Programs/Python/Python313/python.exe", "c:/Users/User/OneDrive/Masaüstü/Proje/StockTracker/run_daily.py"]) 