import subprocess
import sys
import os
import glob
import time

scripts = [
    "nibkrtry.py",
    "ncorrex.py",  # CSV Ex-Dividend Date düzeltici (CNBC)
    "nnormalize_data.py",
    "nmaster_processor.py",  # YEK dosyalarını oluşturur ve Cally değerlerini hesaplar
    "nbefore_common_adv.py",
    "ncalculate_scores.py",
    "nfill_missing_solidity_data.py",
    "nmarket_risk_analyzer.py",
    "ncalculate_thebest.py",
    "noptimize_shorts.py",  # EKHELD dosyalarından en düşük SHORT_FINPAL hisselerini bulur
    "ntumcsvport.py",  # SSFINEK dosyalarından LONG/SHORT hisseleri seçer
    "npreviousadd.py",  # SSFINEK dosyalarına prev_close kolonu ekler ve janek_ prefix ile kaydeder
    "merge_csvs.py",  # janek_ssfinek dosyalarını birleştirir ve janalldata.csv oluşturur
    "gorter.py",  # janalldata.csv'den her CGRUP için en yüksek ve en düşük 3 GORT değerine sahip hisseleri bulur
]

def show_script_menu():
    """Script seçim menüsünü gösterir"""
    print("\n" + "="*80)
    print("🚀 RUN ANYWHERE N - Script Seçim Menüsü")
    print("="*80)
    print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) DOSYALAR KULLANILACAK!")
    print("⚠️  Alt dizinlerdeki (janall, janallw, vb.) dosyalar kullanılmayacak!")
    print()
    print("Hangi script'ten başlamak istiyorsunuz?")
    print()
    
    for i, script in enumerate(scripts, 1):
        print(f"{i:2d}. {script}")
    
    print()
    print("Örnek: 12 yazarsanız 'nbefore_common_adv.py' dan başlar")
    print("       1 yazarsanız 'nibkrtry.py' dan başlar")
    print("       8 yazarsanız 'nbefore_common_adv.py' dan başlar")
    print()

def get_user_choice():
    """Kullanıcıdan geçerli bir seçim alır"""
    while True:
        try:
            choice = input("📝 Seçiminizi girin (1-20): ").strip()
            choice_num = int(choice)
            
            if 1 <= choice_num <= len(scripts):
                return choice_num
            else:
                print(f"❌ Lütfen 1 ile {len(scripts)} arasında bir sayı girin!")
        except ValueError:
            print("❌ Lütfen geçerli bir sayı girin!")
        except KeyboardInterrupt:
            print("\n\n👋 Program sonlandırıldı.")
            sys.exit(0)

def main():
    """Ana fonksiyon"""
    print("🎯 RUN ANYWHERE N - İstediğiniz yerden başlayın!")
    print("⚠️  SADECE ANA DİZİNDEKİ (StockTracker) DOSYALAR KULLANILACAK!")
    print("⚠️  Alt dizinlerdeki (janall, janallw, vb.) dosyalar kullanılmayacak!")
    
    # Çalışma dizinini StockTracker olarak ayarla
    print("=" * 60)
    current_dir = os.getcwd()
    print(f"🔍 Mevcut çalışma dizini: {current_dir}")
    
    # StockTracker dizinini bul ve oraya geç
    if not current_dir.endswith('StockTracker'):
        # StockTracker dizinini bul
        stocktracker_dir = None
        for root, dirs, files in os.walk('.'):
            if 'StockTracker' in root:
                stocktracker_dir = root
                break
        
        if stocktracker_dir:
            print(f"🔍 StockTracker dizini bulundu: {stocktracker_dir}")
            os.chdir(stocktracker_dir)
            current_dir = os.getcwd()
            print(f"✅ StockTracker dizinine geçildi: {current_dir}")
        else:
            print("❌ StockTracker dizini bulunamadı!")
            return
    else:
        print(f"✅ Zaten StockTracker dizinindeyiz: {current_dir}")
    
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
    print("=" * 60)
    
    # Script menüsünü göster
    show_script_menu()
    
    # Kullanıcı seçimini al
    start_index = get_user_choice()
    
    # Seçilen script'i göster
    selected_script = scripts[start_index - 1]
    print(f"\n🎯 {selected_script} dan başlanıyor...")
    print(f"📋 Toplam {len(scripts) - start_index + 1} script çalıştırılacak")
    
    # Onay al
    confirm = input(f"\n✅ {selected_script} dan başlayarak devam etmek istiyor musunuz? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes', 'evet', 'e']:
        print("❌ İşlem iptal edildi.")
        return
    
    # Seçilen script'ten itibaren çalıştır
    scripts_to_run = scripts[start_index - 1:]
    
    print(f"\n🚀 {len(scripts_to_run)} script çalıştırılıyor...")
    print("="*60)
    
    for i, script in enumerate(scripts_to_run, 1):
        print(f"\n[{i}/{len(scripts_to_run)}] Çalıştırılıyor: {script}")
        
        # Script'in varlığını kontrol et
        if not os.path.exists(script):
            print(f"❌ Script bulunamadı: {script}")
            print(f"❌ Mevcut dizin: {os.getcwd()}")
            print(f"❌ Mevcut dosyalar: {os.listdir('.')}")
            break
        
        # Script'i StockTracker dizininde çalıştır
        current_dir = os.getcwd()
        print(f"📁 Script çalıştırılıyor: {current_dir}/{script}")
        print(f"📁 Çalışma dizini: {current_dir}")
        
        result = subprocess.run([sys.executable, script], cwd=current_dir)
        if result.returncode != 0:
            print(f"❌ Hata oluştu, script durdu: {script}")
            print(f"❌ Return code: {result.returncode}")
            break
        print(f"✅ Bitti: {script}")
        print(f"⏳ Bir sonraki script için 5 saniye bekleniyor...")
        time.sleep(5)  # 5 saniye bekle
        print()
    
    print("🎉 Seçilen script'lerden itibaren tüm işlemler tamamlandı.")
    print("✅ Tüm CSV dosyaları ana dizinde (StockTracker) oluşturuldu.")
    print("⚠️  Alt dizinlerdeki dosyalar hiç kullanılmadı!")

if __name__ == "__main__":
    main()