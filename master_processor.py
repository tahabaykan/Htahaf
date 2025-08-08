import subprocess
import sys
import os
from datetime import datetime

def run_script(script_name, description):
    """
    Belirtilen script'i çalıştırır ve sonucunu raporlar
    """
    print(f"\n🔄 {description}")
    print(f"📁 Script: {script_name}")
    print(f"⏰ Başlangıç: {datetime.now().strftime('%H:%M:%S')}")
    
    try:
        # Script'i çalıştır
        result = subprocess.run([sys.executable, script_name], 
                              capture_output=True, 
                              text=True, 
                              timeout=600)  # 10 dakika timeout
        
        if result.returncode == 0:
            print(f"✅ {script_name} başarıyla tamamlandı!")
            # Çıktıyı kısalt
            output_lines = result.stdout.strip().split('\n')
            if len(output_lines) > 10:
                print("📤 Son 10 satır çıktı:")
                for line in output_lines[-10:]:
                    print(f"   {line}")
            else:
                print("📤 Çıktı:")
                print(result.stdout)
        else:
            print(f"❌ {script_name} hata ile sonlandı!")
            print(f"📤 Hata:")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {script_name} timeout nedeniyle durduruldu (10 dakika)")
        return False
    except Exception as e:
        print(f"❌ {script_name} çalıştırılırken hata: {e}")
        return False
    
    print(f"⏰ Bitiş: {datetime.now().strftime('%H:%M:%S')}")
    return True

def main():
    """
    Ana işlem sırası
    """
    print("🚀 MASTER PROCESSOR - TÜM İŞLEMLERİ SIRAYLA ÇALIŞTIRMA")
    print(f"📅 Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # İşlem sırası
    scripts = [
        {
            "name": "ntreyield.py",
            "description": "Treasury Yield'larını Güncelleme",
            "required": True
        },
        {
            "name": "nyield_calculator.py", 
            "description": "Ana Yield Hesaplama ve İşlemler",
            "required": True
        },
        {
            "name": "benchmark_adjuster.py",
            "description": "Benchmark Ayarlama (NCOMP Count'a göre)",
            "required": True
        },
        {
            "name": "risk_premium_calculator.py",
            "description": "Adjusted Risk Primi Hesaplama",
            "required": True
        },
        {
            "name": "all_inclusive_risk_premium.py",
            "description": "All-Inc Risk Prim Kolonu Oluşturma",
            "required": True
        }
    ]
    
    successful_scripts = []
    failed_scripts = []
    
    # Her script'i sırayla çalıştır
    for i, script in enumerate(scripts, 1):
        print(f"\n📋 Adım {i}/{len(scripts)}: {script['description']}")
        
        # Script dosyasının varlığını kontrol et
        if not os.path.exists(script['name']):
            print(f"❌ {script['name']} dosyası bulunamadı!")
            if script['required']:
                print(f"⚠️ Bu script zorunlu, işlem durduruluyor.")
                break
            else:
                print(f"⚠️ Bu script opsiyonel, atlanıyor.")
                continue
        
        # Script'i çalıştır
        success = run_script(script['name'], script['description'])
        
        if success:
            successful_scripts.append(script['name'])
        else:
            failed_scripts.append(script['name'])
            if script['required']:
                print(f"⚠️ Zorunlu script başarısız, işlem durduruluyor.")
                break
    
    # Sonuç raporu
    print(f"\n{'='*50}")
    print("📊 İŞLEM SONUÇ RAPORU")
    print(f"{'='*50}")
    print(f"✅ Başarılı Scriptler ({len(successful_scripts)}):")
    for script in successful_scripts:
        print(f"   ✓ {script}")
    
    if failed_scripts:
        print(f"\n❌ Başarısız Scriptler ({len(failed_scripts)}):")
        for script in failed_scripts:
            print(f"   ✗ {script}")
    
    print(f"\n📅 Bitiş: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if len(successful_scripts) == len(scripts):
        print("\n🎉 TÜM İŞLEMLER BAŞARIYLA TAMAMLANDI!")
        print("📁 YEK CSV dosyalarınız güncel ve hazır!")
    else:
        print(f"\n⚠️ {len(failed_scripts)} script başarısız oldu.")
        print("🔧 Lütfen hataları kontrol edin ve tekrar deneyin.")

if __name__ == "__main__":
    main() 