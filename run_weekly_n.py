import subprocess
import sys
import os
import shutil
import glob

# ═══════════════════════════════════════════════════════════════════════
# PYTHON 3.12 OTOMATİK KONTROL
# ib_insync + nest_asyncio, Python 3.14+ ile uyumsuz (asyncio deprecated).
# Bu script Python 3.12 ile çalışmalı. Yanlış sürüm tespit edilirse
# kendini otomatik olarak Python 3.12 ile yeniden başlatır.
# ═══════════════════════════════════════════════════════════════════════
REQUIRED_PYTHON_MINOR = 12  # Python 3.12.x

if sys.version_info[:2] != (3, REQUIRED_PYTHON_MINOR):
    # Doğru Python'u bul
    python312_paths = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe"),
        r"C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Python312\python.exe",
    ]
    python312 = None
    for p in python312_paths:
        if os.path.exists(p):
            python312 = p
            break
    
    if python312:
        print(f"⚠️  Python {sys.version_info[0]}.{sys.version_info[1]} tespit edildi → Python 3.12 ile yeniden başlatılıyor...")
        print(f"    Kullanılacak: {python312}")
        result = subprocess.run([python312] + sys.argv, cwd=os.getcwd())
        sys.exit(result.returncode)
    else:
        print(f"❌ Python 3.12 bulunamadı! ib_insync Python 3.14+ ile uyumsuz.")
        print(f"   Beklenen konumlar: {python312_paths}")
        print(f"   Mevcut Python: {sys.executable} (v{sys.version_info[0]}.{sys.version_info[1]})")
        sys.exit(1)

print(f"✅ Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} ({sys.executable})")

# ═══════════════════════════════════════════════════════════════════════
# WEEKLY SCRIPTS
# Daily pipeline + haftalık ek scriptler (ncommon_stocks, nget_short_fee_rates)
# ═══════════════════════════════════════════════════════════════════════
scripts = [
    "nibkrtry.py",
    "ncorrex.py",  # CSV Ex-Dividend Date düzeltici (CNBC)
    "nnormalize_data.py",
    "nmaster_processor.py",  # YEK dosyalarını oluşturur ve Cally değerlerini hesaplar
    "nbefore_common_adv.py",
    "ncommon_stocks.py",  # 🔶 WEEKLY ONLY — ortak hisse analizi (market cap vs.)
    "ncalculate_scores.py",
    "nmarket_risk_analyzer.py",
    "ncalculate_thebest.py",
    "nget_short_fee_rates.py",  # 🔶 WEEKLY ONLY — EKHELD dosyalarından short fee rate verilerini çeker
    "noptimize_shorts.py",  # finek*.csv → ssfinek*.csv (SMI merge + SHORT_FINAL hesaplama)
    "netobosol.py",  # NETOBOSOL: ssfinek*.csv üzerinde Market regime FINAL_THG revision
    "ntumcsvport.py",  # SSFINEK dosyalarından LONG/SHORT hisseleri seçer
    "npreviousadd.py",  # SSFINEK dosyalarına prev_close kolonu ekler ve janek_ prefix ile kaydeder
    "merge_csvs.py",  # janek_ssfinek dosyalarını birleştirir ve janalldata.csv oluşturur
    "exdiv_info.py",  # Bugün ex-dividend olan hisseleri bulur → exdiv_today.json
    "gorter.py",  # janalldata.csv'den her CGRUP için en yüksek ve en düşük 3 GORT değerine sahip hisseleri bulur
    "npattern_export.py",  # LPAT ve SPAT skorlarını hesaplayıp pattern_suggestions_lpat_spat.csv olarak kaydeder
]

# Çalışma dizinini run_weekly_n.py'nin bulunduğu klasöre ayarla (nereden çalıştırılırsa çalıştırılsın)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

print("🚀 RUN WEEKLY N - Haftalık İşlemler Başlatılıyor")
print("=" * 60)
current_dir = SCRIPT_DIR
print(f"🔍 Çalışma dizini: {current_dir}")

# === STALE ARA DOSYA TEMİZLİĞİ ===
# Pipeline'ın hatasız çalışması için önceki çalışmadan kalan
# ara dosyaları temizle. Aksi halde bir script hata alıp finek
# üretemezse, eski stale finek kalır ve sonraki adımlar eski veriyle çalışır.
print("\n🧹 Eski ara dosyalar temizleniyor (stale veri önleme)...")
stale_patterns = [
    "finek*.csv",       # ncalculate_thebest output
    "ssfinek*.csv",     # noptimize_shorts output
    "janek_ssfinek*.csv",  # npreviousadd output
    "janalldata.csv",   # merge_csvs output (ana dizin)
]
# janall/ alt dizinindeki eski kopyayı da temizle
stale_janall_files = [
    os.path.join("janall", "janalldata.csv"),
]
total_cleaned = 0
for pattern in stale_patterns:
    old_files = glob.glob(pattern)
    for f in old_files:
        try:
            os.remove(f)
            total_cleaned += 1
        except Exception as e:
            print(f"  ⚠️ {f} silinemedi: {e}")
for f in stale_janall_files:
    if os.path.exists(f):
        try:
            os.remove(f)
            total_cleaned += 1
        except Exception as e:
            print(f"  ⚠️ {f} silinemedi: {e}")
print(f"  🗑️ {total_cleaned} eski ara dosya temizlendi")
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

all_success = True
for script in scripts:
    print(f"Çalıştırılıyor: {script}")
    
    # Script'i mevcut dizinde çalıştır
    current_dir = os.getcwd()
    print(f"📁 Script çalıştırılıyor: {current_dir}/{script}")
    
    result = subprocess.run([sys.executable, script], cwd=current_dir)
    if result.returncode != 0:
        print(f"Hata oluştu, script durdu: {script}")
        all_success = False
        break
    print(f"Bitti: {script}")
    print()

# Tüm scriptler başarıyla tamamlandıktan sonra CSV dosyalarını janall klasörüne kopyala
# NOT: Her script sonrası kopyalamak stale/kısmi dosyaların janall/'e yazılmasına neden oluyordu
if all_success:
    print("📋 CSV dosyaları janall klasörüne kopyalanıyor...")
    copy_csv_files_to_janall()
    print()
    print("Tüm işlemler tamamlandı.")
    print("✅ CSV dosyaları hem ana dizinde hem de janall klasöründe oluşturuldu.")
    print("📊 janalldata.csv dosyası GROUP kolonu ile hazır!")
else:
    print("⚠️ Pipeline hatayla sonlandı — janall/ klasörüne kopyalama YAPILMADI (stale önleme).")
    print("   Ana dizindeki mevcut dosyalar kısmi olabilir!")