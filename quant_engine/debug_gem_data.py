import redis
import json
import time

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
symbol = 'USB PRQ'

print(f"--- {symbol} ---")

# 1. Timeline
inspect_json = r.get(f"truth_ticks:inspect:{symbol}")
if inspect_json:
    inspect = json.loads(inspect_json)
    timeline = inspect.get('data', {}).get('volav_timeline', [])
    print(f"Timeline Count: {len(timeline)}")
    now = time.time()
    for w in timeline:
        end_ts = w.get('end_timestamp', 0)
        age_h = (now - end_ts) / 3600
        volavs = w.get('volavs', [])
        price = volavs[0].get('price') if volavs else 'N/A'
        print(f"Window: Age={age_h:.1f}h, Price={price}")
else:
    print("No inspect data")

# 2. Market Context
ctx_len = r.llen(f"market_context:{symbol}:5m")
print(f"Context Len: {ctx_len}")

for i, name in [(12, '1h'), (48, '4h'), (78, '1d')]:
    entry_json = r.lindex(f"market_context:{symbol}:5m", i)
    if entry_json:
        entry = json.loads(entry_json)
        print(f"{name} (idx {i}): last={entry.get('last')}, ts={entry.get('ts')}")
    else:
        print(f"{name} (idx {i}): None")
