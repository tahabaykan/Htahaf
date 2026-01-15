
import redis
import json
import sys

# Connect to Redis
try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.ping()
    print("Redis connected.")
except Exception as e:
    print(f"Redis connection failed: {e}")
    sys.exit(1)

# 1. Check Universe
univ_json = r.get("market_context:universe")
if not univ_json:
    print("❌ market_context:universe NOT FOUND!")
else:
    univ = json.loads(univ_json)
    print(f"✅ Universe found. Count: {len(univ)}")

    # 2. Check individual keys
    empty_count = 0
    valid_count = 0
    error_count = 0
    
    print("\nChecking first 50 symbols...")
    for i, symbol in enumerate(list(univ.keys())[:50]):
        key = f"market_context:{symbol}:5m"
        try:
            length = r.llen(key)
            if length == 0:
                empty_count += 1
                if i < 5: print(f"  ❌ Empty key: {key}")
            else:
                valid_count += 1
                if i < 5: 
                    item = r.lindex(key, 0)
                    print(f"  ✅ {symbol}: {length} entries. Last: {item}")
        except Exception as e:
            error_count += 1
            print(f"  ⚠️ Error checking {key}: {e}")

    print(f"\nSummary (Sample of 50):")
    print(f"  Found with Data: {valid_count}")
    print(f"  Empty/Missing:   {empty_count}")
    print(f"  Errors:          {error_count}")
