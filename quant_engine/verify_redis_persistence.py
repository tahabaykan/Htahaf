
import sys
import os
import json
import redis

def check_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=2)
        r.ping()
        print("Redis connected.")
        
        # Check auto_analysis key
        key = "truth_ticks:auto_analysis"
        data = r.get(key)
        
        if data:
            print(f"✅ Key '{key}' FOUND!")
            parsed = json.loads(data)
            print(f"   Success: {parsed.get('success')}")
            print(f"   Processed Count: {parsed.get('processed_count')}")
            print(f"   Updated At: {parsed.get('updated_at')}")
            
            # Check for TF_2D keys in first symbol
            results = parsed.get('data', {})
            if results:
                first_sym = list(results.keys())[0]
                metrics = results[first_sym]
                print(f"   Keys in '{first_sym}': {list(metrics.keys())}")
                if 'TF_2D' in metrics and '2d' in metrics:
                    print("   ✅ Dual keys (2d, TF_2D) present!")
                else:
                    print("   ❌ Key mismatch!")
        else:
            print(f"❌ Key '{key}' NOT FOUND yet.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_redis()
