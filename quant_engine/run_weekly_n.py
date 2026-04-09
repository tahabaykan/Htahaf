import subprocess
import sys
import os
import shutil
import glob

scripts = [
    "nibkrtry.py",
    "ncorrex.py",  # sek CSV dosyalarında TIME TO DIV değerlerini kontrol eder ve CNBC'den ex-div date bilgilerini çekerek düzeltir
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
    "gorter.py",  # janalldata.csv'den her CGRUP için en yüksek ve en düşük 3 GORT değerine sahip hisseleri bulur
]

# Çalışma dizinini kontrol et ve yazdır
print("🚀 RUN WEEKLY N - Haftalık İşlemler Başlatılıyor")
print("=" * 60)
current_dir = os.getcwd()
print(f"🔍 Çalışma dizini: {current_dir}")

# Mevcut dizindeki CSV dosyalarını listele
csv_files = [f for f in os.listdir(current_dir) if f.endswith('.csv')]
print(f"📁 Mevcut dizindeki CSV dosyaları ({len(csv_files)} adet):")
for file in csv_files:
    print(f"  - {file}")
print()

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
        
        print(f"📁 Kopyalanacak CSV dosyaları ({len(csv_files)} adet):")
        for file in csv_files:
            print(f"  - {file}")
        
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
    
    # Script'i mevcut dizinde çalıştır
    current_dir = os.getcwd()
    print(f"📁 Script çalıştırılıyor: {current_dir}/{script}")
    
    result = subprocess.run([sys.executable, script], cwd=current_dir)
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