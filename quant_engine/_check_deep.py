import redis, json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Search ALL qagentt keys
keys = r.keys("qagentt*")
print(f"All qagentt keys ({len(keys)}):")
for k in sorted(keys):
    val = r.get(k)
    if val:
        print(f"  {k}: {val[:300]}")
    else:
        print(f"  {k}: (type={r.type(k)})")

print()

# Also check learning_agent keys
keys2 = r.keys("learning_agent*")
print(f"All learning_agent keys ({len(keys2)}):")
for k in sorted(keys2):
    val = r.get(k)
    if val:
        print(f"  {k}: {val[:200]}")

# Check psf:qagentt keys
keys3 = r.keys("psf:qagentt*")
print(f"\nAll psf:qagentt keys ({len(keys3)}):")
for k in sorted(keys3):
    val = r.get(k)
    if val:
        print(f"  {k}: {val[:200]}")
