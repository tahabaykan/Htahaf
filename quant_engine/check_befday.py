import json, sys
sys.path.insert(0, '.')
from app.core.redis_client import get_redis_client

r = get_redis_client()

# Check date key
date_val = r.get('psfalgo:befday:date:IBKR_PED')
date_str = date_val.decode() if isinstance(date_val, bytes) else date_val
print(f"BEFDAY date key: {date_str}")

# Check befday positions
bef_data = r.get('psfalgo:befday:positions:IBKR_PED')
if bef_data:
    bef_s = bef_data.decode() if isinstance(bef_data, bytes) else bef_data
    bef_list = json.loads(bef_s)
    bef_map = {p['symbol']: p['qty'] for p in bef_list}
    print(f"BEFDAY positions count: {len(bef_list)}")
else:
    bef_map = {}
    print("NO BEFDAY positions!")

# Check current positions
cur_data = r.get('psfalgo:positions:IBKR_PED')
cur_map = {}
if cur_data:
    cur_s = cur_data.decode() if isinstance(cur_data, bytes) else cur_data
    cur_obj = json.loads(cur_s)
    if isinstance(cur_obj, dict):
        for sym, p in cur_obj.items():
            cur_map[sym] = p.get('qty', 0) if isinstance(p, dict) else 0
    elif isinstance(cur_obj, list):
        for p in cur_obj:
            cur_map[p.get('symbol', '')] = p.get('qty', 0)
    print(f"Current positions count: {len(cur_map)}")
else:
    print("NO current positions!")

# Show mismatches
mismatches = []
problem_syms = ['PEB PRH','ECCU','FGN','HWCPZ','MET PRF','VNO PRO','VNO PRL','GS PRA','MS PRP']
for sym in problem_syms:
    bef = bef_map.get(sym, 'MISSING')
    cur = cur_map.get(sym, 'MISSING')
    match = "OK" if bef != 'MISSING' and cur != 'MISSING' and abs(float(bef) - float(cur)) < 0.01 else "MISMATCH"
    print(f"  {sym:14s}  BEF={str(bef):>10s}  CUR={str(cur):>10s}  {match}")
