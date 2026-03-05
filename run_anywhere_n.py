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

scripts = [
    "nibkrtry.py",
    "ncorrex.py",  # CSV Ex-Dividend Date düzeltici (CNBC)
    "nnormalize_data.py",
    "nmaster_processor.py",  # YEK dosyalarını oluşturur ve Cally değerlerini hesaplar
    "nbefore_common_adv.py",
    "ncalculate_scores.py",
    # nfill_missing_solidity_data.py KALDIRILDI:
    #   Input olarak sldek*.csv bekliyor ama bu dosyaları üreten bir script yok.
    #   ncalculate_thebest.py solidity verisini doğrudan allcomek_sld.csv'den okuyor.
    #   Bu script sessizce "dosya bulunamadı" yazıp geçiyordu — ölü kod.
    "nmarket_risk_analyzer.py",
    "ncalculate_thebest.py",
    "noptimize_shorts.py",  # EKHELD dosyalarından en düşük SHORT_FINAL hisselerini bulur
    "ntumcsvport.py",  # SSFINEK dosyalarından LONG/SHORT hisseleri seçer
    "npreviousadd.py",  # SSFINEK dosyalarına prev_close kolonu ekler ve janek_ prefix ile kaydeder
    "merge_csvs.py",  # janek_ssfinek dosyalarını birleştirir ve janalldata.csv oluşturur
    "gorter.py",  # janalldata.csv'den her CGRUP için en yüksek ve en düşük 3 GORT değerine sahip hisseleri bulur
]

# Çalışma dizinini run_anywhere_n.py'nin bulunduğu klasöre ayarla (nereden çalıştırılırsa çalıştırılsın)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# Hangi dosya paternlerinin hangi scriptlerden üretildiğini belirle
SCRIPT_OUTPUTS = {
    "ncalculate_thebest.py": ["finek*.csv"],
    "noptimize_shorts.py": ["ssfinek*.csv"],
    "npreviousadd.py": ["janek_ssfinek*.csv"],
    "merge_csvs.py": ["janalldata.csv"],
}


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


def clean_stale_files(scripts_to_run):
    """Çalıştırılacak scriptlerin output dosyalarını temizle (stale veri önleme)"""
    print("\n🧹 İlgili ara dosyalar temizleniyor (stale veri önleme)...")
    total_cleaned = 0
    for script in scripts_to_run:
        patterns = SCRIPT_OUTPUTS.get(script, [])
        for pattern in patterns:
            old_files = glob.glob(pattern)
            for f in old_files:
                try:
                    os.remove(f)
                    total_cleaned += 1
                except Exception as e:
                    print(f"  ⚠️ {f} silinemedi: {e}")
    # janall/janalldata.csv'yi de temizle (eğer merge_csvs çalışacaksa)
    if "merge_csvs.py" in scripts_to_run:
        janall_janalldata = os.path.join("janall", "janalldata.csv")
        if os.path.exists(janall_janalldata):
            try:
                os.remove(janall_janalldata)
                total_cleaned += 1
            except Exception as e:
                print(f"  ⚠️ {janall_janalldata} silinemedi: {e}")
    print(f"  🗑️ {total_cleaned} eski ara dosya temizlendi")
    print()


def show_menu():
    """Script seçim menüsünü göster"""
    print()
    print("=" * 60)
    print("📋 SCRIPT LİSTESİ")
    print("=" * 60)
    for i, script in enumerate(scripts, 1):
        print(f"  {i:2d}. {script}")
    print()
    print("KULLANIM:")
    print("  python run_anywhere_n.py <numara>        → Sadece o script'i çalıştır")
    print("  python run_anywhere_n.py <isim.py>       → Sadece o script'i çalıştır")
    print("  python run_anywhere_n.py <num> <num>     → Birden fazla script çalıştır")
    print("  python run_anywhere_n.py <num>-<num>     → Aralık belirt (from-to)")
    print()
    print("ÖRNEKLER:")
    print("  python run_anywhere_n.py 11              → npreviousadd.py çalıştır")
    print("  python run_anywhere_n.py npreviousadd.py → npreviousadd.py çalıştır")
    print("  python run_anywhere_n.py 11 12 13        → 11, 12, 13 numaralı scriptler")
    print("  python run_anywhere_n.py 11-13           → 11'den 13'e kadar (dahil)")
    print("=" * 60)


