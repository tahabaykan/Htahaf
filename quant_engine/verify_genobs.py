import requests
import redis
import json
import sys
import os

# Add parent dir
sys.path.append(os.getcwd())

def verify():
    print("CORE: Verifying Genobs Module...")
    
    # 1. Check Redis Connection
    try:
        r = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis Connected")
    except Exception as e:
        print(f"❌ Redis Connection Failed: {e}")
        return

    # 2. Check OFI Keys
    ofi_keys = r.keys("ofi:score:*")
    print(f"✅ Found {len(ofi_keys)} OFI scores in Redis")
    if len(ofi_keys) > 0:
        print(f"   Example: {ofi_keys[0]} = {r.get(ofi_keys[0])}")
        
    # 3. Check API
    try:
        url = "http://localhost:8000/api/genobs/data"
        print(f"Testing API: {url}")
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get('success'):
                count = data.get('count', 0)
                print(f"✅ API Success! Returned {count} rows.")
                if count > 0:
                    row = data['data'][0]
                    print("   Sample Row Keys:", row.keys())
                    print("   Sample Row:", row)
            else:
                print(f"❌ API returned success=False: {data}")
        else:
            print(f"❌ API Failed with Status {res.status_code}")
    except Exception as e:
        print(f"❌ API Call Exception: {e}")
        print("   (Note: You need to restart backend/worker for changes to apply)")

if __name__ == "__main__":
    verify()
