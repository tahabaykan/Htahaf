import sys
sys.path.insert(0, '.')
from app.agent.exdiv_analyzer import ExDivFlashAnalyzer

a = ExDivFlashAnalyzer()
a.load_data()

# Test: DLR PRJ
tickers = ['DLR PRJ', 'F PRB', 'PSA PRF', 'BAC PRB']
for tk in tickers:
    print(f"\n{'='*60}")
    r = a.analyze_single_sync(tk)
    if r is None:
        print(f"  {tk}: NO RESULT")
        continue
    
    ex = r['exdiv']
    pat = r['patterns']
    pred = r['prediction']
    
    print(f"  {tk}")
    print(f"  Div: ${r['div_amount']:.4f}  Yield: {r['yield_pct']:.1f}%")
    print(f"  ExDiv cycles: {ex['n_cycles']}, Quality: {ex['quality']}, Avg: {ex['avg_cycle_len']:.1f}d")
    print(f"  Pattern strength: {pat['pattern_strength']}%")
    
    print(f"\n  ---WINDOWS---")
    for k, v in pat['windows'].items():
        print(f"    {k}: ret={v['total_ret']:+.3f}% pos={v['avg_pos_rate']:.1%}")
    
    print(f"\n  ---SIGNALS---")
    if not pat['signals']:
        print(f"    No signals")
    for s in pat['signals']:
        star = '***' if s.get('p_value', 1) < 0.05 else '**' if s.get('p_value', 1) < 0.10 else ''
        print(f"    {s['action']:12s}: entry={s['entry_day']:+3d} exit={s['exit_day']:+3d} "
              f"ret={s['expected_return']:+.2f}% win={s['win_rate']:.0%} "
              f"p={s.get('p_value', 1):.3f} {star}")
    
    print(f"\n  ---PREDICTION---")
    print(f"    Last exdiv: {pred.get('last_exdiv', 'N/A')}")
    print(f"    Next predicted: {pred.get('predicted_date', 'N/A')}")
    print(f"    Status: {pred.get('status', 'N/A')}")

# Quick batch stats
print(f"\n\n{'='*60}")
print("  BATCH STATS")
print(f"{'='*60}")

stocks = a.get_available_stocks()
ok = 0
top_patterns = []
for tk in stocks:
    r = a.analyze_single_sync(tk)
    if r:
        ok += 1
        s = r['patterns']
        top_patterns.append((tk, s['pattern_strength'], r['yield_pct'], 
                           r['exdiv']['n_cycles'], r['exdiv']['quality']))

top_patterns.sort(key=lambda x: x[1], reverse=True)
print(f"\n  Analyzed: {ok}/{len(stocks)}")
print(f"\n  TOP 20 BY PATTERN STRENGTH:")
print(f"  {'Ticker':15s} {'Str%':>5s} {'Yld%':>5s} {'Cyc':>4s} {'Q':>5s}")
print(f"  {'-'*38}")
for tk, str_pct, yld, cyc, q in top_patterns[:20]:
    print(f"  {tk:15s} {str_pct:>5.1f} {yld:>5.1f} {cyc:>4d} {q:>5s}")
