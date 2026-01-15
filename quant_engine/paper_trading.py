
import subprocess
import time
import sys
import os
import signal
from pathlib import Path
from datetime import datetime

# Configuration
QUANT_ENGINE_DIR = Path(__file__).parent
BASLAT_SCRIPT = QUANT_ENGINE_DIR / "baslat.py"
OBSERVE_SCRIPT = QUANT_ENGINE_DIR / "tests" / "run_observe_mode.py"
LOG_DIR = QUANT_ENGINE_DIR / "logs"

def get_today_log_path():
    today_str = datetime.now().strftime('%Y%m%d')
    return LOG_DIR / f"observe_actions_{today_str}.jsonl"

def start_backend():
    print("🚀 Auto-Starting Backend services (127)...")
    # Feed "127\n" to baslat.py to select Backend + Frontend + Truth Ticks
    process = subprocess.Popen(
        [sys.executable, str(BASLAT_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(QUANT_ENGINE_DIR),
        bufsize=1
    )
    
    # Send "127" selection
    try:
        process.stdin.write("127\n")
        process.stdin.flush()
    except Exception as e:
        print(f"⚠️ Failed to send input to backend: {e}")
        
    return process

def start_orchestrator():
    print("🧠 Starting Orchestrator in OBSERVE_ONLY mode...")
    process = subprocess.Popen(
        [sys.executable, str(OBSERVE_SCRIPT)],
        stdout=subprocess.PIPE,  # Capture stdout to avoid clutter
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(QUANT_ENGINE_DIR)
    )
    return process

def tail_log(path, stop_event):
    print(f"\n📄 Tailing Log: {path.name}")
    print("====================================")
    
    # Wait for file to exist
    while not path.exists() and not stop_event():
        print(f"⏳ Waiting for log file... ({datetime.now().strftime('%H:%M:%S')})", end='\r')
        time.sleep(1)
    
    if stop_event(): return
    
    print(f"✅ Log file found! Streaming...      ")
    print("------------------------------------")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            # Go to end of file
            f.seek(0, 2)
            
            while not stop_event():
                line = f.readline()
                if line:
                    print(line.strip())
                else:
                    time.sleep(0.1)
    except Exception as e:
        print(f"\n❌ Error reading log: {e}")

def main():
    print("============================================================")
    print("   PAPER TRADING MODE - OBSERVE_ONLY TEST LAUNCHER")
    print("============================================================")
    
    # Ensure log dir exists
    LOG_DIR.mkdir(exist_ok=True)
    
    # Track processes
    backend_proc = None
    orch_proc = None
    stop_logging = False
    
    def cleanup(signum, frame):
        nonlocal stop_logging
        print("\n\n🛑 Stopping all services...")
        stop_logging = True
        
        if orch_proc:
            print("   Killing Orchestrator...")
            orch_proc.terminate()
            try:
                orch_proc.wait(timeout=2)
            except:
                orch_proc.kill()
        
        if backend_proc:
            print("   Killing Backend...")
            # Backend spawns Docker/other shells, might need aggressive kill
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=2)
            except:
                backend_proc.kill()
                
        print("✅ Shutdown complete. Bye!")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    try:
        # 1. Start Backend
        backend_proc = start_backend()
        
        # Monitor backend output briefly to confirm start
        print("⏳ Waiting for backend to initialize (10s)...")
        time.sleep(10) # Give it time to spin up Redis/FastAPI
        
        # 2. Start Orchestrator
        orch_proc = start_orchestrator()
        
        # 3. Tail Logs
        log_path = get_today_log_path()
        tail_log(log_path, lambda: stop_logging)
        
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        cleanup(None, None)

if __name__ == "__main__":
    main()
