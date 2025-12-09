import subprocess
import sys
import os
import time
from datetime import datetime

def run_script_simple(script_name):
    """
    Script'i basit şekilde çalıştırır
    """
    print(f"🔄 {script_name} çalıştırılıyor...")
    
    try:
        # Script'i mevcut dizinde çalıştır
        current_dir = os.getcwd()
        print(f"📁 Script çalıştırılıyor: {current_dir}/{script_name}")
        
        # ntreyield.py için özel ayarlar
        if script_name == "ntreyield.py":
            # ntreyield.py için daha uzun timeout ve farklı ayarlar
            result = subprocess.run([sys.executable, script_name], 
                                  timeout=600,  # 10 dakika
                                  text=True,
                                  cwd=current_dir)  # Mevcut dizinde çalıştır
        elif script_name == "nyield_calculator.py":
            # nyield_calculator.py için output göster
            result = subprocess.run([sys.executable, script_name], 
                                  text=True, 
                                  timeout=300,
                                  cwd=current_dir)  # Mevcut dizinde çalıştır
        else:
            # Diğer scriptler için normal ayarlar
            result = subprocess.run([sys.executable, script_name], 
                                  capture_output=False,  # ✅ ÇIKTI GÖRÜNÜR!
                                  text=True, 
                                  timeout=300,
                                  cwd=current_dir)  # Mevcut dizinde çalıştır
        
        if result.returncode == 0:
            print(f"✅ {script_name} başarıyla tamamlandı")
            return True
        else:
            print(f"❌ {script_name} başarısız oldu")
            print(f"   Hata: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {script_name} timeout oldu")
        return False
    except Exception as e:
        print(f"❌ {script_name} çalıştırılırken hata: {e}")
        return False

def main():
    """
    Ana master processor fonksiyonu
    """
    print("=== MASTER PROCESSOR BAŞLATILIYOR ===")
    print(f"Başlangıç zamanı: {datetime.now()}")
    print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) DOSYALAR KULLANILACAK!")
    print("⚠️  Alt dizinlerdeki (janall, janallw, vb.) dosyalar kullanılmayacak!")
    
    # Çalışma dizinini kontrol et ve yazdır
    current_dir = os.getcwd()
    print(f"🔍 Çalışma dizini: {current_dir}")
    
    # Mevcut dizindeki CSV dosyalarını listele (sadece ana dizindeki)
    csv_files = []
    for f in os.listdir(current_dir):
        if f.endswith('.csv'):
            # Dosya ana dizinde mi kontrol et
            file_path = os.path.join(current_dir, f)
            if os.path.isfile(file_path) and not os.path.dirname(file_path).endswith(('janall', 'janallw', 'janall_backup')):
                csv_files.append(f)
    
    print(f"📁 Mevcut dizindeki CSV dosyaları (sadece ana dizinden) ({len(csv_files)} adet):")
    for file in csv_files:
        print(f"  - {file}")
    
    # Script sırası
    scripts = [
        "create_yek_files.py",                    # 1. nek*.csv → yek*.csv (boş Cally kolonları eklenir)
        "ntreyield.py",                           # 2. Treasury yield'ları güncelle (US15Y dahil)
        "nyield_calculator.py",                   # 3. Cally değerleri hesaplanır (15Y dahil)
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
            print(f"⏳ Bir sonraki script için 5 saniye bekleniyor...")
            time.sleep(5)  # 5 saniye bekle
        else:
            print(f"⚠️ {script} başarısız oldu, devam ediliyor...")
            print(f"⏳ Bir sonraki script için 5 saniye bekleniyor...")
            time.sleep(5)  # 5 saniye bekle
    
    print(f"\n=== MASTER PROCESSOR TAMAMLANDI ===")
    print(f"Bitiş zamanı: {datetime.now()}")
    print(f"Başarılı scriptler: {successful_scripts}/{total_scripts}")
    
    if successful_scripts == total_scripts:
        print("🎉 TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI!")
    else:
        print(f"⚠️ {total_scripts - successful_scripts} script başarısız oldu")

if __name__ == "__main__":
    main() 