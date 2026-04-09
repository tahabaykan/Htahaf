"""Test: run_30day_plan artık yeni exhaustive short sonuçlarını kullanıyor mu?"""
import sys
sys.path.insert(0, '.')
from run_30day_plan import load_data, build_plan

out = open('_plan_test.txt', 'w', encoding='utf-8')
def p(s=""): out.write(s + "\n")

summary, base_exdiv_map, held_tickers = load_data()
plan = build_plan(summary, base_exdiv_map, 50, 50, 50, 50, held_tickers)

p("═" * 90)
p("  YENİ 30 GÜNLÜK PLAN (Exhaustive Search Sonrası)")
p("═" * 90)
p(f"  Long: {len(plan['selected_longs'])} hisse")
p(f"  Short: {len(plan['selected_shorts'])} hisse")

p()
p("  TOP LONG adaylar:")
for t in plan['selected_longs'][:10]:
    h = "H" if t.get('is_held') else "NH"
    p(f"    {t['ticker']:14s} [{h}] {t['strategy']:20s} "
      f"d{t.get('entry_offset','?'):+d}→d{t.get('exit_offset','?'):+d}  "
      f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  "
      f"win={t.get('win_rate',0):.0%}  "
      f"entry={t['entry_date']}  exit={t['exit_date']}")

p()
p("  TOP SHORT adaylar:")
for t in plan['selected_shorts'][:10]:
    h = "H" if t.get('is_held') else "NH"
    p(f"    {t['ticker']:14s} [{h}] {t['strategy']:20s} "
      f"d{t.get('entry_offset','?'):+d}→d{t.get('exit_offset','?'):+d}  "
      f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  "
      f"win={t.get('win_rate',0):.0%}  "
      f"entry={t['entry_date']}  exit={t['exit_date']}")

# Aksiyon takvimi ilk 5 gün
p()
p("  AKSİYON TAKVİMİ (ilk 5 gün):")
cd = None
shown = 0
for a in plan['actions']:
    if a['date'] != cd:
        cd = a['date']
        shown += 1
        if shown > 5:
            break
        p(f"\n  📌 {cd}")
    emoji = '🟢' if a['action'] == 'BUY' else '🔴' if a['action'] == 'SHORT' else '📤' if a['action'] == 'SELL' else '📥'
    p(f"    {emoji} {a['action']:6s} {a['ticker']:14s} ret={a['expected_return']:+.2f}%")

out.close()
print("Done -> _plan_test.txt")