def resolve_script(arg):
    """Argümanı script adına çevir. Numara veya dosya adı kabul eder."""
    # Numara mı?
    try:
        num = int(arg)
        if 1 <= num <= len(scripts):
            return scripts[num - 1]
        else:
            print(f"❌ Geçersiz numara: {num} (1-{len(scripts)} arası olmalı)")
            return None
    except ValueError:
        pass
    
    # Dosya adı mı?
    # Tam eşleşme
    if arg in scripts:
        return arg
    # .py olmadan yazılmışsa
    if not arg.endswith(".py"):
        arg_with_py = arg + ".py"
        if arg_with_py in scripts:
            return arg_with_py
    # Kısmi eşleşme (contains)
    matches = [s for s in scripts if arg.lower() in s.lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"❌ '{arg}' birden fazla script ile eşleşti: {matches}")
        return None
    
    print(f"❌ Script bulunamadı: {arg}")
    return None


def parse_arguments(args):
    """Komut satırı argümanlarını parse et. Tekli, çoklu, ve aralık destekler."""
    scripts_to_run = []
    
    for arg in args:
        # Aralık mı? (örn: 11-13)
        if "-" in arg and not arg.startswith("-"):
            parts = arg.split("-", 1)
            try:
                start = int(parts[0])
                end = int(parts[1])
                if 1 <= start <= len(scripts) and 1 <= end <= len(scripts) and start <= end:
                    for i in range(start, end + 1):
                        s = scripts[i - 1]
                        if s not in scripts_to_run:
                            scripts_to_run.append(s)
                    continue
                else:
                    print(f"❌ Geçersiz aralık: {arg} (1-{len(scripts)} arası olmalı)")
                    return None
            except ValueError:
                pass  # Aralık değil, normal argüman olarak devam et
        
        # Tekli argüman
        resolved = resolve_script(arg)
        if resolved is None:
            return None
        if resolved not in scripts_to_run:
            scripts_to_run.append(resolved)
    
    return scripts_to_run


# ═══════════════════════════════════════════════════════════════════════
# ANA ÇALIŞMA BLOĞU
# ═══════════════════════════════════════════════════════════════════════

print("🚀 RUN ANYWHERE N - İstediğin Script'i Çalıştır")
print("=" * 60)
current_dir = SCRIPT_DIR
print(f"🔍 Çalışma dizini: {current_dir}")

# Argüman yoksa menüyü göster ve çık
if len(sys.argv) < 2:
    show_menu()
    sys.exit(0)

# Argümanları parse et
scripts_to_run = parse_arguments(sys.argv[1:])
if scripts_to_run is None or len(scripts_to_run) == 0:
    print("\n❌ Çalıştırılacak script belirlenemedi!")
    show_menu()
    sys.exit(1)

# Çalıştırılacak scriptleri göster
print(f"\n🎯 Çalıştırılacak {len(scripts_to_run)} script:")
for i, s in enumerate(scripts_to_run, 1):
    idx = scripts.index(s) + 1
    print(f"  {idx:2d}. {s}")
print()

# === STALE ARA DOSYA TEMİZLİĞİ ===
clean_stale_files(scripts_to_run)

# === SCRIPTLERI ÇALIŞTIR ===
all_success = True
for i, script in enumerate(scripts_to_run, 1):
    print(f"Çalıştırılıyor: {script}")
    
    # Script'in varlığını kontrol et
    if not os.path.exists(script):
        print(f"❌ Script bulunamadı: {script}")
        all_success = False
        break
    
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