#!/usr/bin/env python3
"""
QAGENTT Worker — Preferred Stock Learning Agent Runner
=======================================================

Bu script, QAGENTT'yi bağımsız bir terminal penceresinde çalıştırır.
baslat.py'dan 'q' kodu ile başlatılır.

Kullanım:
    python workers/run_qagentt.py
    
Veya baslat.py üzerinden:
    python baslat.py 12790brlq
    (sonundaki 'q' bu script'i tetikler)
"""

import sys
import os
import asyncio
import time
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env if dotenv available
env_path = project_root / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # Manual .env loading
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()


BANNER = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🧠  QAGENTT — Quant Agent Trading Controller               ║
║                                                              ║
║   Preferred Stock System Controller & Auditor                ║
║   Haiku SCAN + Sonnet DEEP (Smart Hybrid v2)                 ║
║                                                              ║
║   Görev: İzle, Analiz Et, Sorunları Bul, Raporla            ║
║   Kural: Kesinlikle işlem AÇMA                               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def print_status(msg: str, icon: str = "►"):
    """Print colored status message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  [{timestamp}] {icon} {msg}")


async def main():
    print(BANNER)
    print_status("QAGENTT başlatılıyor...", "🚀")
    print()

    # ─── 1. Check for API Key ───────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY", "")
    
    if not api_key:
        # Try Redis
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
            r.ping()
            key_from_redis = r.get("psfalgo:agent:gemini_api_key")
            if key_from_redis:
                api_key = key_from_redis.decode("utf-8") if isinstance(key_from_redis, bytes) else key_from_redis
                print_status("API key Redis'ten alındı", "✅")
        except Exception:
            pass
    else:
        print_status("API key .env'den alındı", "✅")

    if not api_key:
        print_status("HATA: GEMINI_API_KEY bulunamadı!", "❌")
        print_status("  → .env dosyasına GEMINI_API_KEY=... ekleyin", "💡")
        print_status("  → veya Redis'e set edin: psfalgo:agent:gemini_api_key", "💡")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)

    print_status(f"Gemini Key: {api_key[:10]}...{api_key[-4:]}", "🔑")

    # ─── 1b. Check for Claude API Key (fallback) ──────────────────
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
    
    if not claude_key:
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
            r.ping()
            key_from_redis = r.get("psfalgo:agent:claude_api_key")
            if key_from_redis:
                claude_key = key_from_redis.decode("utf-8") if isinstance(key_from_redis, bytes) else key_from_redis
                print_status("Claude key Redis'ten alındı (fallback)", "✅")
        except Exception:
            pass
    else:
        print_status("Claude key .env'den alındı (fallback)", "✅")

    if claude_key:
        print_status(f"Claude Key: {claude_key[:15]}...{claude_key[-4:]}", "🔑")
    else:
        print_status("Claude key bulunamadı — sadece Gemini kullanılacak", "⚠️")
    print()

    # ─── 2. Wait for Backend ────────────────────────────────────────
    print_status("Backend bağlantısı bekleniyor...", "⏳")
    
    backend_ready = False
    for attempt in range(30):  # 30 x 2s = max 60s wait
        try:
            from urllib.request import urlopen
            resp = urlopen("http://localhost:8000/health", timeout=2)
            if resp.status == 200:
                backend_ready = True
                break
        except Exception:
            pass
        
        if attempt > 0 and attempt % 5 == 0:
            print_status(f"Backend henüz hazır değil... ({attempt * 2}s)", "⏳")
        time.sleep(2)

    if backend_ready:
        print_status("Backend bağlantısı başarılı!", "✅")
    else:
        print_status("UYARI: Backend'e bağlanılamadı — agent yine de başlayacak", "⚠️")
        print_status("  (MetricsCollector Redis'ten veri alabilir)", "💡")
    
    print()

    # ─── 3. Check Redis ─────────────────────────────────────────────
    redis_ok = False
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        redis_ok = True
        print_status("Redis bağlantısı başarılı!", "✅")
    except Exception as e:
        print_status(f"UYARI: Redis bağlantısı yok — {e}", "⚠️")
        print_status("  (Agent in-memory çalışacak, hafıza persist edilmeyecek)", "💡")
    
    print()

    # ─── 4. Load Static Data (janalldata.csv) ──────────────────────
    try:
        from app.market_data.static_data_store import initialize_static_store
        store = initialize_static_store()
        if store and store.is_loaded():
            print_status(f"Static data yüklendi: {len(store.get_all_symbols())} sembol", "✅")
        else:
            store.load_csv()
            if store.is_loaded():
                print_status(f"Static data CSV'den yüklendi: {len(store.get_all_symbols())} sembol", "✅")
            else:
                print_status("Static data yüklenemedi — truth tick analizi sınırlı olacak", "⚠️")
    except Exception as e:
        print_status(f"Static data yükleme hatası: {e}", "⚠️")
    
    print()

    # ─── 5. Start Learning Agent ────────────────────────────────────
    print_status("QAGENTT Learning Agent başlatılıyor...", "🧠")
    print()

    try:
        from app.agent.learning_agent import PreferredStockLearningAgent
        
        # CRITICAL: mode="v2" enables Smart Hybrid (Haiku scan + Sonnet deep)
        # which is the ONLY mode that persists learnings via _persist_evolving_knowledge()
        # v1 mode has NO persistent learning — it just calls Gemini and discards results
        agent_mode = "v2" if claude_key else "v1"
        
        agent = PreferredStockLearningAgent(
            api_key=api_key,
            claude_api_key=claude_key if claude_key else None,
            quick_interval=300,      # 5 dakika
            trend_interval=1800,     # 30 dakika
            deep_interval=7200,      # 2 saat
            mode=agent_mode,
        )
        
        await agent.start()
        
        if agent_mode == "v2":
            provider_info = "v2 Smart Hybrid (Haiku+Sonnet)"
        elif agent.claude:
            provider_info = "v1 Gemini + Claude Fallback"
        else:
            provider_info = "v1 Gemini Only"
        
        print()
        print("  ╔═══════════════════════════════════════════════════╗")
        print("  ║  🧠 QAGENTT AKTİF — İzliyor & Öğreniyor         ║")
        print("  ╟───────────────────────────────────────────────────╢")
        print(f"  ║  Mode:          {provider_info:<30} ║")
        if agent_mode == "v2":
            print("  ║  Haiku SCAN:    Her 5 dakikada (anomali tarama)   ║")
            print("  ║  Sonnet DEEP:   Anomali + Her 2 saatte (öğrenme) ║")
            print("  ║  Bilgi Persist: Redis + Disk backup               ║")
        else:
            print("  ║  Quick Check:   Her 5 dakikada                   ║")
            print("  ║  Trend Analiz:  Her 30 dakikada                  ║")
            print("  ║  Derin Analiz:  Her 2 saatte                     ║")
        print("  ╟───────────────────────────────────────────────────╢")
        print("  ║  Durdurmak için: Ctrl+C                          ║")
        print("  ╚═══════════════════════════════════════════════════╝")
        print()

        # ─── 5. Run Forever (until Ctrl+C) ──────────────────────────
        status_interval = 300  # Print status every 5 minutes
        last_status_time = time.time()
        
        while agent.is_running:
            await asyncio.sleep(10)

            # Periodic status print
            now = time.time()
            if now - last_status_time >= status_interval:
                last_status_time = now
                s = agent.status
                active = s.get('active_provider', '?')
                
                # v2 mode stats (keys: v2_scan_count, v2_deep_count)
                scans = s.get('v2_scan_count', s.get('quick_checks', 0))
                deeps = s.get('v2_deep_count', s.get('deep_analyses', 0))
                patterns = s.get('patterns_learned', 0)
                cycles = s.get('total_cycles', 0)
                daily_cost = s.get('v2_daily_cost_usd', 0)
                
                print_status(
                    f"Cycles: {cycles} | "
                    f"Scans: {scans} | Deep: {deeps} | "
                    f"Patterns: {patterns} | "
                    f"Cost: ${daily_cost:.3f}",
                    "📊"
                )

                # Print latest insight snippet
                if agent.latest_insight:
                    insight_type = agent.latest_insight.get("type", "?")
                    insight_time = agent.latest_insight.get("timestamp", "?")
                    insight_provider = agent.latest_insight.get("provider", "?")
                    print_status(f"Son analiz: {insight_type} via {insight_provider} @ {insight_time}", "💭")

    except KeyboardInterrupt:
        print()
        print_status("Durduruluyor...", "🛑")
        
        if agent and agent.is_running:
            await agent.stop()
        
        s = agent.status if agent else {}
        print()
        print("  ╔═══════════════════════════════════════════════════╗")
        print("  ║  QAGENTT — Günlük Özet                           ║")
        print("  ╟───────────────────────────────────────────────────╢")
        print(f"  ║  Toplam Cycle:     {s.get('total_cycles', 0):>6}                       ║")
        print(f"  ║  Quick Checks:     {s.get('quick_checks', 0):>6}                       ║")
        print(f"  ║  Trend Analizleri: {s.get('trend_analyses', 0):>6}                       ║")
        print(f"  ║  Derin Analizler:  {s.get('deep_analyses', 0):>6}                       ║")
        print(f"  ║  Öğrenilen Pattern:{s.get('patterns_learned', 0):>6}                       ║")
        print(f"  ║  Gemini Calls:     {s.get('gemini_stats', {}).get('daily_calls', 0):>6}/1500                  ║")
        print(f"  ║  Uptime:           {str(s.get('uptime', 'N/A'))[:20]:>20}   ║")
        print("  ╚═══════════════════════════════════════════════════╝")
        print()

    except Exception as e:
        print_status(f"HATA: {e}", "❌")
        import traceback
        traceback.print_exc()
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  [🛑] QAGENTT sonlandırıldı.")
    except Exception as e:
        print(f"\n  [❌] HATA: {e}")
        input("\nDevam etmek için Enter'a basın...")
