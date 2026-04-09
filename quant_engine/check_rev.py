import redis, json
r = redis.Redis()

# REV order structure
print("=== REV ORDER STRUCTURE (DDT) ===")
data = r.get("psfalgo:revorders:active:DDT")
if data:
    d = json.loads(data)
    print(json.dumps(d, indent=2))

# REV queue (list type)
print("\n=== REV QUEUE HAMPRO ===")
items = r.lrange("psfalgo:rev_queue:HAMPRO", 0, 2)
for i, item in enumerate(items):
    d = json.loads(item)
    print(f"\n--- Item {i} ---")
    print(json.dumps(d, indent=2))

# Check type of rev_queue
print(f"\nrev_queue type: {r.type('psfalgo:rev_queue:HAMPRO')}")
print(f"rev_queue length: {r.llen('psfalgo:rev_queue:HAMPRO')}")
