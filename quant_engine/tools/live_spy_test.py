import sys
import os
import time
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.live.hammer_client import HammerClient
from app.config.settings import settings
from loguru import logger

def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("🚀 Connecting to Hammer Pro for LIVE SPY Data...")
    client = HammerClient(
        host=settings.HAMMER_HOST,
        port=settings.HAMMER_PORT,
        password=settings.HAMMER_PASSWORD,
        account_key=settings.HAMMER_ACCOUNT_KEY
    )
    
    l2_discovered = []
    
    def observer(data):
        cmd = data.get('cmd')
        if cmd == 'L2Update':
            l2_discovered.append(data)
            res = data.get('result', {})
            bids = res.get('bids', [])
            asks = res.get('asks', [])
            msg_type = data.get('type', 'unknown')
            logger.info(f"📥 [L2_DATA] {msg_type} for {res.get('sym')}: {len(bids)} bids, {len(asks)} asks")
            if bids: logger.info(f"   Top Bid: {bids[0].get('price')} x {bids[0].get('size')}")
            if asks: logger.info(f"   Top Ask: {asks[0].get('price')} x {asks[0].get('size')}")
        elif cmd == 'dataStreamerStateUpdate':
            logger.info(f"📡 [StreamerState] {data.get('streamerID')}: {data.get('state')}")

    client.add_observer(observer)
    
    if not client.connect():
        print("❌ Failed to connect")
        return

    # Wait for streamer to be ready
    print("⏳ Waiting for streamer to be ready...")
    ready = client._streamer_ready_event.wait(timeout=10)
    if not ready:
        print(f"⚠️ Streamer {client.streamer_id} not ready, but proceeding...")
    else:
        print(f"✅ Streamer {client.streamer_id} is READY.")

    symbols = ["SPY", "QQQ", "NVDA", "TSLA"]
    print(f"📡 Subscribing to {symbols} with L1 + Manual L2...")
    
    client.subscribe_symbols_batch(symbols)
    
    for symbol in symbols:
        l2_cmd = {
            "cmd": "subscribe",
            "sub": "L2",
            "streamerID": client.streamer_id,
            "sym": symbol,
            "transient": False
        }
        client._send_command(l2_cmd)
    
    print("⏳ Listening for 20 seconds...")
    start_time = time.time()
    while time.time() - start_time < 20:
        if l2_discovered:
            latest = l2_discovered.pop(0)
            res = latest.get('result', {})
            sym = res.get('sym')
            bids = res.get('bids', [])
            asks = res.get('asks', [])
            msg_type = latest.get('type', 'unknown')
            
            logger.info(f"📊 LIVE L2 [{sym}] ({msg_type})")
            if bids: logger.info(f"   BIDS: {[[b.get('price'), b.get('size')] for b in bids[:3]]}")
            if asks: logger.info(f"   ASKS: {[[a.get('price'), a.get('size')] for a in asks[:3]]}")
            
        time.sleep(0.5)

    # Try getQuotes directly one more time
    print(f"\n📡 Requesting getQuotes Snapshot for {symbol}...")
    snapshot = client.get_l2_snapshot(symbol)
    if snapshot:
        print(f"✅ Snapshot received: {json.dumps(snapshot)[:500]}")
    else:
        print("❌ getQuotes returned no data.")

    client.disconnect()
    print("\n👋 Done")

if __name__ == "__main__":
    main()
