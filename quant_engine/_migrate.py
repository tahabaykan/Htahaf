"""Migrate existing tt_training_result.json into the daily learning storage."""
import json, os, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, r"C:\StockTracker\quant_engine")

# Storage paths
LEARNING_DIR = Path(r"C:\StockTracker\quant_engine\tt_learning")
DAILY_DIR = LEARNING_DIR / "daily"
CUMULATIVE_FILE = LEARNING_DIR / "cumulative_insights.json"

for d in [LEARNING_DIR, DAILY_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Load existing result
src = r"C:\StockTracker\quant_engine\tt_training_result.json"
data = json.load(open(src, encoding="utf-8"))
raw = data.get("raw_analysis", {})

# Extract date from analysis_time
analysis_time = raw.get("analysis_time", "")
if analysis_time:
    today = analysis_time[:10]  # YYYY-MM-DD
else:
    today = datetime.now().strftime("%Y-%m-%d")

print(f"Migrating analysis from {today}")
print(f"  Symbols: {raw.get('total_symbols_analyzed', 0)}")
print(f"  Groups: {raw.get('total_groups', 0)}")

# Save as daily snapshot
daily_file = DAILY_DIR / f"{today}.json"
daily_data = {
    "date": today,
    "timestamp": data.get("timestamp", datetime.now().isoformat()),
    "elapsed_seconds": raw.get("elapsed_seconds", 0),
    "analysis": raw,
}
daily_file.write_text(
    json.dumps(daily_data, ensure_ascii=False, indent=2, default=str),
    encoding="utf-8",
)
print(f"  Saved daily: {daily_file} ({daily_file.stat().st_size/1024:.0f} KB)")

# Build initial cumulative
cumulative = {
    "created": datetime.now().isoformat(),
    "last_updated": datetime.now().isoformat(),
    "days_analyzed": [today],
    "symbol_history": {},
    "group_trends": {},
    "top_performers": [],
    "learning_notes": [],
}

groups = raw.get("groups", {})
total_ticks = 0
for g_name, g_data in groups.items():
    total_ticks += g_data.get("total_ticks_group", 0)
    
    cumulative["group_trends"][g_name] = [{
        "date": today,
        "direction": g_data.get("group_direction"),
        "total_ticks": g_data.get("total_ticks_group", 0),
        "active_count": g_data.get("active_count", 0),
        "busiest_window": g_data.get("group_busiest_window"),
        "buyer_vs_seller": g_data.get("buyer_vs_seller"),
    }]

    for stock in g_data.get("top_stocks", []):
        sym = stock.get("symbol", "")
        if not sym:
            continue
        cumulative["symbol_history"][sym] = [{
            "date": today,
            "group": g_name,
            "interest_score": stock.get("interest_score", 0),
            "mm_score": stock.get("mm_score", 0),
            "total_ticks": stock.get("total_ticks", 0),
            "vol_adv_pct": stock.get("vol_adv_total_pct", 0),
            "spread_bps": stock.get("overall_spread_bps", 0),
            "fbtot": stock.get("fbtot"),
            "sfstot": stock.get("sfstot"),
            "gort": stock.get("gort"),
            "busiest_window": stock.get("busiest_window"),
        }]

CUMULATIVE_FILE.write_text(
    json.dumps(cumulative, ensure_ascii=False, indent=2, default=str),
    encoding="utf-8",
)

print(f"  Total truth ticks: {total_ticks:,}")
print(f"  Symbols tracked: {len(cumulative['symbol_history'])}")
print(f"  Groups tracked: {len(cumulative['group_trends'])}")
print(f"  Cumulative: {CUMULATIVE_FILE} ({CUMULATIVE_FILE.stat().st_size/1024:.0f} KB)")
print("Migration complete!")
