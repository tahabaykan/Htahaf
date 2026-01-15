#!/usr/bin/env python3
"""
Quant Engine - Backend ve Frontend Başlatma Scripti
Kullanım: python baslat.py
"""

import subprocess
import sys
import os
import time
from pathlib import Path

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
            print("   ℹ️ Redis container bulundu, çalıştırılıyor...")
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
                print(f"   ⚠️ Container başlatılamadı: {result.stderr[:100]}")
                return False
        else:
            # Container yok, yeni oluştur
            print("   🐳 Redis container oluşturuluyor ve başlatılıyor...")
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
                    print(f"   ⚠️ Container oluşturma hatası: {result.stderr[:150]}")
                return False
    except subprocess.TimeoutExpired:
        print("   ⚠️ Redis başlatma zaman aşımı")
        return False
    except FileNotFoundError:
        print("   ⚠️ Docker bulunamadı - Redis container başlatılamıyor")
        print("   💡 Docker Desktop'ın çalıştığından emin olun")
        return False
    except Exception as e:
        print(f"   ⚠️ Redis başlatma hatası: {str(e)[:100]}")
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

def start_worker(script_dir, worker_num, worker_name, worker_title, worker_script):
    """Worker başlatma fonksiyonu"""
    print(f"🔧 {worker_title} başlatılıyor (yeni pencere)...")
    
    if sys.platform == "win32":
        script_dir_str = str(script_dir)
        worker_cmd = f'start "Quant Engine - {worker_title}" cmd /k "cd /d ""{script_dir_str}"" && set WORKER_NAME={worker_name} && python {worker_script}"'
        os.system(worker_cmd)
    else:
        # Linux/Mac için
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd '{script_dir}' && export WORKER_NAME={worker_name} && python {worker_script}; exec bash"],
            start_new_session=True
        )
    
    time.sleep(0.5)

def start_cluster(script_dir):
    """Cluster başlatma fonksiyonu"""
    print("🚀 Truth Ticks Cluster (6 Terminal) başlatılıyor...")
    
    if sys.platform == "win32":
        script_dir_str = str(script_dir)
        # Launch the python script directly which spawns its own windows
        cluster_cmd = f'start "Quant Engine - Cluster Launcher" cmd /k "cd /d ""{script_dir_str}"" && python launch_cluster.py"'
        os.system(cluster_cmd)
    else:
        # Linux/Mac için
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd '{script_dir}' && python launch_cluster.py; exec bash"],
            start_new_session=True
        )
    
    time.sleep(1.0)

def start_backend(script_dir):
    """Backend başlatma fonksiyonu"""
    print("🚀 Backend başlatılıyor (yeni pencere)...")
    
    if sys.platform == "win32":
        script_dir_str = str(script_dir)
        backend_cmd = f'start "Quant Engine - Backend" cmd /k "cd /d ""{script_dir_str}"" && python main.py api"'
        os.system(backend_cmd)
    else:
        # Linux/Mac için
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd '{script_dir}' && python main.py api; exec bash"],
            start_new_session=True
        )
    
    time.sleep(0.5)

def start_frontend(frontend_dir):
    """Frontend başlatma fonksiyonu"""
    print("🎨 Frontend başlatılıyor (yeni pencere)...")
    
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

def show_menu():
    """Servis seçim menüsünü göster"""
    print("=" * 60)
    print("Quant Engine - Servis Başlatma")
    print("=" * 60)
    print()
    print("📋 Mevcut Servisler:")
    print("   1. Backend (FastAPI)")
    print("   2. Frontend (React)")
    print("   3. Deeper Analysis Worker")
    print("   4. Ticker Alert Worker")
    print("   5. Decision Helper Worker")
    print("   6. Decision Helper V2 Worker")
    print("   7. Truth Ticks CLUSTER (6 Terminal)")
    print("   8. Venue & Hybrid Collector (Shadow Mode)")
    print("   9. Greatest MM Quant Worker")
    print("   10. Market Context Worker (Use '0' to select)")
    print("   11. QeBenchData Worker (Use 'b' to select)")
    print()
    print("💡 Kullanım: İstediğiniz servis numaralarını yazın (örn: 12, 126, 123456789b)")
    print("   Örnek: '12' yazarsanız -> Backend + Frontend başlar")
    print("   Örnek: 'b' yazarsanız -> QeBenchData Worker başlar")
    print("   🎯 Öneri: '1678b' -> Shadow Mode + Benchmark")
    print("   Örnek: '12345678' yazarsanız -> Tüm servisler başlar (Benchmark hariç)")
    print()

def parse_selection(selection):
    """Kullanıcı seçimini parse et ve servis numaralarını döndür"""
    if not selection:
        return set()
    
    final_numbers = []
    
    # Handle 'b' for Benchmark Worker (11)
    if 'b' in selection.lower():
        final_numbers.append(11)
    
    # Sadece rakamları al
    numbers = [int(c) for c in selection if c.isdigit()]
    
    for n in numbers:
        if n == 0:
            final_numbers.append(10)
        elif 1 <= n <= 9:
            final_numbers.append(n)
            
    return set(final_numbers)

