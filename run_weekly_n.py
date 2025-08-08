import subprocess
import sys
import os
import shutil
import glob

scripts = [
    "nibkrtry.py",
    "nnormalize_data.py",
    "nmaster_processor.py",  # YEK dosyalarını oluşturur ve Cally değerlerini hesaplar
    "nbefore_common_adv.py",
    "ncommon_stocks.py",
    "ncalculate_scores.py",
    "nfill_missing_solidity_data.py",
    "nmarket_risk_analyzer.py",
    "ncalculate_thebest.py",
    "nget_short_fee_rates.py",  # EKHELD dosyalarından short fee rate verilerini çeker
    "noptimize_shorts.py",  # EKHELD dosyalarından en düşük SHORT_FINAL hisselerini bulur
    "ntumcsvport.py",  # SSFINEK dosyalarından LONG/SHORT hisseleri seçer
    "npreviousadd.py",  # SSFINEK dosyalarına prev_close kolonu ekler ve janek_ prefix ile kaydeder
    "merge_csvs.py",  # janek_ssfinek dosyalarını birleştirir ve janalldata.csv oluşturur
]

def copy_csv_files_to_janall():
    """Oluşturulan CSV dosyalarını janall klasörüne kopyala"""
    try:
        # janall klasörünün var olduğundan emin ol
        janall_dir = "janall"
        if not os.path.exists(janall_dir):
            os.makedirs(janall_dir)
            print(f"✅ {janall_dir} klasörü oluşturuldu")
        
        # Tüm CSV dosyalarını bul
        csv_files = glob.glob("*.csv")
        
        for csv_file in csv_files:
            try:
                # Dosyayı janall klasörüne kopyala
                destination = os.path.join(janall_dir, csv_file)
                shutil.copy2(csv_file, destination)
                print(f"📋 {csv_file} → {janall_dir}/")
            except Exception as e:
                print(f"❌ {csv_file} kopyalanırken hata: {e}")
                
    except Exception as e:
        print(f"❌ CSV kopyalama hatası: {e}")

for script in scripts:
    print(f"Çalıştırılıyor: {script}")
    result = subprocess.run([sys.executable, script])
    if result.returncode != 0:
        print(f"Hata oluştu, script durdu: {script}")
        break
    print(f"Bitti: {script}")
    
    # Her script çalıştıktan sonra CSV dosyalarını janall klasörüne kopyala
    print("📋 CSV dosyaları janall klasörüne kopyalanıyor...")
    copy_csv_files_to_janall()
    print()

print("Tüm işlemler tamamlandı.")
print("✅ CSV dosyaları hem ana dizinde hem de janall klasöründe oluşturuldu.")
print("📊 janalldata.csv dosyası GROUP kolonu ile hazır!") 