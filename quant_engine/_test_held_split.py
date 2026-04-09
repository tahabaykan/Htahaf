#!/usr/bin/env python3
"""
Tam sistem doğrulama: Pattern Cycle Trading Plan
Her adımı trace ederek çıktıyı _verify_output.txt'e yazar.
"""
import sys, os
sys.path.insert(0, '.')

out = open('_verify_output.txt', 'w', encoding='utf-8')
def p(s=""): print(s); out.write(s + "\n")

from run_30day_plan import load_data, build_plan, TODAY, END_DATE
import pandas as pd

# ═══════════════════════════════════════════
# ADIM 1: Veri Yükleme
# ═══════════════════════════════════════════
summary, base_exdiv_map, held_tickers = load_data()
p("═" * 80)
p("ADIM 1: VERİ YÜKLEME")
p(f"  v5_summary: {len(summary)} hisse (backtest sonuçları)")
p(f"  base_exdiv_map: {len(base_exdiv_map)} ticker (baz ex-div tarihleri)")
p(f"  held_tickers: {len(held_tickers)} ticker (ekheld CSV'lerinden)")
p(f"  Bugün: {TODAY.strftime('%Y-%m-%d')}")
p(f"  Plan sonu: {END_DATE.strftime('%Y-%m-%d')}")

# ═══════════════════════════════════════════
# ADIM 2: v5_summary ne bilgi içeriyor?
# ═══════════════════════════════════════════
p()
p("═" * 80)
p("ADIM 2: v5_summary İÇERİĞİ (patternların backtest sonuçları)")
p(f"  Sütunlar: {list(summary.columns)}")

# Long sinyali olan hisseler
has_long = summary[summary['best_long_sharpe'].notna() & (summary['best_long_sharpe'] >= 0.3)]
has_long_sig = has_long[has_long['best_long_pval'].notna() & (has_long['best_long_pval'] <= 0.15)]
p(f"  Long sinyal adayı: {len(has_long_sig)} hisse (sharpe>=0.3, pval<=0.15)")

# Short sinyali olan hisseler
has_short = summary[summary['best_short_sharpe'].notna() & (summary['best_short_sharpe'] >= 0.3)]
p(f"  Short sinyal adayı: {len(has_short)} hisse (sharpe>=0.3)")

# Top 5 Long pattern
p()
p("  TOP 5 LONG PATTERN (en yüksek sharpe):")
top5_long = has_long_sig.sort_values('best_long_sharpe', ascending=False).head(5)
for _, r in top5_long.iterrows():
    tk = r['ticker']
    in_held = "HELD" if tk in held_tickers else "NOT-HELD"
    p(f"    {tk:14s} [{in_held:8s}] sharpe={r['best_long_sharpe']:+.2f} "
      f"ret={r['best_long_ret']:+.2f}% win={r['best_long_win']:.0%} "
      f"entry=d{int(r['best_long_entry']):+d} exit=d{int(r['best_long_exit']):+d} "
      f"pval={r['best_long_pval']:.3f} yield={r['yield_pct']:.1f}%")

# Top 5 Short pattern
p()
p("  TOP 5 SHORT PATTERN (en yüksek sharpe):")
top5_short = has_short.sort_values('best_short_sharpe', ascending=False).head(5)
for _, r in top5_short.iterrows():
    tk = r['ticker']
    in_held = "HELD" if tk in held_tickers else "NOT-HELD"
    p(f"    {tk:14s} [{in_held:8s}] sharpe={r['best_short_sharpe']:+.2f} "
      f"ret={r['best_short_ret']:+.2f}%")

# ═══════════════════════════════════════════
# ADIM 3: Plan oluştur (50/50, held=50%)
# ═══════════════════════════════════════════
p()
p("═" * 80)
p("ADIM 3: PLAN OLUŞTUR (50L/50S, Held=50%)")

plan = build_plan(summary, base_exdiv_map, 50, 50, 50, 50, held_tickers)

p(f"  Toplam Long aday: {plan['all_longs_n']}")
p(f"  Toplam Short aday: {plan['all_shorts_n']}")
p()

# Bugün aktif sinyaller
p("  ⚡ BUGÜN AKTİF SİNYALLER:")
if plan['active_buys']:
    for t in plan['active_buys'][:5]:
        h = "H" if t.get('is_held') else "NH"
        p(f"    🟢 BUY  {t['ticker']:14s} [{h}] ret={t['expected_return']:+.2f}% "
          f"shrp={t['sharpe']:.1f} win={t['win_rate']:.0%} exdiv={t['exdiv_date']} "
          f"entry={t['entry_date']} exit={t['exit_date']}")
