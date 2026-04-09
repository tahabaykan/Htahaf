"""Quick test: Hammer getTicks."""
import os, sys, time, json
sys.path.insert(0, r"C:\StockTracker\quant_engine")

# Load .env
with open(r"C:\StockTracker\quant_engine\.env", "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import logging
logging.basicConfig(level=logging.WARNING)

# Redirect all output to file
out = open(r"C:\StockTracker\quant_engine\hammer_test_result.txt", "w")

from app.live.hammer_client import HammerClient, set_hammer_client

password = os.getenv("HAMMER_PASSWORD", "")
client = HammerClient(host="127.0.0.1", port=16400, password=password)
ok = client.connect()
out.write(f"Connected: {ok}\n")

if ok:
    set_hammer_client(client)
    time.sleep(3)
    out.write(f"Authenticated: {client.authenticated}\n")

    for sym in ["CIM PRB", "NLY PRD", "PSEC PRA"]:
        out.write(f"\n=== {sym} ===\n")
        result = client.get_ticks(sym, lastFew=50, tradesOnly=True, regHoursOnly=False, timeout=10.0)
        if result:
            data = result.get("data", [])
            out.write(f"Raw ticks: {len(data)}\n")
            if data:
                t = data[0]
                out.write(f"First tick: price={t.get('p')}, size={t.get('s')}, exch={t.get('e')}, time={t.get('t')}\n")
                # Truth tick count
                truth = 0
                for tick in data:
                    size = tick.get("s", 0)
                    venue = str(tick.get("e", "")).upper()
                    is_dark = "FNRA" in venue or "ADFN" in venue or "TRF" in venue or venue == "D"
                    if is_dark:
                        if size in (100, 200):
                            truth += 1
                    else:
                        if size >= 15:
                            truth += 1
                out.write(f"Truth ticks: {truth}/{len(data)}\n")
            else:
                out.write("Empty data array\n")
        else:
            out.write("No result (None returned)\n")
    
    client.disconnect()

out.write("\nDONE\n")
out.close()
print("Output saved to hammer_test_result.txt")
