
import asyncio
import logs
import sys
import signal
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from app.core.logger import logger
from app.orchestrator.runall_orchestrator import RunallOrchestrator, OrchestratorMode
from app.config import config_loader

async def run_observe_mode():
    """
    Runs the RunallOrchestrator in OBSERVE_ONLY mode.
    This script is safe to run alongside the legacy Janall/PSFALGO system.
    It will:
    1. Read orders from order_controller (via symbol_memory)
    2. Evaluate what it WOULD do (cancel, replace)
    3. Log decisions to logs/observe_actions_YYYYMMDD.jsonl
    4. adhere to 'NO SIDE EFFECTS' rule (OBSERVE_ONLY mode)
    """
    print("============================================================")
    print("   RUNALL ORCHESTRATOR - OBSERVE ONLY MODE")
    print("   Safe to run alongside Legacy System")
    print("============================================================")
    
    # Load config (force OBSERVE_ONLY safety)
    config = config_loader.load_config()
    runall_config = config.get('runall_orchestrator', {})
    runall_config['mode'] = 'OBSERVE_ONLY'  # Force override for safety
    runall_config['selective_cancel_enabled'] = False
    
    # Initialize Orchestrator
    try:
        orchestrator = RunallOrchestrator(runall_config)
        print(f"✅ Orchestrator Initialized (Mode: {orchestrator.mode.value})")
    except Exception as e:
        print(f"❌ Failed to initialize orchestrator: {e}")
        return

    # Mock/Wire dependencies if needed
    # The orchestrator uses symbol_memory which should connect to order_controller
    # In a standalone script, we might need to initialize the shared components
    # But usually simple structure is enough if dependencies are imported correctly
    
    print("\n🚀 Starting Loop (Press Ctrl+C to stop)...")
    print(f"   Log File: logs/observe_actions_{datetime.now().strftime('%Y%m%d')}.jsonl")
    
    running = True
    
    def handle_sigint(sig, frame):
        nonlocal running
        print("\n🛑 Stopping...")
        running = False
        
    signal.signal(signal.SIGINT, handle_sigint)

    while running:
        try:
            # Run one tick
            await orchestrator.tick()
            
            # Print heartbeat
            print(f".", end="", flush=True)
            
            # Wait for next tick
            await asyncio.sleep(orchestrator.phase_tick_seconds)
            
        except Exception as e:
            logger.error(f"Error in observe loop: {e}", exc_info=True)
            await asyncio.sleep(5)  # Wait on error

if __name__ == "__main__":
    try:
        asyncio.run(run_observe_mode())
    except KeyboardInterrupt:
        pass
