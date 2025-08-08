import subprocess
import sys
import os
from datetime import datetime
import pandas as pd
from simulation_helper import get_simulation_filename, is_simulation_mode

def run_script_simple(script_name):
    """
    Script'i basit şekilde çalıştırır
    """
    print(f"RUNNING {script_name} çalıştırılıyor...")
    
    try:
        # ntreyield.py için özel ayarlar
        if script_name == "ntreyield.py":
            # ntreyield.py için daha uzun timeout ve farklı ayarlar
            result = subprocess.run([sys.executable, script_name], 
                                  timeout=600,  # 10 dakika
                                  text=True)
        else:
            # Diğer scriptler için normal ayarlar
            result = subprocess.run([sys.executable, script_name], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=300)  # 5 dakika
        
        if result.returncode == 0:
            print(f"OK {script_name} başarıyla tamamlandı")
            return True
        else:
            print(f"ERROR {script_name} çalıştırılırken hata: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT {script_name} timeout oldu")
        return False
    except Exception as e:
        print(f"ERROR {script_name} çalıştırılırken hata: {e}")
        return False

def main():
    """
    Ana master processor fonksiyonu
    """
    print("=== MASTER PROCESSOR BAŞLATILIYOR ===")
    print(f"Başlangıç zamanı: {datetime.now()}")
    
    # Script sırası
    scripts = [
        "create_yek_files.py",                    # 1. nek*.csv → yek*.csv (Cally kolonları eklenir)
        "decntreyield.py",                           # 2. Treasury yield'ları güncelle (US15Y dahil)
        "nyield_calculator.py",                   # 3. NCOMP Count + Cally değerleri hesaplanır (15Y dahil)
        "update_normal_treasury_benchmark.py",    # 4. Normal Treasury benchmark'ları (yeni kupon aralıkları)
        "update_adjusted_treasury_benchmark.py",  # 5. Adjusted Treasury benchmark'ları (US15Y dahil)
        "add_adj_risk_premium.py"                 # 6. Adj Risk Premium (US15Y dahil)
    ]
    
    successful_scripts = 0
    total_scripts = len(scripts)
    
    for i, script in enumerate(scripts, 1):
        print(f"\n--- Adım {i}/{total_scripts}: {script} ---")
        
        if run_script_simple(script):
            successful_scripts += 1
        else:
            print(f"WARNING {script} başarısız oldu, devam ediliyor...")
    
    print(f"\n=== MASTER PROCESSOR TAMAMLANDI ===")
    print(f"Bitiş zamanı: {datetime.now()}")
    print(f"Başarılı scriptler: {successful_scripts}/{total_scripts}")
    
    if successful_scripts == total_scripts:
        print("SUCCESS TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI!")
    else:
        print(f"WARNING {total_scripts - successful_scripts} script başarısız oldu")

if __name__ == "__main__":
    main() 