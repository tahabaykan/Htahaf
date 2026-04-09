"""System Health Check - Redis verilerini okuyarak sistemin durumunu gosterir."""
import redis
import json
from datetime import datetime

r = redis.Redis()

print("=" * 70)
print(f"  QUANT ENGINE - SYSTEM HEALTH CHECK  ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
print("=" * 70)

# 1. Account Status
print("\n=== 1. ACCOUNT STATUS ===")
account_keys = [
    "psfalgo:account_mode",
    "psfalgo:account_selected",
    "psfalgo:recovery:account_open",
    "psfalgo:xnl:running",
    "psfalgo:xnl:running_account",
    "psfalgo:ibkr:active_account",
    "psfalgo:trading:account_mode",
]
for k in account_keys:
    v = r.get(k)
    val = v.decode() if v else "(empty)"
    print(f"  {k:45s} = {val}")

# 2. BEFDAY Data
for acct in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
    key = f"psfalgo:befday:positions:{acct}"
    bef = r.get(key)
    if bef:
        data = json.loads(bef)
        items = data if isinstance(data, list) else []
        print(f"\n=== 2. BEFDAY {acct} ({len(items)} positions) ===")
        for p in items[:15]:
            if isinstance(p, dict):
                sym = p.get("symbol", "?")
                qty = p.get("qty", 0)
                print(f"  {sym:14s} befday_qty = {qty:>8.0f}")
        if len(items) > 15:
            print(f"  ... +{len(items)-15} more")
    else:
        print(f"\n=== 2. BEFDAY {acct} === (NO DATA)")

# 3. Positions (current)
for acct in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
    key = f"psfalgo:positions:{acct}"
    pos = r.get(key)
    if pos:
        data = json.loads(pos)
        if isinstance(data, dict) and data:
            print(f"\n=== 3. CURRENT POSITIONS {acct} ({len(data)} symbols) ===")
            for sym, pdata in list(data.items())[:10]:
                qty = pdata.get("qty", 0)
                pot = pdata.get("potential_qty", 0)
                bef = pdata.get("befday_qty", 0)
                print(f"  {sym:14s}  qty={qty:>8.0f}  pot={pot:>8.0f}  bef={bef:>8.0f}  gap={bef-pot:>8.0f}")
            if len(data) > 10:
                print(f"  ... +{len(data)-10} more")
    # no else: skip if no data

# 4. Execution Ledger (last fills)
print("\n=== 4. EXECUTION LEDGER (last 15 fills) ===")
try:
    entries = r.xrevrange("psfalgo:execution:ledger", count=15)
    if entries:
        for eid, data in entries:
            d = {k.decode(): v.decode() for k, v in data.items()}
            sym = d.get("symbol", "?")
            act = d.get("action", d.get("side", "?"))
            qty = d.get("qty", "0")
            price = d.get("price", "0")
            acct = d.get("account_id", "?")
            ts = d.get("timestamp", "?")
            tag = d.get("tag", "-")
            oid = d.get("order_id", "-")
            # shorten timestamp
            ts_short = ts[11:19] if len(ts) > 19 else ts
            print(f"  {ts_short:10s} {sym:12s} {act:5s} {qty:>8s} @ ${price:>8s} | {acct:10s} | tag={tag}")
    else:
        print("  (no fills in stream)")
except Exception as e:
    print(f"  ERROR: {e}")

# 5. Active REV Orders
print("\n=== 5. ACTIVE REV ORDERS ===")
rev_keys = r.keys("psfalgo:revorders:active:*")
if rev_keys:
    for rk in sorted(rev_keys):
        try:
            data = r.get(rk)
            if data:
                d = json.loads(data)
                sym = rk.decode().split(":")[-1]
                act = d.get("action", "?")
                qty = d.get("qty", "?")
                price = d.get("price", "?")
                tag = d.get("tag", "?")
                method = d.get("method", "?")
                print(f"  {str(sym):14s} {str(act):5s} {str(qty):>6} @ ${str(price):>8} | {str(tag):30s} | {str(method)}")
        except:
            pass
else:
    print("  (no active REV orders)")

# 6. REV Queue
for acct in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
    key = f"psfalgo:rev_queue:{acct}"
    qlen = r.llen(key)
    if qlen > 0:
        print(f"\n=== 6. REV QUEUE {acct} ({qlen} pending) ===")
        items = r.lrange(key, 0, 5)
        for item in items:
            d = json.loads(item)
            print(f"  {str(d.get('symbol','?')):12s} {str(d.get('action','?')):5s} {str(d.get('qty','?')):>6} @ ${str(d.get('price','?')):>8}")

# 7. Pending Orders
pkey = "psfalgo:orders:pending"
plen = r.llen(pkey)
print(f"\n=== 7. PENDING ORDER QUEUE === ({plen} orders)")
if plen > 0:
    items = r.lrange(pkey, 0, 5)
    for item in items:
        d = json.loads(item)
        print(f"  {str(d.get('symbol','?')):12s} {str(d.get('action','?')):5s} qty={d.get('qty','?')} @ ${d.get('price','?')} | {d.get('strategy_tag','?')}")

# 8. Open Orders
for acct in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
    key = f"psfalgo:open_orders:{acct}"
    oo = r.get(key)
    if oo:
        data = json.loads(oo)
        items = data if isinstance(data, list) else []
        if items:
            print(f"\n=== 8. OPEN ORDERS {acct} ({len(items)} orders) ===")
            for o in items[:8]:
                sym = o.get("symbol", "?")
                act = o.get("action", o.get("side", "?"))
                qty = o.get("qty", o.get("quantity", "?"))
                price = o.get("price", o.get("limit_price", "?"))
                print(f"  {sym:14s} {act:5s} qty={str(qty):>6s} @ ${str(price):>8s}")

print("\n" + "=" * 70)
print("  CHECK COMPLETE")
print("=" * 70)
