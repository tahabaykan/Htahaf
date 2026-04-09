import sys
sys.path.insert(0, '.')
from app.agent.exdiv_analyzer import ExDivFlashAnalyzer

a = ExDivFlashAnalyzer()
a.load_data()

# Specific test stocks
tickers = ['DLR PRJ', 'F PRB', 'PSA PRF', 'BAC PRB', 'SWKHL', 'FITBP']
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
    print(f"  Ex-div dates: {', '.join(ex['exdiv_dates'][-5:])}")
    
    print(f"\n  WINDOWS:")
    for k, v in pat['windows'].items():
        print(f"    {k:20s}: ret={v['total_ret']:+.3f}%  pos={v['avg_pos_rate']:.0%}")
    
    print(f"\n  SIGNALS:")
    if not pat['signals']:
        print(f"    (none)")
    for s in pat['signals']:
        star = '***' if s.get('p_value', 1) < 0.05 else '**' if s.get('p_value', 1) < 0.10 else ''
        print(f"    {s['action']:12s}: day{s['entry_day']:+3d}→day{s['exit_day']:+3d} "
              f"ret={s['expected_return']:+.2f}% win={s['win_rate']:.0%} "
              f"p={s.get('p_value', 1):.3f} {star}")
    
    print(f"\n  NEXT EXDIV: {pred.get('predicted_date', 'N/A')} ({pred.get('status', 'N/A')})")
