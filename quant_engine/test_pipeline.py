import sys
sys.path.insert(0, '.')
from app.agent.exdiv_pipeline import detect_exdiv_dates, compute_excess_patterns, load_div_info, load_stock_df

div_info = load_div_info()
single = sys.argv[1] if len(sys.argv) > 1 else 'F PRB'

info = div_info.get(single)
if not info:
    print(f"No div info for {single}")
    sys.exit(1)

out = open('pipeline_result.txt', 'w')

det = detect_exdiv_dates(single, info['div_amount'], info['anchor_date'])
out.write(f"{'='*60}\n")
out.write(f"  {single} - EX-DIV PIPELINE v5\n")
out.write(f"{'='*60}\n")
out.write(f"  Div: ${info['div_amount']:.4f}\n")
out.write(f"  Detected: {det['n_confirmed']} ex-divs (quality={det['quality']})\n")
out.write(f"  Avg cycle: {det['avg_cycle_days']:.0f} days (std={det['cycle_std']:.0f})\n")
out.write(f"  Peers: {', '.join(det.get('peers_used', []))}\n\n")

out.write(f"  Ex-div windows:\n")
for w in det.get('all_windows', []):
    out.write(f"    {w['expected_month']}: {w['detected_date']} "
              f"gap={w['stock_gap_pct']:+.1f}% peer={w['peer_median_pct']:+.1f}% "
              f"div={w['divergence_pct']:+.1f}% [{w['confidence']}]\n")

if det['n_confirmed'] >= 3:
    pat = compute_excess_patterns(single, info['div_amount'], det['exdiv_dates'])
    if pat:
        out.write(f"\n  Pattern strength: {pat['pattern_strength']}%\n")
        out.write(f"  Ex-divs used: {pat['n_exdiv_used']}\n\n")
        out.write(f"  STRATEGIES (sorted by Sharpe):\n")
        strats = sorted(pat['strategies'], key=lambda x: x['sharpe'], reverse=True)
        for s in strats:
            sig = '***' if s['pval'] < 0.05 else '**' if s['pval'] < 0.10 else ''
            out.write(f"    {s['name']:16s} d{s['entry_day']:+3d}->d{s['exit_day']:+3d} "
                      f"ret={s['avg_ret']:+.2f}% win={s['win_rate']:.0%} "
                      f"sharpe={s['sharpe']:+.2f} p={s['pval']:.3f} n={s['n_trades']} {sig}\n")
        
        # Key daily patterns
        out.write(f"\n  DAILY PATTERN (d-10 to d+10):\n")
        for d in pat['daily_stats']:
            if abs(d['day']) <= 10:
                sig = '*' if d['pval'] < 0.10 else ''
                out.write(f"    Day{d['day']:+3d}: avg={d['avg']:+.4f}% cum={d['cum']:+.3f}% "
                          f"pos={d['pos']:.0%} n={d['n']} p={d['pval']:.3f} {sig}\n")

out.close()
print("Done -> pipeline_result.txt")
