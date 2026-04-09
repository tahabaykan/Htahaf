"""
Hammer L2 Debugger
==================

Prints ALL incoming L2Update messages for debugging.
"""
import sys
import os
import json
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.live.hammer_client import HammerClient
from app.config.settings import settings
from loguru import logger

def main():
    logger.remove()
    
    print("🚀 Connecting to Hammer...")
    client = HammerClient(
        host=settings.HAMMER_HOST,
        port=settings.HAMMER_PORT,
        password=settings.HAMMER_PASSWORD,
        account_key=settings.HAMMER_ACCOUNT_KEY
    )
    
    msg_count = 0
    
    def observer(data):
        nonlocal msg_count
        cmd = data.get('cmd')
        if cmd == 'L2Update':
            msg_count += 1
            print(f"📥 [L2] {json.dumps(data)[:200]}...")

    client.add_observer(observer)
    
    if not client.connect():
        print("❌ Failed to connect")
        return

    print(f"✅ Authenticated. StreamerID: {client.streamer_id}")
    
    # Try subscribing to something very active
    symbols = ["SPY", "TSLA", "NVDA", "AAPL"]
    print(f"📡 Subscribing to L2 for {symbols}...")
    
    l2_cmd = {
        "cmd": "subscribe",
        "sub": "L2",
        "streamerID": client.streamer_id,
        "sym": symbols,
        "transient": False
    }
    client.send_command(l2_cmd)
    
    print("⏳ Listening for 10 seconds...")
    time.sleep(10)
    
    print(f"\n📊 Total L2 messages received: {msg_count}")
    
    client.disconnect()
    print("\n👋 Done")

if __name__ == "__main__":
    main()
