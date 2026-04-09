"""Show what we actually captured in the training result."""
import json, os
from datetime import datetime

f = r"C:\StockTracker\quant_engine\tt_training_result.json"
data = json.load(open(f, encoding="utf-8"))
raw = data.get("raw_analysis", {})

print("=" * 80)
print("MEVCUT ANALIZ VERISI — KAYITLI")
print("=" * 80)
print(f"Timestamp: {data.get('timestamp', 'N/A')}")
print(f"Symbols analyzed: {raw.get('total_symbols_analyzed', 0)}")
print(f"Groups: {raw.get('total_groups', 0)}")
print(f"Elapsed: {raw.get('elapsed_seconds', 0):.0f}s")
print(f"Mode: {raw.get('mode', 'N/A')}")
print(f"Lookback: {raw.get('lookback_trading_days', 0)} trading days")
print(f"Prompt size: {data.get('prompt_length', 0)} chars")
print(f"Gemini: {'YES' if data.get('gemini_interpretation') and 'ERROR' not in str(data.get('gemini_interpretation','')) else 'NO (rate limited)'}")
print()

# Summary per group
groups = raw.get("groups", {})
total_ticks = 0
total_stocks = 0
print(f"{'GROUP':<25s} {'STOCKS':>6s} {'TICKS':>6s} {'DIRECTION':>15s} {'BUSIEST':>15s}")
print("-" * 80)
for g_name in sorted(groups.keys()):
    g = groups[g_name]
    ticks = g.get("total_ticks_group", 0)
    total_ticks += ticks
    stocks = g.get("active_count", 0)
    total_stocks += stocks
    print(f"{g_name:<25s} {stocks:>6d} {ticks:>6d} {g.get('group_direction','?'):>15s} {g.get('group_busiest_window','?'):>15s}")

print("-" * 80)
print(f"{'TOTAL':<25s} {total_stocks:>6d} {total_ticks:>6d}")
print()

# Top interest scores across all groups
all_stocks = []
for g_name, g in groups.items():
    for s in g.get("top_stocks", []):
        s["_group"] = g_name
        all_stocks.append(s)

print("TOP 20 MOST INTERESTING (by interest_score):")
print(f"{'SYMBOL':<14s} {'GROUP':<22s} {'INT':>5s} {'MM':>5s} {'TICKS':>6s} {'VOL/ADV':>8s} {'SPREAD':>8s} {'FBtot':>8s} {'SFStot':>8s} {'GORT':>7s}")
print("-" * 100)
for s in sorted(all_stocks, key=lambda x: x.get("interest_score", 0), reverse=True)[:20]:
    fbtot = s.get("fbtot")
    sfstot = s.get("sfstot")
    gort = s.get("gort")
    print(
        f"{s.get('symbol','?'):<14s} "
        f"{s.get('_group',''):<22s} "
        f"{s.get('interest_score',0):>5.1f} "
        f"{s.get('mm_score',0):>5.1f} "
        f"{s.get('total_ticks',0):>6d} "
        f"{s.get('vol_adv_total_pct',0):>7.0f}% "
        f"{s.get('overall_spread_bps',0):>7.1f} "
        f"{str(fbtot)[:7] if fbtot else 'N/A':>8s} "
        f"{str(sfstot)[:7] if sfstot else 'N/A':>8s} "
        f"{str(gort)[:6] if gort is not None else 'N/A':>7s}"
    )

print()
print(f"File size: {os.path.getsize(f)/1024:.0f} KB")
