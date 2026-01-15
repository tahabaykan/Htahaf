
import asyncio
import websockets
import json
import os
from dotenv import load_dotenv
import logging
from app.market_data.truth_ticks_engine import TruthTicksEngine
from app.market_data.hammer_ingest_stub import HammerIngest

# Load environment variables
load_dotenv(r"c:\StockTracker\quant_engine\.env")

HAMMER_HOST = os.getenv("HAMMER_HOST", "127.0.0.1")
HAMMER_PORT = os.getenv("HAMMER_PORT", "16400")
HAMMER_PASSWORD = os.getenv("HAMMER_PASSWORD")

async def fetch_and_process():
    uri = f"ws://{HAMMER_HOST}:{HAMMER_PORT}"
    print(f"Connecting to Hammer Pro API at {uri}...")
    
    try:
        # Increase max_size to handle large payloads just in case
        async with websockets.connect(uri, max_size=10*1024*1024) as websocket:
            # 0. Expect initial "CONNECTED" message
            init_msg = await websocket.recv()
            print(f"Initial Server Message: '{init_msg}'")
            
            # 1. Connect/Authenticate
            connect_cmd = {
                "cmd": "connect",
                "pwd": HAMMER_PASSWORD,
                "reqID": "auth_req"
            }
            await websocket.send(json.dumps(connect_cmd))
            
            # 2. Get Auth Response
            response = await websocket.recv()
            print(f"Raw Auth Response: '{response}'") # DEBUG
            
            if not response:
                print("Empty response received.")
                return
            
            auth_resp = json.loads(response)
            
            if auth_resp.get("success") != "OK":
                print(f"Authentication Failed: {auth_resp}")
                return

            print("Authentication Successful!")

            # 2. Request Ticks for HBANP (Last 5000 to ensure we have enough after filtering)
            get_ticks_cmd = {
                "cmd": "getTicks",
                "reqID": "hbanp_ticks",
                "regHoursOnly": True,
                "tradesOnly": False, 
                "lastFew": 5000, # Use lastFew to limit data size
                "sym": "HBANP"
            }
            
            await websocket.send(json.dumps(get_ticks_cmd))
            
            # 3. Receive Data
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                
                if data.get("reqID") == "hbanp_ticks":
                    if data.get("success") == "OK":
                        result = data.get("result", {})
                        ticks_data = result.get("data", [])
                        
                        print(f"Received {len(ticks_data)} raw ticks for HBANP.")
                        process_ticks(ticks_data)
                        break
                    else:
                        print(f"getTicks Failed: {data}")
                        break
                        
    except Exception as e:
        print(f"Connection Error: {e}")

def process_ticks(raw_ticks):
    engine = TruthTicksEngine()
    
    # Re-doing normalization for this list specifically since I suspect ingest might miss 's'
    processed_list = []
    for raw in raw_ticks:
        # Map single letters
        s = float(raw.get('s', raw.get('size', raw.get('volume', 0))))
        p = float(raw.get('p', raw.get('last', raw.get('price', 0))))
        e = raw.get('e', raw.get('exch', raw.get('exchange', 'UNKNOWN')))
        t = raw.get('t', raw.get('ts', raw.get('timestamp', 0)))
        
        # Ingest stub normalizer might skip 's' or 'p', so we map manually for robust demo
        processed_list.append({
            'size': s,
            'price': p,
            'exch': str(e).upper(),
            'ts': t,
            'raw': raw
        })
        
    print(f"Total processed ticks: {len(processed_list)}")
    
    accepted = []
    rejected_log = []
    
    # Sort by timestamp to show logical flow
    processed_list.sort(key=lambda x: str(x['ts'])) 

    for t in processed_list:
        if engine.is_truth_tick(t):
            accepted.append(t)
        else:
            rejected_log.append(t)

    print(f"Accepted Truth Ticks: {len(accepted)}")
    
    # Write to file for reliable reading
    with open(r"c:\StockTracker\quant_engine\hbanp_results.txt", "w", encoding="utf-8") as f:
        f.write(f"--- LAST 40 TRUTH TICKS (ACCEPTED) ---\n")
        f.write(f"Total Processed: {len(processed_list)}\n")
        f.write(f"Total Accepted: {len(accepted)}\n\n")
        
        to_show = accepted[-40:]
        for i, t in enumerate(to_show):
            line = f"{i+1:02d}. [ACCEPTED] {t['ts']} | {t['exch']:<5} | Size: {t['size']:<6} | Price: {t['price']}\n"
            f.write(line)
            print(line.strip()) # Also print to stdout

if __name__ == "__main__":
    if not HAMMER_PASSWORD:
        print("ERROR: HAMMER_PASSWORD not found in .env")
    else:
        asyncio.run(fetch_and_process())
