import redis
r = redis.Redis(host='localhost', decode_responses=True)

lines = []
checks = [
    'tt:ticks:*', 'live:*', 'market_context:*', 'market_data:*',
    'market:*', 'janall:*', 'ofi:*', 'gem:*', 'bench:*',
    'group_index:*', 'psfalgo:positions:*', 'psfalgo:exposure:*',
    'psfalgo:dual_process:*', 'psfalgo:xnl:*', 'psfalgo:revorders:*',
    'psfalgo:trading:*', 'greatest_mm:*', 'qagentt:*', 'proposals:*',
    'truthtick:latest:*', 'truth_ticks:inspect:*',
]

for p in checks:
    n = len(r.keys(p))
    s = 'OK' if n else 'EMPTY'
    lines.append(f"{s:5s} {n:>4} {p}")

lines.append("")
lines.append("PSFALGO KEYS:")
for k in sorted(r.keys('psfalgo:*')):
    t = r.type(k)
    if t == 'string':
        v = r.get(k) or ''
        lines.append(f"  {k}: {v[:70]}")
    else:
        lines.append(f"  {k}: [{t}]")

with open('audit_result.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print("Done")
