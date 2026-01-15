
import sys
import os
from app.mm.greatest_mm_engine import GreatestMMEngine, MMScenarioType
from app.market_data.static_data_store import StaticDataStore

def debug_sojc():
    symbol = "SOJC"
    
    # 1. Load Static Data for PrevClose
    store = StaticDataStore()
    store.load_csv()
    static = store.get_static_data(symbol)
    
    if not static:
        print(f"ERROR: {symbol} not found in Static Data")
        return

    prev_close = float(static.get('prev_close', 0))
    print(f"Symbol: {symbol}")
    print(f"Prev Close: {prev_close}")
    
    # 2. Values from User Screenshot
    bid = 22.00
    ask = 22.07
    spread = 0.07
    son5_tick = 22.07
    
    # 3. Calculated Inputs
    entry_long = 22.01  # From Screenshot
    entry_short = 22.06 # Estimated (Ask - 15% spread)
    
    # 4. Unknowns (Assume 0 for now, or check pricing overlay if possible)
    benchmark_chg = 0.0 
    
    print(f"Bid: {bid}, Ask: {ask}, Spread: {spread}")
    print(f"Son5Tick: {son5_tick}")
    print(f"Entry Long: {entry_long}")
    
    # 5. Run Engine Logic
    engine = GreatestMMEngine()
    
    scenario = engine.compute_mm_scenario(
        MMScenarioType.ORIGINAL,
        bid, ask, spread, prev_close, benchmark_chg,
        entry_long, entry_short, son5_tick
    )
    
    print("\n--- SCORE BREAKDOWN ---")
    print(f"b_long (Son5 - Entry): {scenario.b_long:.4f}")
    print(f"a_long (Ask - Son5):   {scenario.a_long:.4f}")
    print(f"Ucuzluk (Entry - Prev): {scenario.ucuzluk:.4f}")
    
    print("\n--- FORMULA ---")
    term1 = 200 * scenario.b_long
    term2 = 4 * (scenario.b_long / scenario.a_long)
    term3 = -50 * scenario.ucuzluk
    
    print(f"200 * b:       {term1:.2f}")
    print(f"4 * (b/a):     {term2:.2f}")
    print(f"-50 * Ucuzluk: {term3:.2f}")
    print(f"TOTAL:         {term1 + term2 + term3:.2f}")

if __name__ == "__main__":
    debug_sojc()
