
from app.mm.greatest_mm_engine import GreatestMMEngine, MMScenarioType

def simulate_score():
    engine = GreatestMMEngine()
    
    # Scenario: Stale Last Price (Son5Tick) vs Current Quotes
    # Stock crashed or quotes dropped, but Last Print is old and high.
    
    bid = 20.00
    ask = 20.10
    spread = 0.10
    prev_close = 20.00
    benchmark_chg = 0.0
    
    # Son5Tick (Last) is OLD and HIGH (e.g., played at 22.00 earlier)
    son5_tick = 22.00 
    
    entry_long = 20.015 # Bid + 15% spread
    entry_short = 20.085
    
    print(f"--- SIMULATION: Stale High Last Price ---")
    print(f"Bid: {bid}, Ask: {ask}")
    print(f"Son5Tick (Last): {son5_tick} (User sees this as 'Price')")
    
    scenario = engine.compute_mm_scenario(
        MMScenarioType.ORIGINAL,
        bid, ask, spread, prev_close, benchmark_chg,
        entry_long, entry_short, son5_tick
    )
    
    print(f"\nCalculated Values:")
    print(f"b_long (Son5 - Entry): {scenario.b_long:.4f} (Huge Gain Potential?)")
    print(f"a_long (Ask - Son5): {scenario.a_long:.4f} (Risk?)")
    
    if scenario.a_long <= 0.01:
        print(f"WARNING: a_long was clamped to 0.01 because Ask ({ask}) < Son5Tick ({son5_tick})")
        
    print(f"\nScore Components:")
    print(f"200 * b: {200 * scenario.b_long:.2f}")
    print(f"4 * (b/a): {4 * (scenario.b_long / scenario.a_long):.2f} (HUGE RATIO)")
    print(f"TOTAL SCORE: {scenario.mm_long:.2f}")

if __name__ == "__main__":
    simulate_score()
