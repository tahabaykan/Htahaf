
import asyncio
import json
from datetime import datetime
from app.core.redis_client import get_redis_client
from app.core.event_bus import EventBus
from app.core.logger import logger

async def test_fill_broadcast():
    print("Testing Fill Event Broadcasting...")
    
    # 1. Create a mock fill event
    fill_data = {
        "event": "FILL",
        "order_id": "TEST_STRATEGY",
        "fill_id": f"test_fill_{int(datetime.now().timestamp())}",
        "symbol": "AAPL",
        "qty": "100.0",
        "price": "150.25",
        "action": "BUY",
        "account_id": "IBKR_PED",
        "timestamp": datetime.now().isoformat()
    }
    
    # 2. Push to Redis Stream
    print(f"Pushing test fill to psfalgo:execution:ledger: {fill_data['symbol']} {fill_data['qty']} @ {fill_data['price']}")
    msg_id = EventBus.xadd("psfalgo:execution:ledger", fill_data)
    print(f"Successfully pushed message with ID: {msg_id}")
    
    # 3. Read it back to verify
    print("Reading back from stream to verify persistence...")
    read_back = EventBus.stream_read("psfalgo:execution:ledger", last_id="0-0", count=5000)
    
    found = False
    if read_back:
        # Check if our message is in there (EventBus.stream_read returns one message or uses count)
        # Actually EventBus.stream_read returns Optional[Dict[str, Any]] with 'id' and 'data'
        pass
        
    # Let's use xrange to see recent entries
    redis = get_redis_client().sync
    entries = redis.xrevrange("psfalgo:execution:ledger", max='+', min='-', count=5)
    
    print("\nRecent Ledger Entries:")
    for eid, data in entries:
        print(f"ID: {eid}, Symbol: {data.get('symbol')}, Qty: {data.get('qty')}, Action: {data.get('action')}")
        if data.get('fill_id') == fill_data['fill_id'] or data.get('order_id') == fill_data['order_id']:
            found = True
            
    if found:
        print("\n✓ SUCCESS: Fill event correctly broadcasted and verified in Redis.")
    else:
        print("\n✗ FAILURE: Fill event not found in Redis stream.")

if __name__ == "__main__":
    asyncio.run(test_fill_broadcast())
