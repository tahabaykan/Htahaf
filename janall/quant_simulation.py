
import pandas as pd
import random
from quant_brain import QuantBrain, MarketData

def run_simulation():
    print("="*60)
    print("QUANT STRATEGY SIMULATION: SPREAD CAPTURE")
    print("="*60)
    
    brain = QuantBrain()
    
    # 1. Setup Synthetic Market: "The Illiquid Preferred"
    # True Price is hovering around $24.25
    # Beholders are asking $24.50
    # Bargain hunters are bidding $24.00
    true_value = 24.25
    spread = 0.50
    
    print(f"Scenario: Preferred Stock 'P-ILLIQ'")
    print(f"True Value: ${true_value}")
    print(f"Spread: ${spread} (Wide!)")
    
    # Simulating 100 ticks of market data
    ticks = []
    for i in range(100):
        # Random walk of true value
        true_value += random.gauss(0, 0.02)
        
        # Market Maker quotes around true value
        bid = round(true_value - (spread / 2) - random.uniform(0, 0.05), 2)
        ask = round(true_value + (spread / 2) + random.uniform(0, 0.05), 2)
        
        # Volumes (random skew)
        bid_size = random.randint(100, 1000)
        ask_size = random.randint(100, 1000)
        
        ticks.append(MarketData('P-ILLIQ', bid, ask, true_value, bid_size, ask_size, 0, i))

    # 2. Run Strategies
    
    # Strategy A: "The Retail Trader" (Market Orders)
    # Buys immediately when "signal" says go (randomly every 10 ticks)
    retail_pnl = 0
    retail_trades = 0
    
    # Strategy B: "The Quant" (Passive Limit Orders)
    # Uses QuantBrain to place Limit orders inside the spread
    quant_pnl = 0
    quant_trades = 0
    
    print("\nStarting Simulation Loop...")
    
    for i, market_data in enumerate(ticks):
        # --- Retail Logic ---
        # Dumb logic: Buy every 10th tick
        if i % 10 == 0:
            # Market Buy = Pay the ASK price
            execution_price = market_data.ask 
            
            # Mark to Market (Instant PnL vs Fair Value)
            fair_val_at_execution = brain.calculate_fair_value(market_data)
            pnl = fair_val_at_execution - execution_price
            
            retail_pnl += pnl
            retail_trades += 1
            # print(f"Retail BUY @ {execution_price} (FV: {fair_val_at_execution}) -> PnL: {pnl:.2f}")

        # --- Quant Logic ---
        # Smart logic: Use Brain
        signal = brain.get_market_maker_signal(market_data)
        
        if signal and signal.action == 'BUY':
            # We place a LIMIT order at signal.price (Bid + 0.01)
            # SIMULATION MATCHING ENGINE:
            # Does price drop enough to fill us?
            # For simplicity: If TrueValue < LimitPrice, we get filled (Lucky fill)
            # OR roughly: If we are the best bid, maybe someone hits us?
            # Let's assume 30% fill rate for passive orders to be conservative
            is_filled = random.random() < 0.30
            
            if is_filled:
                execution_price = signal.price
                fair_val_at_execution = brain.calculate_fair_value(market_data)
                
                # Check if we got toxic fill (Buying right before crash)
                # But generally, buying below FV is good
                pnl = fair_val_at_execution - execution_price
                
                quant_pnl += pnl
                quant_trades += 1
                # print(f"Quant BUY @ {execution_price} (FV: {fair_val_at_execution}) -> PnL: {pnl:.2f}")

    # 3. Results
    print("\n" + "="*60)
    print("RESULTS REPORT")
    print("="*60)
    
    if retail_trades > 0:
        print(f"Retail Strategy (Market Orders):")
        print(f"  Trades: {retail_trades}")
        print(f"  Total Slippage Cost: ${retail_pnl:.2f}")
        print(f"  Avg Cost per Trade: ${retail_pnl/retail_trades:.2f}")
        print("  (Negative means you paid the spread)")
        
    print("-" * 30)
    
    if quant_trades > 0:
        print(f"Quant Strategy (Passive Limits):")
        print(f"  Trades: {quant_trades} (Fill Rate approx 30%)")
        print(f"  Total Alpha/Edge: ${quant_pnl:.2f}")
        print(f"  Avg Gain per Trade: ${quant_pnl/quant_trades:.2f}")
        print("  (Positive means you captured the spread!)")
    else:
        print("Quant Strategy: No trades filled (Too passive?)")
        
    print("\nCONCLUSION:")
    diff = (quant_pnl/quant_trades) - (retail_pnl/retail_trades) if quant_trades and retail_trades else 0
    print(f"Quant Improvement: ${diff:.2f} per share")

if __name__ == "__main__":
    run_simulation()
