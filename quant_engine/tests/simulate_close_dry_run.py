
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Any

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.event_driven.decision_engine.hard_exit_engine import HardExitEngine

def run_simulation():
    print("🚀 Starting CLOSE Dry-Run Simulation...")
    
    # 1. Setup Engine
    engine = HardExitEngine()
    
    # 3. Setup Scenario Data (PM-Grade)
    # 8 Symbols:
    # A: WINNER_MM (Profit)
    # B: LOSER_SMALL_MM (Small Loss)
    # C: LOSER_BIG_MM (Big Loss, High Splippage) -> Should be skipped for D
    # D: LOSER_LT (Better Cost than C)
    # E: ILLIQUID_MM (Tie breaker vs F) -> Lower ADV
    # F: LIQUID_MM (Same PnL as E) -> Higher ADV
    # G: WIDE_MM (Tie breaker vs H) -> Wide Spread
    # H: NARROW_MM (Same PnL as G) -> Narrow Spread
    # I: LOW_CONF_MM (Low Confidence - Checks capping)
    
    positions = [
        {'symbol': 'WINNER_MM', 'size': 500, 'avg_cost': 90.0, 'bucket': 'MM', 'mark_price': 100.0},
        {'symbol': 'LOSER_SMALL_MM', 'size': 500, 'avg_cost': 102.0, 'bucket': 'MM', 'mark_price': 100.0},
        {'symbol': 'LOSER_BIG_MM', 'size': 2000, 'avg_cost': 110.0, 'bucket': 'MM', 'mark_price': 100.0}, 
        {'symbol': 'LOSER_LT', 'size': 2000, 'avg_cost': 110.0, 'bucket': 'LT', 'mark_price': 100.0},
        
        # Liquidity Tie Break Pair (Same PnL=FLAT)
        {'symbol': 'ILLIQUID_MM', 'size': 500, 'avg_cost': 100.0, 'bucket': 'MM', 'mark_price': 100.0},
        {'symbol': 'LIQUID_MM', 'size': 500, 'avg_cost': 100.0, 'bucket': 'MM', 'mark_price': 100.0},
        
        # Spread Tie Break Pair (Same PnL=FLAT)
        {'symbol': 'WIDE_MM', 'size': 500, 'avg_cost': 100.0, 'bucket': 'MM', 'mark_price': 100.0},
        {'symbol': 'NARROW_MM', 'size': 500, 'avg_cost': 100.0, 'bucket': 'MM', 'mark_price': 100.0},
        
        {'symbol': 'LOW_CONF_MM', 'size': 500, 'avg_cost': 100.0, 'bucket': 'MM', 'mark_price': 100.0},
    ]
    
    market_data = {
        'WINNER_MM': {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 1000000},
        'LOSER_SMALL_MM': {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 1000000},
        
        # Big Loser MM: Cost = 2.0
        'LOSER_BIG_MM': {'bid': 98, 'ask': 102, 'truth_price': 100.0, 'adv': 1000000},
        # LT Alternative: Cost = 0.5 (2.0 > 1.8 * 0.5) -> Switch!
        'LOSER_LT': {'bid': 99.5, 'ask': 100.5, 'truth_price': 100.0, 'adv': 1000000},
        
        # Illiquid vs Liquid
        'ILLIQUID_MM': {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 5000},   # Should go first
        'LIQUID_MM':   {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 1000000}, # Should go after
        
        # Wide vs Narrow
        'WIDE_MM':   {'bid': 99.0, 'ask': 101.0, 'truth_price': 100.00, 'adv': 1000000}, # Spread 2.0 (Hold/Later)
        'NARROW_MM': {'bid': 99.9, 'ask': 100.1, 'truth_price': 100.00, 'adv': 1000000}, # Spread 0.2 (Exit First)
        
        'LOW_CONF_MM': {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 1000000},
    }
    
    confidence_scores = {k: 90.0 for k in market_data}
    confidence_scores['LOW_CONF_MM'] = 10.0
    
    # 3. Define Timelines
    target_reduction = 500000.0 # Increased to cover all logic
    
    print(f"Target Reduction: ${target_reduction:,.2f}")
    
    # Run Plan
    intents = engine.plan_hard_derisk(
        reduction_notional=target_reduction,
        positions=positions,
        l1_data=market_data,
        truth_data=market_data,
        regime='CLOSE', # Aggressive -> 4000 lots
        mode='HARD_DERISK',
        confidence_scores=confidence_scores,
        rules={}
    )
    
    # 4. Generate Report
    report_lines = []
    report_lines.append("# CLOSE DRY-RUN REPORT (PM-Grade Verification)")
    report_lines.append(f"Date: {datetime.now().isoformat()}")
    report_lines.append(f"Regime: CLOSE (Aggressive, clip_size=4000)")
    report_lines.append(f"Target Reduction: ${target_reduction:,.2f}")
    report_lines.append("")
    
    report_lines.append("## 1. Decision Trace")
    
    total_slippage_usd = 0.0
    mm_count = 0
    lt_count = 0
    profit_exits = 0
    loss_exits = 0
    flat_exits = 0
    
    for i, intent in enumerate(intents):
        sym = intent['symbol']
        qty = intent['qty']
        intent_type = intent['type']
        trace = intent.get('_debug_trace', {})
        
        # Find pos & md
        pos = next(p for p in positions if p['symbol'] == sym)
        md = market_data[sym]
        
        # Metrics
        is_long = pos['size'] > 0
        exec_price = md['bid'] if is_long else md['ask']
        truth = md['truth_price']
        slip_per_share = abs(exec_price - truth)
        total_slip = slip_per_share * qty
        
        pnl = (exec_price - pos['avg_cost']) * qty * (1 if is_long else -1)
        pnl_label = "PROFIT" if pnl > 0.01 else ("LOSS" if pnl < -0.01 else "FLAT")
        
        report_lines.append(f"### {i+1}. {sym} ({intent_type})")
        report_lines.append(f"- **Action**: Sell {qty} shares @ {exec_price}")
        report_lines.append(f"- **Context**: Cost {pos['avg_cost']}, Truth {truth}")
        report_lines.append(f"- **PnL**: ${pnl:,.2f} (**{pnl_label}**)")
        report_lines.append(f"- **Slippage**: ${total_slip:,.2f} ({slip_per_share:.2f}/sh)")
        report_lines.append(f"- **Reasoning**: {'MM Profit' if pnl_label == 'PROFIT' and 'MM' in intent_type else ('LT Switch' if 'LT' in intent_type else 'MM Reduction')}")
        report_lines.append(f"- **Remaining Reduction**: ${trace.get('reduction_remaining', 0):,.2f}")
        
        if trace.get('skipped_candidates'):
            report_lines.append(f"- **Skipped Candidates**:")
            for s in trace['skipped_candidates']:
                report_lines.append(f"  - 🚫 {s['symbol']}: {s['reason']}")
        
        # Aggregates
        total_slippage_usd += total_slip
        if 'MM' in intent_type: mm_count += 1
        else: lt_count += 1
        
        if pnl_label == 'PROFIT': profit_exits += 1
        elif pnl_label == 'LOSS': loss_exits += 1
        else: flat_exits += 1
        
    report_lines.append("")
    report_lines.append("## 2. Aggregate Metrics")
    report_lines.append(f"- **Total Realized Slippage**: ${total_slippage_usd:,.2f}")
    report_lines.append(f"- **MM Exits**: {mm_count}")
    report_lines.append(f"- **LT Exits**: {lt_count}")
    report_lines.append(f"- **Profitable Exits**: {profit_exits}")
    report_lines.append(f"- **Loss Exits**: {loss_exits}")
    report_lines.append(f"- **Flat Exits**: {flat_exits}")
    
    report_lines.append("")
    report_lines.append("## 3. Behavior Verification")
    
    # Automated Checks
    checks = []
    
    # Check 1: Profit Priority (Winner exited first?)
    winner_rank = next((i for i, x in enumerate(intents) if x['symbol'] == 'WINNER_MM'), 999)
    checks.append(f"- {'✅' if winner_rank == 0 else '❌'} **Profit Priority**: WINNER_MM exited at rank {winner_rank+1} (Expected 1).")
    
    # Check 2: Cost Override (Loser Big MM Skipped?)
    big_mm_present = any(x['symbol'] == 'LOSER_BIG_MM' for x in intents)
    lt_rank = next((i for i, x in enumerate(intents) if x['symbol'] == 'LOSER_LT'), 999)
    checks.append(f"- {'✅' if not big_mm_present else '❌'} **Cost Override**: LOSER_BIG_MM skipped (Cost 2.0 > 1.8*0.5).")
    checks.append(f"- {'✅' if lt_rank != 999 else '❌'} **Switch Success**: LOSER_LT selected instead.")
    
    # Check 3: Illiquid Gift (Illiquid exited before Liquid?)
    illiquid_rank = next((i for i, x in enumerate(intents) if x['symbol'] == 'ILLIQUID_MM'), 999)
    liquid_rank = next((i for i, x in enumerate(intents) if x['symbol'] == 'LIQUID_MM'), 999)
    checks.append(f"- {'✅' if illiquid_rank < liquid_rank else '❌'} **Liquidity Tie-Break**: Illiquid (Rank {illiquid_rank+1}) < Liquid (Rank {liquid_rank+1}).")
    
    # Check 4: Spread Preference (Narrow exited before Wide?)
    narrow_rank = next((i for i, x in enumerate(intents) if x['symbol'] == 'NARROW_MM'), 999)
    wide_rank = next((i for i, x in enumerate(intents) if x['symbol'] == 'WIDE_MM'), 999)
    checks.append(f"- {'✅' if narrow_rank < wide_rank else '❌'} **Spread Preference**: Narrow (Rank {narrow_rank+1}) < Wide (Rank {wide_rank+1}).")
    
    # Check 5: Low Conf
    low_conf_present = any(x['symbol'] == 'LOW_CONF_MM' for x in intents)
    checks.append(f"- {'✅' if low_conf_present else '❌'} **Low Confidence**: Exited successfully.")
    
    report_lines.extend(checks)
    
    # Save Report
    with open("CLOSE_RUN_REPORT.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print("\n✅ Simulation Complete. Report generated: CLOSE_RUN_REPORT.md")
    print("\nSnippet of Intents:")
    for i in intents:
        print(f" - {i['type']} {i['symbol']} Qty:{i['qty']}")

if __name__ == "__main__":
    run_simulation()