else:
    p("    Bugün alım penceresi açık hisse yok")

if plan['active_shorts']:
    for t in plan['active_shorts'][:5]:
        h = "H" if t.get('is_held') else "NH"
        p(f"    🔴 SHORT {t['ticker']:14s} [{h}] ret={t['expected_return']:+.2f}% "
          f"shrp={t['sharpe']:.1f} exdiv={t['exdiv_date']} "
          f"entry={t['entry_date']} exit={t['exit_date']}")
else:
    p("    Bugün short penceresi açık hisse yok")

# Seçilen portföy
p()
p("  📋 SEÇİLEN PORTFÖY:")
p(f"    Long:  {len(plan['selected_longs'])} hisse  (HELD: {len(plan['held_longs'])} / NOT-HELD: {len(plan['notheld_longs'])})")
p(f"    Short: {len(plan['selected_shorts'])} hisse  (HELD: {len(plan['held_shorts'])} / NOT-HELD: {len(plan['notheld_shorts'])})")

p()
p("    Selected LONG hisseler:")
for t in plan['selected_longs']:
    h = "HELD" if t.get('is_held') else "NTHD"
    p(f"      {t['ticker']:14s} [{h}] score={t['score']:.3f} ret={t['expected_return']:+.2f}% "
      f"shrp={t['sharpe']:.1f} entry={t['entry_date']} exit={t['exit_date']} "
      f"exdiv={t['exdiv_date']} d_until={t['days_until_exdiv']}d")

p()
p("    Selected SHORT hisseler:")
for t in plan['selected_shorts']:
    h = "HELD" if t.get('is_held') else "NTHD"
    p(f"      {t['ticker']:14s} [{h}] score={t['score']:.3f} ret={t['expected_return']:+.2f}% "
      f"shrp={t['sharpe']:.1f} entry={t['entry_date']} exit={t['exit_date']} "
      f"exdiv={t['exdiv_date']} d_until={t['days_until_exdiv']}d")

# ═══════════════════════════════════════════
# ADIM 4: Aksiyon Takvimi (ilk 10 gün)
# ═══════════════════════════════════════════
p()
p("═" * 80)
p("ADIM 4: AKSİYON TAKVİMİ (ilk 10 gün)")
current_date = None
shown_dates = 0
for a in plan['actions']:
    if a['date'] != current_date:
        current_date = a['date']
        shown_dates += 1
        if shown_dates > 10:
            p("    ...")
            break
        p(f"\n  📌 {current_date}")
    emoji = '🟢' if a['action'] == 'BUY' else '🔴' if a['action'] == 'SHORT' else '📤' if a['action'] == 'SELL' else '📥'
    p(f"    {emoji} {a['action']:6s} {a['ticker']:14s} ret={a['expected_return']:+.2f}% shrp={a['sharpe']:.1f}")

# ═══════════════════════════════════════════
# ADIM 5: Farklı held oranları karşılaştırma
# ═══════════════════════════════════════════
p()
p("═" * 80)
p("ADIM 5: HELD ORAN KARŞILAŞTIRMA")
for hpct in [20, 50, 80, 100]:
    plan_x = build_plan(summary, base_exdiv_map, 50, 50, hpct, hpct, held_tickers)
    p(f"  Held={hpct}%: Long={len(plan_x['selected_longs'])} "
      f"(H:{len(plan_x['held_longs'])}/NH:{len(plan_x['notheld_longs'])}) "
      f"| Short={len(plan_x['selected_shorts'])} "
      f"(H:{len(plan_x['held_shorts'])}/NH:{len(plan_x['notheld_shorts'])})")

# ═══════════════════════════════════════════
# ADIM 6: Long/Short oran karşılaştırma
# ═══════════════════════════════════════════
p()
p("═" * 80)
p("ADIM 6: LONG/SHORT ORAN KARŞILAŞTIRMA (held=50%)")
for lpct in [30, 50, 70, 100]:
    spct = 100 - lpct
    plan_x = build_plan(summary, base_exdiv_map, lpct, spct, 50, 50, held_tickers)
    p(f"  {lpct}L/{spct}S: Long slots={int(lpct/100/0.03)} sel={len(plan_x['selected_longs'])} "
      f"| Short slots={int(spct/100/0.03)} sel={len(plan_x['selected_shorts'])}")

out.close()
print("Done -> _verify_output.txt")