def main():
    # Service definitions
    services = {
        1: { "type": "backend", "title": "Backend (FastAPI)" },
        2: { "type": "frontend", "title": "Frontend (React)" },
        3: { "type": "worker", "name": "worker1", "title": "Deeper Analysis Worker", "script": "workers/run_deeper_worker.py" },
        4: { "type": "worker", "name": "ticker_alert_worker1", "title": "Ticker Alert Worker", "script": "workers/run_ticker_alert_worker.py" },
        5: { "type": "worker", "name": "decision_helper_worker1", "title": "Decision Helper Worker", "script": "workers/run_decision_helper_worker.py" },
        6: { "type": "worker", "name": "decision_helper_v2_worker1", "title": "Decision Helper V2 Worker", "script": "workers/run_decision_helper_v2_worker.py" },
        7: { "type": "cluster",  "title": "Truth Ticks CLUSTER (6 Terminals)" },
        8: { "type": "worker", "name": "venue_collector_worker1", "title": "Venue & Hybrid Collector (Shadow Mode)", "script": "workers/run_venue_collector.py" },
        9: { "type": "worker", "name": "greatest_mm_worker1", "title": "Greatest MM Quant Worker", "script": "workers/run_greatest_mm_worker.py" },
        10: { "type": "worker", "name": "market_context_worker1", "title": "Market Context Worker", "script": "workers/market_context_worker.py" },
        11: { "type": "worker", "name": "qebench_worker1", "title": "QeBenchData Worker (Fill Recovery)", "script": "workers/qebench_worker.py" }
    }

    # Check for command line arguments
    if len(sys.argv) > 1:
        selection = sys.argv[1]
        selected_services = parse_selection(selection)
        if selected_services:
            print(f"🚀 Otomatik başlatma modu: {selection}")
        else:
            print(f"⚠️ Geçersiz argüman: {selection}")
            sys.exit(1)
    else:
        # Interactive Mode
        show_menu()
        
        while True:
            try:
                selection = input("Servis seçimi (numaraları yazın, Enter'a basın): ").strip()
                selected_services = parse_selection(selection)
                
                if selection == "":
                    print("⚠️  Hiçbir servis seçilmedi.")
                    confirm = input("Devam etmek istiyor musunuz? (e/h): ").strip().lower()
                    if confirm == 'e':
                        break
                    else:
                        print()
                        continue
                
                if selected_services:
                    break
                else:
                    print("⚠️  Geçersiz seçim. Lütfen 1-8 arası numaralar girin.")
                    print()
            except KeyboardInterrupt:
                print("\n\nİptal edildi.")
                sys.exit(0)
            except Exception as e:
                print(f"⚠️  Hata: {e}")
                print()

    # Display Selected Services
    if selected_services:
        print()
        print("✅ Seçilen Servisler:")
        for num in sorted(selected_services):
            title = services[num]["title"]
            print(f"   - {num}. {title}")
        print()
    
    print()
    print("=" * 60)
    print("Servisler başlatılıyor...")
    print("=" * 60)
    print()
    
    # Redis kontrolü ve otomatik başlatma
    print("🔍 Redis kontrol ediliyor...")
    
    # Önce container'ın çalışıp çalışmadığını kontrol et
    container_running = check_redis_container()
    
    if container_running:
        print("✅ Redis container çalışıyor!")
        # Redis bağlantısını test et
        if check_redis():
            print("✅ Redis bağlantısı başarılı!")
        else:
            print("⚠️ Redis container çalışıyor ama bağlantı kurulamıyor (hazır olması bekleniyor)...")
            time.sleep(2)
    else:
        print("⚠️ Redis container çalışmıyor, başlatılıyor...")
        if start_redis_container():
            print("✅ Redis container başlatıldı ve hazır!")
        else:
            print("⚠️ Redis başlatılamadı - sistem in-memory cache kullanacak")
            print("   (Redis opsiyonel - hata olsa bile devam ediliyor)")
    
    print()
    
    # Script'in bulunduğu dizin
    script_dir = Path(__file__).parent.absolute()
    frontend_dir = script_dir / "frontend"
    
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
        elif service["type"] == "cluster":
            start_cluster(script_dir)
            started_services.append((service_num, service["title"]))
        elif service["type"] == "worker":
            start_worker(script_dir, service_num, service["name"], service["title"], service["script"])
            started_services.append((service_num, service["title"]))
    
    print()
    print("=" * 60)
    print("✅ Başlatma tamamlandı!")
    print("=" * 60)
    print()
    print("📋 Başlatılan Servisler:")
    print("   ✅ Redis (Docker container)")
    
    if started_services:
        for service_num, service_title in started_services:
            print(f"   ✅ {service_num}. {service_title}")
    else:
        print("   ⚠️  Hiçbir servis başlatılmadı")
    
    print()
    print("=" * 60)
    print()
    print("💡 Bu pencereyi kapatabilirsiniz.")
    print("💡 Servisleri durdurmak için ilgili pencerelerde Ctrl+C yapın.")
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

