import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
symbol = 'NRUC'

print(f"--- {symbol} ---")

# 1. Market Context List
list_key = f"market_context:{symbol}:5m"
ctx_len = r.llen(list_key)
print(f"Context Len: {ctx_len}")

l = r.lrange(list_key, 0, 20)
for i, item in enumerate(l):
    d = json.loads(item)
    print(f"Idx {i}: last={d.get('last')} prev={d.get('prev_close')} ts={d.get('ts')}")

# 2. Truth Volavs
inspect_key = f"truth_ticks:inspect:{symbol}"
inspect_json = r.get(inspect_key)
if inspect_json:
    inspect = json.loads(inspect_json)
    timeline = inspect.get('data', {}).get('volav_timeline', [])
    print(f"Timeline Count: {len(timeline)}")
    if timeline:
        volavs = timeline[0].get('volavs', [])
        if volavs:
            print(f"First Volav Price: {volavs[0].get('price')}")
        else:
            print("First Volav: No volavs in window")
else:
    print("No inspect data")
