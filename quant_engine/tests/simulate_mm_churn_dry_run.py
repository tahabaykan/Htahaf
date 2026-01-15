
import logging
import time
import random
import sys
import os
from typing import Dict, List, Any
from datetime import datetime

# Add root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Engine
from app.event_driven.strategy.mm_churn_engine import MMChurnEngine

# Setup Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("mm_churn_dry_run")

def run_simulation():
    print("🚀 Starting MM Churn Dry-Run Simulation...")
    
    # 1. Initialize Engine
    engine = MMChurnEngine(tick_size=0.01)
    
    # 2. Setup Symbols
    # A: Tight Spread (0.02)
    # B: Wide Spread (0.20)
    # C: Low Confidence (10.0) + Wide + Low Vol -> Gating Test
    symbols = ['TIGHT_SYM', 'WIDE_SYM', 'LOW_CONF_SYM']
    
    # Market State
    market_state = {
        'TIGHT_SYM': {
            'bid': 100.00, 'ask': 100.02, 'truth': 100.01, 'conf': 100.0, 'volav': 50000, 
            'orders': []
        },
        'WIDE_SYM': {
            'bid': 100.00, 'ask': 100.20, 'truth': 100.10, 'conf': 100.0, 'volav': 50000,
            'orders': []
        },
        'LOW_CONF_SYM': {
            'bid': 100.00, 'ask': 100.20, 'truth': 100.10, 'conf': 10.0, 'volav': 500, # Low Vol
            'orders': []
        }
    }
    
    # Statistics
    stats = {s: {'updates': 0, 'replaces': 0, 'new': 0, 'frozen': 0} for s in symbols}
    
    # Simulation Loop (60 seconds)
    start_time = time.time()
    sim_duration = 60.0
    tick_step = 0.5 # 500ms steps
    
    report_lines = []
    report_lines.append("# MM CHURN DRY-RUN REPORT")
    report_lines.append(f"Date: {datetime.now().isoformat()}")
    report_lines.append(f"Duration: {sim_duration}s")
    report_lines.append("")
    report_lines.append("## Timeline")
    
    current_time = start_time
    step_count = 0
    
    while current_time - start_time < sim_duration:
        elapsed = current_time - start_time
        
        # Simulate Market Updates (Random Walk)
        for sym in symbols:
            # Randomly drift mid
            drift = random.choice([-0.01, 0, 0.01]) if random.random() < 0.8 else 0
            
            md = market_state[sym]
            md['truth'] += drift
            
            # Recalc Bid/Ask based on Spread Profile
            if sym == 'TIGHT_SYM':
                # Spread 0.02
                md['bid'] = md['truth'] - 0.01
                md['ask'] = md['truth'] + 0.01
            else:
                # Spread 0.20
                md['bid'] = md['truth'] - 0.10
                md['ask'] = md['truth'] + 0.10
                
            # Simulate L1 Timestamp (Fresh)
            md['ts'] = current_time
            
            # Stale Test: Freezing LOW_CONF at T=30s
            if sym == 'LOW_CONF_SYM' and 30 < elapsed < 40:
                md['ts'] = current_time - 3.0 # Stale (>2s)
            
        # Run Engine
        for sym in symbols:
            md = market_state[sym]
            
            l1_data = {'bid': md['bid'], 'ask': md['ask'], 'timestamp': md['ts']}
            truth_data = {
                'truth_price': md['truth'], 
                'confidence': md['conf'], 
                'volav': md['volav']
            }
            position = {'size': 0} # Flat
            
            intents = engine.plan_churn(
                symbol=sym,
                l1_data=l1_data,
                truth_data=truth_data,
                position=position,
                active_orders=md['orders'],
                regime='NORMAL',
                current_time=current_time
            )
            
            if intents:
                for intent in intents:
                    action = intent.get('action', 'UNKNOWN')
                    price = intent.get('price', 0)
                    side = intent.get('side', 'UNK')
                    qty = intent.get('qty', 0)
                    
                    stats[sym]['updates'] += 1
                    if action == 'REPLACE':
                        stats[sym]['replaces'] += 1
                        # Update Mock Order
                        for o in md['orders']:
                            if o['id'] == intent['order_id']:
                                o['price'] = price
                                o['qty'] = qty
                    elif action == 'NEW':
                        stats[sym]['new'] += 1
                        # Create Mock Order
                        new_order = {
                            'id': f"{sym}_{int(current_time*1000)}_{side}",
                            'price': price,
                            'qty': qty,
                            'side': side
                        }
                        md['orders'].append(new_order)
                        
                    report_lines.append(f"- `T={elapsed:.1f}s` **{sym}** {action} {side} @ {price:.2f} ({qty} lots) (Bid:{md['bid']:.2f}/Ask:{md['ask']:.2f})")
            
            # Check Frozen State (Implicit)
            # If Engine returns empty during active phase
            if sym == 'LOW_CONF_SYM' and 30 < elapsed < 40 and not intents:
                stats[sym]['frozen'] += 1

        
        current_time += tick_step
        step_count += 1
        time.sleep(0.01) # Fast forward in real time
        
    report_lines.append("")
    report_lines.append("## KPI Summary")
    for sym, data in stats.items():
        report_lines.append(f"### {sym}")
        report_lines.append(f"- Total Updates: {data['updates']}")
        report_lines.append(f"- New Orders: {data['new']}")
        report_lines.append(f"- Replaces: {data['replaces']}")
        report_lines.append(f"- Frozen Cycles (Stale): {data['frozen']}")
        
    # Validation Checks
    report_lines.append("")
    report_lines.append("## Validation Checks")
    
    # 1. Rounding
    report_lines.append("- [ ] **Tick Rounding**: All prices 0.01 increments?")
    
    # 2. Gating
    frozen_count = stats['LOW_CONF_SYM']['frozen']
    report_lines.append(f"- {'✅' if frozen_count > 0 else '❌'} **Stale Gating**: LOW_CONF_SYM frozen during T=30-40s (Count: {frozen_count}).")
    
    # 3. Throttle (Approx Check)
    # TIGHT_SYM updates should be roughly Duration / 2.5s = 60/2.5 = 24 updates max?
    tight_updates = stats['TIGHT_SYM']['updates']
    report_lines.append(f"- {'✅' if tight_updates <= 30 else '❌'} **Throttling**: TIGHT_SYM updates ({tight_updates}) consistent with 2.5s interval (Max ~25-30).")
    
    # 4. Sizing
    # LOW_CONF should use min_lot (200)
    # TIGHT should use max (4000)
    report_lines.append("- [ ] **Low Conf Sizing**: LOW_CONF orders size = 200?")
    report_lines.append("- [ ] **Normal Sizing**: TIGHT orders size = 4000?")

    with open("MM_CHURN_DRY_RUN_REPORT.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print("\n✅ MM Churn Simulation Complete. Report: MM_CHURN_DRY_RUN_REPORT.md")

if __name__ == '__main__':
    run_simulation()
