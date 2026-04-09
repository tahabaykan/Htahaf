#!/usr/bin/env python3
"""
Quant Engine - Backend ve Frontend Başlatma Scripti
Kullanım: python baslat.py
"""

import subprocess
import sys
import os
import time
import glob
from pathlib import Path
from datetime import datetime, timedelta

# ═══════════════════════════════════════════════════════════════════════
# TEMETTÜ PATTERN PLAN DEFAULTS
# ═══════════════════════════════════════════════════════════════════════
DEFAULT_LONG_PCT = 50
DEFAULT_LONG_HELD_PCT = 50
DEFAULT_SHORT_HELD_PCT = 50

def check_redis_container():
    """Redis Docker container'ının çalışıp çalışmadığını kontrol et"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=redis-quant-engine", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "redis-quant-engine" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False

def check_redis_container_exists():
    """Redis container'ının var olup olmadığını kontrol et (çalışsın ya da durmuş olsun)"""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=redis-quant-engine", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "redis-quant-engine" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False

def start_redis_container():
    """Redis Docker container'ını başlat"""
    try:
        # Önce container var mı kontrol et (durmuş olabilir)
        container_exists = check_redis_container_exists()
        
        if container_exists:
            # Container var ama durmuş, sadece başlat
            print("   [i] Redis container bulundu, calistiriliyor...")
            result = subprocess.run(
                ["docker", "start", "redis-quant-engine"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                time.sleep(2)
                return True
            else:
                print(f"   [!] Container başlatılamadı: {result.stderr[:100]}")
                return False
        else:
            # Container yok, yeni oluştur
            print("   [>] Redis container olusturuluyor ve baslatiliyor...")
            result = subprocess.run(
                ["docker", "run", "-d", "-p", "6379:6379", "--name", "redis-quant-engine", "redis:latest"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                # Container başlatıldı, biraz bekle
                time.sleep(2)
                # Redis'in hazır olup olmadığını kontrol et
                for i in range(5):
                    try:
                        import redis
                        client = redis.Redis(host='localhost', port=6379, socket_connect_timeout=1)
                        client.ping()
                        return True
                    except Exception:
                        time.sleep(1)
                return True  # Container başlatıldı, Redis hazır olabilir
            else:
                # Hata mesajını göster
                if result.stderr:
                    print(f"   [!] Container oluşturma hatası: {result.stderr[:150]}")
                return False
    except subprocess.TimeoutExpired:
        print("   [!] Redis başlatma zaman aşımı")
        return False
    except FileNotFoundError:
        print("   [!] Docker bulunamadı - Redis container başlatılamıyor")
        print("   [TIP] Docker Desktop'ın çalıştığından emin olun")
        return False
    except Exception as e:
        print(f"   [!] Redis başlatma hatası: {str(e)[:100]}")
        return False

def check_redis():
    """Redis'in çalışıp çalışmadığını kontrol et (bağlantı testi)"""
    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False

def _get_python_cmd(script_dir: Path) -> str:
    """
    Proje için kullanılacak Python yorumlayıcısını belirle.
    
    Tercih sırası:
    1) Aynı klasördeki `venv312` sanal ortamı (Windows: Scripts/python.exe, Linux/Mac: bin/python)
    2) Sistem PATH üzerindeki `python`
    """
    venv_dir = script_dir / "venv312"
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"
    
    if venv_python.exists():
        return str(venv_python)
    
    # Yedek: sistemdeki python
    return "python"


# ═══════════════════════════════════════════════════════════════════════
# TERMINAL LOG MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def _get_terminal_log_dir(script_dir: Path) -> Path:
    """Terminal log dizinini döndür, yoksa oluştur."""
    log_dir = script_dir / "data" / "logs" / "terminals"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

def _get_terminal_log_path(script_dir: Path, worker_name: str) -> str:
    """
    Her terminal oturumu için benzersiz log dosya yolu oluştur.
    Format: {worker_name}_{YYYYMMDD}_{HHMMSS}.log
    
    Aynı gün aynı worker 40 kez açılsa bile her biri ayrı dosya olur.
    En güncel olan = en yüksek timestamp.
    """
    log_dir = _get_terminal_log_dir(script_dir)
    ts = time.strftime("%Y%m%d_%H%M%S")
    return str(log_dir / f"{worker_name}_{ts}.log")

def _cleanup_old_terminal_logs(script_dir: Path, retention_days: int = 7):
    """7 günden eski terminal loglarını temizle."""
    log_dir = _get_terminal_log_dir(script_dir)
    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    cleaned = 0
    
    for log_file in log_dir.glob("*.log"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                cleaned += 1
        except Exception:
            pass
    
    if cleaned > 0:
        print(f"   [i] {cleaned} eski terminal logu temizlendi ({retention_days}+ gün)")


def _write_launcher_bat(script_dir: Path, worker_name: str, python_cmd: str, log_file: str, script_args: str, env_vars: str = "") -> str:
    """
    Write a temporary .bat launcher to avoid CMD quote escaping hell.
    Returns the path to the .bat file.
    """
    bat_dir = _get_terminal_log_dir(script_dir)
    bat_path = bat_dir / f"_launch_{worker_name}.bat"
    tee_wrapper = script_dir / "_tee_wrapper.py"
    
    lines = [
        "@echo off",
        "chcp 65001 >nul 2>&1",
        "set PYTHONIOENCODING=utf-8",
        f"cd /d \"{script_dir}\"",
    ]
    if env_vars:
        lines.append(env_vars)
    lines.append(f'"{python_cmd}" -u "{tee_wrapper}" "{log_file}" {script_args}')
    lines.append("pause")
    
    bat_path.write_text("\r\n".join(lines), encoding="utf-8")
    return str(bat_path)


def start_worker(script_dir, worker_num, worker_name, worker_title, worker_script):
    """Worker başlatma fonksiyonu — tüm çıktı log dosyasına da kaydedilir."""
    log_file = _get_terminal_log_path(script_dir, worker_name)
    print(f"[>] {worker_title} başlatılıyor (yeni pencere)...")
    print(f"    📝 Log: {log_file}")
    
    python_cmd = _get_python_cmd(script_dir)

    if sys.platform == "win32":
        bat_path = _write_launcher_bat(
            script_dir, worker_name, python_cmd, log_file,
            script_args=worker_script,
            env_vars=f"set WORKER_NAME={worker_name}",
        )
        os.system(f'start "Quant Engine - {worker_title}" cmd /k ""{bat_path}""')
    else:
        tee_wrapper = str(script_dir / "_tee_wrapper.py")
        subprocess.Popen(
            [
                "gnome-terminal", "--", "bash", "-c",
                f"cd '{script_dir}' && export WORKER_NAME={worker_name} && \"{python_cmd}\" -u \"{tee_wrapper}\" \"{log_file}\" {worker_script}; exec bash",
            ],
            start_new_session=True,
        )
    
    time.sleep(0.5)



def start_backend(script_dir):
    """Backend başlatma fonksiyonu — tüm çıktı log dosyasına da kaydedilir."""
    log_file = _get_terminal_log_path(script_dir, "backend")
    print("[>] Backend başlatılıyor (yeni pencere)...")
    print(f"    📝 Log: {log_file}")
    
    python_cmd = _get_python_cmd(script_dir)

    if sys.platform == "win32":
        bat_path = _write_launcher_bat(
            script_dir, "backend", python_cmd, log_file,
            script_args="main.py api",
        )
        os.system(f'start "Quant Engine - Backend" cmd /k ""{bat_path}""')
    else:
        tee_wrapper = str(script_dir / "_tee_wrapper.py")
        subprocess.Popen(
            [
                "gnome-terminal", "--", "bash", "-c",
                f"cd '{script_dir}' && \"{python_cmd}\" -u \"{tee_wrapper}\" \"{log_file}\" main.py api; exec bash",
            ],
            start_new_session=True,
        )
    
    time.sleep(0.5)

def start_frontend(frontend_dir):
    """Frontend başlatma fonksiyonu"""
    print("[>] Frontend baslatiliyor (yeni pencere)...")
    
    if sys.platform == "win32":
        frontend_dir_str = str(frontend_dir)
        frontend_cmd = f'start "Quant Engine - Frontend" cmd /k "cd /d ""{frontend_dir_str}"" && npm run dev"'
        os.system(frontend_cmd)
    else:
        # Linux/Mac için
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd '{frontend_dir}' && npm run dev; exec bash"],
            start_new_session=True
        )
    
    time.sleep(0.5)


def run_exdiv_plan():
    """Temettü pattern 30 günlük planı çalıştır (run_30day_plan entegrasyonu)"""
    print()
    print("═" * 60)
    print("  TEMETTÜ PATTERN - 30 GÜNLÜK PLAN")
    print("═" * 60)
    print()
    print(f"  Default ayarlar: Long={DEFAULT_LONG_PCT}% / Short={100-DEFAULT_LONG_PCT}%")
    print(f"                   Long Held={DEFAULT_LONG_HELD_PCT}% / Short Held={DEFAULT_SHORT_HELD_PCT}%")
    print()
    
    try:
        change = input("  Default değerleri değiştirmek ister misiniz? (y/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        change = 'n'
    
    if change == 'y':
        # Soru 1: Long/Short oranı
        print()
        print("  ┌─ ADIM 1: Long / Short Oranı ──────────────┐")
        print("  │  Örnekler: 50, 70, 30, 100                │")
        print("  └───────────────────────────────────────────┘")
        while True:
            try:
                raw = input(f"  Long %  [default={DEFAULT_LONG_PCT}]: ").strip()
                long_pct = int(raw) if raw else DEFAULT_LONG_PCT
                if 0 <= long_pct <= 100:
                    short_pct = 100 - long_pct
                    print(f"  ✓ Long: {long_pct}%  |  Short: {short_pct}%")
                    break
                print("  ⚠ 0-100 arası gir")
            except (ValueError, KeyboardInterrupt):
                long_pct = DEFAULT_LONG_PCT
                short_pct = 100 - long_pct
                break
        print()
        
        # Soru 2: Long Held
        print("  ┌─ ADIM 2: Long Held Oranı ─────────────────┐")
        print("  │  100 = hepsi  |  50 = en iyi yarısı       │")
        print("  └───────────────────────────────────────────┘")
        while True:
            try:
                raw = input(f"  Long held %  [default={DEFAULT_LONG_HELD_PCT}]: ").strip()
                long_held = int(raw) if raw else DEFAULT_LONG_HELD_PCT
                if 1 <= long_held <= 100:
                    print(f"  ✓ Long'ların {long_held}%'i held")
                    break
                print("  ⚠ 1-100 arası gir")
            except (ValueError, KeyboardInterrupt):
                long_held = DEFAULT_LONG_HELD_PCT
                break
        print()
        
        # Soru 3: Short Held
        print("  ┌─ ADIM 3: Short Held Oranı ────────────────┐")
        print("  │  100 = hepsi  |  50 = en iyi yarısı       │")
        print("  └───────────────────────────────────────────┘")
        while True:
            try:
                raw = input(f"  Short held %  [default={DEFAULT_SHORT_HELD_PCT}]: ").strip()
                short_held = int(raw) if raw else DEFAULT_SHORT_HELD_PCT
                if 1 <= short_held <= 100:
                    print(f"  ✓ Short'ların {short_held}%'i held")
                    break
                print("  ⚠ 1-100 arası gir")
            except (ValueError, KeyboardInterrupt):
                short_held = DEFAULT_SHORT_HELD_PCT
                break
        print()
    else:
        long_pct = DEFAULT_LONG_PCT
        short_pct = 100 - long_pct
        long_held = DEFAULT_LONG_HELD_PCT
        short_held = DEFAULT_SHORT_HELD_PCT
    
    print("  ═══════════════════════════════════════════")
    print(f"  AYARLAR: {long_pct}L/{short_pct}S  "
          f"| L-Held={long_held}%  | S-Held={short_held}%")
    print("  ═══════════════════════════════════════════")
    print()
    
    # 30 günlük planı çalıştır
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from run_30day_plan import load_data, build_plan, print_and_save
        
        print("  Veriler yükleniyor...")
        summary, base_exdiv_map, held_tickers = load_data()
        print(f"  {len(summary)} hisse, {len(base_exdiv_map)} baz ex-div, {len(held_tickers)} held ticker")
        
        print("  Plan hesaplanıyor...")
        plan = build_plan(summary, base_exdiv_map, long_pct, short_pct, long_held, short_held, held_tickers)
        print_and_save(plan, long_pct, short_pct, long_held, short_held)
        
        print()
        print("  ✅ Temettü pattern planı tamamlandı!")
    except SystemExit:
        print("  ⚠ Pipeline sonuçları bulunamadı (v5_summary.csv)")
        print("  Önce run_pipeline_v51.py çalıştırın.")
        print("  (Menüye devam ediliyor...)")
    except FileNotFoundError:
        print("  ⚠ Pipeline sonuçları bulunamadı (v5_summary.csv)")
        print("  Önce run_pipeline_v51.py çalıştırın.")
    except ImportError as e:
        print(f"  ⚠ run_30day_plan modülü yüklenemedi: {e}")
    except Exception as e:
        print(f"  ⚠ Plan oluşturulurken hata: {e}")
    
    print()
    print("  Terminal menüsüne devam ediliyor...")
    print()


def show_menu():
    """Servis seçim menüsünü göster"""
    print("==" * 60)
    print("Quant Engine - Servis Başlatma")
    print("=" * 60)
    print()
    print("[MENU] Mevcut Servisler:")
    print("   1. Backend (FastAPI)")
    print("   2. Frontend (React)")
    print("   3. Deeper Analysis Worker")
    print("   4. Ticker Alert Worker")
    print("   5. Decision Helper Worker")
    print("   6. Decision Helper V2 Worker")
    print("   7. [OTOMATIK] Truth Ticks CLUSTER -> Backend basladiginda otomatik baslar")
    print("   8. Venue & Hybrid Collector (Shadow Mode)")
    print("   9. Greatest MM Quant Worker")
    print("   10. Market Context Worker (Use '0' to select)")
    print("   11. QeBenchData Worker (Use 'b' to select)")
    print("   12. RevnBookCheck Terminal (Use 'r' to select)")
    print("   13. L1 Feed Terminal (Use 'l' to select)")
    print("   14. QAGENTT Learning Agent (Use 'q' to select)")
    print()
    print("[TIP] Kullanim: Istediginiz servis numaralarini yazin (orn: 12, 126, 123456789br)")
    print("   Örnek: '12' yazarsanız -> Backend + Frontend başlar")
    print("   Örnek: 'b' yazarsanız -> QeBenchData Worker başlar")
    print("   Örnek: 'r' yazarsanız -> RevnBookCheck Terminal başlar")
    print("   Örnek: 'q' yazarsanız -> QAGENTT Learning Agent başlar")
    print("   [*] Oneri: '1689brlq' -> Shadow Mode + Benchmark + RevCheck + L1 Feed + QAGENTT")
    print("   ⚠️  NOT: TT Cluster backend ile otomatik baslar, ayrica secmenize GEREK YOK!")
    print()

def parse_selection(selection):
    """Kullanıcı seçimini parse et ve servis numaralarını döndür"""
    if not selection:
        return set()
    
    final_numbers = []
    
    # Handle 'b' for Benchmark Worker (11)
    if 'b' in selection.lower():
        final_numbers.append(11)
    
    # Handle 'r' for RevnBookCheck Terminal (12)
    if 'r' in selection.lower():
        final_numbers.append(12)
    
    # Handle 'l' for L1 Feed Terminal (13)
    if 'l' in selection.lower():
        final_numbers.append(13)
    
    # Handle 'q' for QAGENTT Learning Agent (14)
    if 'q' in selection.lower():
        final_numbers.append(14)
    
    # Sadece rakamları al
    numbers = [int(c) for c in selection if c.isdigit()]
    
    for n in numbers:
        if n == 0:
            final_numbers.append(10)
        elif n == 7:
            # TT Cluster is auto-managed by backend — skip with warning
            print("   ⚠️  7 (TT Cluster) backend ile otomatik baslar, ayrica secmenize GEREK YOK!")
        elif 1 <= n <= 9:
            final_numbers.append(n)
            
    return set(final_numbers)

def main():
    # ═══════════════════════════════════════════════════════════════════
    # ADIM 0: Temettü Pattern 30 Günlük Plan
    # ═══════════════════════════════════════════════════════════════════
    run_exdiv_plan()

    # Service definitions
    services = {
        1: { "type": "backend", "title": "Backend (FastAPI)" },
        2: { "type": "frontend", "title": "Frontend (React)" },
        3: { "type": "worker", "name": "worker1", "title": "Deeper Analysis Worker", "script": "workers/run_deeper_worker.py" },
        4: { "type": "worker", "name": "ticker_alert_worker1", "title": "Ticker Alert Worker", "script": "workers/run_ticker_alert_worker.py" },
        5: { "type": "worker", "name": "decision_helper_worker1", "title": "Decision Helper Worker", "script": "workers/run_decision_helper_worker.py" },
        6: { "type": "worker", "name": "decision_helper_v2_worker1", "title": "Decision Helper V2 Worker", "script": "workers/run_decision_helper_v2_worker.py" },
        # 7 = TT CLUSTER -> Backend otomatik yönetir, baslat.py'den başlatılmaz!
        8: { "type": "worker", "name": "venue_collector_worker1", "title": "Venue & Hybrid Collector (Shadow Mode)", "script": "workers/run_venue_collector.py" },
        9: { "type": "worker", "name": "greatest_mm_worker1", "title": "Greatest MM Quant Worker", "script": "workers/run_greatest_mm_worker.py" },
        10: { "type": "worker", "name": "market_context_worker1", "title": "Market Context Worker", "script": "workers/market_context_worker.py" },
        11: { "type": "worker", "name": "qebench_worker1", "title": "QeBenchData Worker (Fill Recovery)", "script": "workers/qebench_worker.py" },
        12: { "type": "worker", "name": "revnbookcheck_terminal", "title": "RevnBookCheck Terminal (REV Order Recovery)", "script": "terminals/revnbookcheck_terminal.py" },
        13: { "type": "worker", "name": "l1_feed_worker", "title": "L1 Feed Terminal (30s L1 Updates)", "script": "workers/l1_feed_worker.py" },
        14: { "type": "qagentt", "name": "qagentt_learner", "title": "QAGENTT Learning Agent (Izle & Ogren)", "script": "workers/run_qagentt.py" }
    }

    # Check for command line arguments
    if len(sys.argv) > 1:
        selection = sys.argv[1]
        selected_services = parse_selection(selection)
        if selected_services:
            print(f"[>] Otomatik başlatma modu: {selection}")
        else:
            print(f"[!] Geçersiz argüman: {selection}")
            sys.exit(1)
    else:
        # Interactive Mode
        show_menu()
        
        while True:
            try:
                selection = input("Servis seçimi (numaraları yazın, Enter'a basın): ").strip()
                selected_services = parse_selection(selection)
                
                if selection == "":
                    print("[!]  Hiçbir servis seçilmedi.")
                    confirm = input("Devam etmek istiyor musunuz? (e/h): ").strip().lower()
                    if confirm == 'e':
                        break
                    else:
                        print()
                        continue
                
                if selected_services:
                    break
                else:
                    print("[!]  Geçersiz seçim. Lütfen 1-8 arası numaralar girin.")
                    print()
            except KeyboardInterrupt:
                print("\n\nİptal edildi.")
                sys.exit(0)
            except Exception as e:
                print(f"[!]  Hata: {e}")
                print()

    # Display Selected Services
    if selected_services:
        print()
        print("[OK] Seçilen Servisler:")
        for num in sorted(selected_services):
            title = services[num]["title"]
            print(f"   - {num}. {title}")
        print()
    
    print()
    print("=" * 60)
    print("Servisler başlatılıyor...")
    print("=" * 60)
    print()
    
    # Script'in bulunduğu dizin (tüm servisler için gerekli)
    script_dir = Path(__file__).parent.absolute()
    frontend_dir = script_dir / "frontend"
    
    # Terminal log temizliği (7+ günlük logları sil)
    _cleanup_old_terminal_logs(script_dir)
    
    # Redis kontrolü ve otomatik başlatma
    print("[>] Redis kontrol ediliyor...")
    
    # Önce container'ın çalışıp çalışmadığını kontrol et
    container_running = check_redis_container()
    
    if container_running:
        print("[OK] Redis container çalışıyor!")
        # Redis bağlantısını test et
        if check_redis():
            print("[OK] Redis bağlantısı başarılı!")
        else:
            print("[!] Redis container çalışıyor ama bağlantı kurulamıyor (hazır olması bekleniyor)...")
            time.sleep(2)
    else:
        print("[!] Redis container çalışmıyor, başlatılıyor...")
        if start_redis_container():
            print("[OK] Redis container başlatıldı ve hazır!")
        else:
            print("[!] Redis başlatılamadı - sistem in-memory cache kullanacak")
            print("   (Redis opsiyonel - hata olsa bile devam ediliyor)")
    
    print()
    
    # script_dir ve frontend_dir yukarıda tanımlandı (Redis kontrolü öncesinde)
    
    # Servis tanımları

    
    # Seçilen servisleri başlat
    started_services = []
    
    for service_num in sorted(selected_services):
        service = services[service_num]
        
        if service["type"] == "backend":
            start_backend(script_dir)
            started_services.append((service_num, service["title"]))
        elif service["type"] == "frontend":
            start_frontend(frontend_dir)
            started_services.append((service_num, service["title"]))
        elif service["type"] in ("worker", "qagentt"):
            start_worker(script_dir, service_num, service["name"], service["title"], service["script"])
            started_services.append((service_num, service["title"]))
    
    print()
    print("=" * 60)
    print("[OK] Başlatma tamamlandı!")
    print("=" * 60)
    print()
    print("[INFO] Başlatılan Servisler:")
    print("   [OK] Redis (Docker container)")
    
    if started_services:
        for service_num, service_title in started_services:
            print(f"   [OK] {service_num}. {service_title}")
    else:
        print("   [!]  Hiçbir servis başlatılmadı")
    
    print()
    print("=" * 60)
    print()
    print("[TIP] Bu pencereyi kapatabilirsiniz.")
    print("[TIP] Servisleri durdurmak için ilgili pencerelerde Ctrl+C yapın.")
    print()
    
    # Kısa bekle ve çık
    time.sleep(0.5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nİptal edildi.")
        sys.exit(0)
    except Exception as e:
        print(f"\nHATA: {e}")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)

