"""Quick test: paper trader components."""
import sys, os
sys.path.insert(0, r"C:\StockTracker\quant_engine")
env_path = os.path.join(r"C:\StockTracker\quant_engine", ".env")
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from tt_paper_trader import LearningMemory, PaperPortfolio, MMStrategy
from app.market_data.static_data_store import initialize_static_store

store = initialize_static_store()
store.load_csv()
strategy = MMStrategy(store)
candidates = strategy.load_candidates()
memory = LearningMemory()
portfolio = PaperPortfolio()

print(f"Candidates: {len(candidates)}")
print(f"Memory stocks: {len(memory.stock_history)}")
print(f"Memory lessons: {len(memory.daily_lessons)}")
print("Top 5 by MM score:")
candidates.sort(key=lambda s: strategy.stock_data.get(s, {}).get("mm_score", 0), reverse=True)
for sym in candidates[:5]:
    sd = strategy.stock_data[sym]
    print(f"  {sym:12s} mm={sd['mm_score']:.1f} lot={sd['lot']} price={sd['price']:.2f} adv={sd['avg_adv']:.0f}")
print("ALL COMPONENTS OK")
