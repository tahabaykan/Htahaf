"""Top 5 Buy / Top 5 Short - Anlik Sonuclar"""
import sys, os
sys.path.insert(0, '.')
os.chdir(r'c:\StockTracker\quant_engine')
# Fix encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
TODAY_STR = TODAY.strftime('%Y-%m-%d')
END_DT = TODAY + timedelta(days=30)

print(f"{'='*80}")
print(f"  BUGUNUN TARIHI: {TODAY_STR} ({TODAY.strftime('%A')})")
print(f"{'='*80}")

summary = pd.read_csv('output/exdiv_v5/v5_summary.csv')
edf = pd.read_csv('output/exdiv_v5/v5_exdiv_dates.csv')

exdiv_dates = {}
for _, row in edf.iterrows():
    tk = row['ticker']
    if tk not in exdiv_dates:
        exdiv_dates[tk] = []
    if row.get('confidence', '') in ('HIGH', 'MEDIUM', 'LOW'):
        exdiv_dates[tk].append(row['detected_date'])

def find_next_exdiv(dates_list):
    if not dates_list:
        return None, None
    sd = sorted(pd.to_datetime(dates_list))
    nxt = sd[-1] + pd.DateOffset(months=3)
    while nxt < TODAY:
        nxt = nxt + pd.DateOffset(months=3)
    return nxt, (nxt - TODAY).days

def biz_day(base_dt, offset):
    dt = base_dt + timedelta(days=int(offset * 7 / 5))
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt

stock_cycles = []
for _, row in summary.iterrows():
    tk = row['ticker']
    dates = exdiv_dates.get(tk, [])
    if not dates or row.get('n_exdivs', 0) < 3:
        continue
    nxt, du = find_next_exdiv(dates)
    if nxt is None:
        continue
    stock_cycles.append({'ticker': tk, 'row': row, 'next_exdiv': nxt, 'days_until': du, 'cycle_day': -du})

# === LONG ===
active_buys = []
upcoming_buys = []

for sc in stock_cycles:
    row = sc['row']
    tk = sc['ticker']
    nxt = sc['next_exdiv']
    du = sc['days_until']
    if pd.isna(row.get('best_long_sharpe')) or row['best_long_sharpe'] < 0.3:
        continue
    if pd.isna(row.get('best_long_pval')) or row['best_long_pval'] > 0.15:
        continue
    entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
    exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0
    entry_dt = biz_day(nxt, entry_off)
    exit_dt = biz_day(nxt, exit_off)
    if exit_dt <= entry_dt:
        exit_dt = entry_dt + timedelta(days=2)
        while exit_dt.weekday() >= 5: exit_dt += timedelta(days=1)
    score = (float(row.get('best_long_sharpe', 0)) * 0.4 +
             float(row.get('best_long_win', 0)) * 10 * 0.3 +
             float(row.get('best_long_ret', 0)) * 0.3)
    item = {
        'ticker': tk, 'strategy': str(row.get('best_long_name', '')),
        'entry_date': entry_dt.strftime('%Y-%m-%d'), 'exit_date': exit_dt.strftime('%Y-%m-%d'),
        'exdiv_date': nxt.strftime('%Y-%m-%d'), 'days_until_exdiv': du,
        'expected_return': round(float(row.get('best_long_ret', 0)), 3),
        'win_rate': round(float(row.get('best_long_win', 0)), 3),
        'sharpe': round(float(row.get('best_long_sharpe', 0)), 2),
        'p_value': round(float(row.get('best_long_pval', 1)), 4),
        'yield_pct': round(float(row.get('yield_pct', 0)), 1),
        'score': round(score, 3),
    }
    win_start = entry_dt - timedelta(days=1)
    win_end = entry_dt + timedelta(days=1)
    if win_start <= TODAY <= win_end:
        item['signal'] = 'BUY_NOW'
        active_buys.append(item)
    elif entry_dt > TODAY and entry_dt <= END_DT:
        item['days_to_entry'] = (entry_dt - TODAY).days
        upcoming_buys.append(item)

active_buys.sort(key=lambda x: x['score'], reverse=True)
upcoming_buys.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

# === SHORT ===
active_shorts = []
upcoming_shorts = []

for sc in stock_cycles:
    row = sc['row']
    tk = sc['ticker']
    nxt = sc['next_exdiv']
    du = sc['days_until']
    if pd.isna(row.get('best_short_sharpe')) or row['best_short_sharpe'] < 0.3:
        continue
    entry_dt = nxt
    while entry_dt.weekday() >= 5: entry_dt += timedelta(days=1)
    exit_dt = entry_dt + timedelta(days=7)
    while exit_dt.weekday() >= 5: exit_dt += timedelta(days=1)
    score = (float(row.get('best_short_sharpe', 0)) * 0.5 +
             float(row.get('best_short_ret', 0)) * 0.5)
    item = {
        'ticker': tk, 'strategy': str(row.get('best_short_name', 'WASHOUT')),
        'entry_date': entry_dt.strftime('%Y-%m-%d'), 'exit_date': exit_dt.strftime('%Y-%m-%d'),
        'exdiv_date': nxt.strftime('%Y-%m-%d'), 'days_until_exdiv': du,
        'expected_return': round(float(row.get('best_short_ret', 0)), 3),
        'sharpe': round(float(row.get('best_short_sharpe', 0)), 2),
        'yield_pct': round(float(row.get('yield_pct', 0)), 1),
        'score': round(score, 3),
    }
    win_start = entry_dt - timedelta(days=1)
    win_end = entry_dt + timedelta(days=1)
    if win_start <= TODAY <= win_end:
        item['signal'] = 'SHORT_NOW'
        active_shorts.append(item)
    elif entry_dt > TODAY and entry_dt <= END_DT:
        item['days_to_entry'] = (entry_dt - TODAY).days
        upcoming_shorts.append(item)

active_shorts.sort(key=lambda x: x['score'], reverse=True)
upcoming_shorts.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

# === OUTPUT ===
print()
print(f"  [BUY] TOP 5 BEST BUY - Bugun Pencere Acik ({len(active_buys)} toplam)")
print(f"  {'#':>3s} {'Ticker':14s} {'Strateji':18s} {'Entry':>10s} {'ExDiv':>10s} {'Ret%':>8s} {'Win%':>6s} {'Sharpe':>7s} {'P-val':>8s} {'Yld%':>5s} {'Score':>6s}")
print(f"  {'-'*100}")
for i, t in enumerate(active_buys[:5], 1):
    print(f"  {i:>3d} {t['ticker']:14s} {t['strategy']:18s} {t['entry_date']:>10s} {t['exdiv_date']:>10s} "
          f"{t['expected_return']:+7.2f}% {t['win_rate']:5.0%} {t['sharpe']:+6.1f} {t['p_value']:7.4f} {t['yield_pct']:4.1f}% {t['score']:5.2f}")
if not active_buys:
    print("  (Bugun long entry penceresi acik hisse yok)")
    print()
    print(f"  >> En yakin LONG firsatlari:")
    for t in upcoming_buys[:5]:
        print(f"     [BUY] {t['ticker']:14s} entry={t['entry_date']}  exdiv={t['exdiv_date']}  "
              f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  win={t['win_rate']:.0%}  ({t['days_to_entry']}d sonra)")

print()
print(f"  [SHORT] TOP 5 BEST SHORT - Bugun Pencere Acik ({len(active_shorts)} toplam)")
print(f"  {'#':>3s} {'Ticker':14s} {'Strateji':18s} {'Entry':>10s} {'ExDiv':>10s} {'Ret%':>8s} {'Sharpe':>7s} {'Yld%':>5s} {'Score':>6s}")
print(f"  {'-'*90}")
for i, t in enumerate(active_shorts[:5], 1):
    print(f"  {i:>3d} {t['ticker']:14s} {t['strategy']:18s} {t['entry_date']:>10s} {t['exdiv_date']:>10s} "
          f"{t['expected_return']:+7.2f}% {t['sharpe']:+6.1f} {t['yield_pct']:4.1f}% {t['score']:5.2f}")
if not active_shorts:
    print("  (Bugun short penceresi acik hisse yok)")
    print()
    print(f"  >> En yakin SHORT firsatlari:")
    for t in upcoming_shorts[:5]:
        print(f"     [SHORT] {t['ticker']:14s} entry={t['entry_date']}  exdiv={t['exdiv_date']}  "
              f"ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  ({t['days_to_entry']}d sonra)")

# YARIN
tomorrow = TODAY + timedelta(days=1)
tom_str = tomorrow.strftime('%Y-%m-%d')
tom_buys = [b for b in upcoming_buys if b['entry_date'] == tom_str]
tom_shorts = [s for s in upcoming_shorts if s['entry_date'] == tom_str]

# Also check active for tomorrow (entry window includes tomorrow)
for sc in stock_cycles:
    row = sc['row']
    tk = sc['ticker']
    nxt = sc['next_exdiv']
    du = sc['days_until']
    # Long check for tomorrow
    if not pd.isna(row.get('best_long_sharpe')) and row['best_long_sharpe'] >= 0.3:
        if not pd.isna(row.get('best_long_pval')) and row['best_long_pval'] <= 0.15:
            entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
            entry_dt = biz_day(nxt, entry_off)
            ws = entry_dt - timedelta(days=1)
            we = entry_dt + timedelta(days=1)
            if ws <= tomorrow <= we and not any(b['ticker'] == tk for b in tom_buys):
                score = (float(row.get('best_long_sharpe', 0)) * 0.4 +
                         float(row.get('best_long_win', 0)) * 10 * 0.3 +
                         float(row.get('best_long_ret', 0)) * 0.3)
                tom_buys.append({
                    'ticker': tk, 'entry_date': entry_dt.strftime('%Y-%m-%d'),
                    'exdiv_date': nxt.strftime('%Y-%m-%d'),
                    'expected_return': round(float(row.get('best_long_ret', 0)), 3),
                    'sharpe': round(float(row.get('best_long_sharpe', 0)), 2),
                    'win_rate': round(float(row.get('best_long_win', 0)), 3),
                    'score': round(score, 3),
                })
    # Short check for tomorrow
    if not pd.isna(row.get('best_short_sharpe')) and row['best_short_sharpe'] >= 0.3:
        entry_dt = nxt
        while entry_dt.weekday() >= 5: entry_dt += timedelta(days=1)
        ws = entry_dt - timedelta(days=1)
        we = entry_dt + timedelta(days=1)
        if ws <= tomorrow <= we and not any(s['ticker'] == tk for s in tom_shorts):
            score = (float(row.get('best_short_sharpe', 0)) * 0.5 +
                     float(row.get('best_short_ret', 0)) * 0.5)
            tom_shorts.append({
                'ticker': tk, 'entry_date': entry_dt.strftime('%Y-%m-%d'),
                'exdiv_date': nxt.strftime('%Y-%m-%d'),
                'expected_return': round(float(row.get('best_short_ret', 0)), 3),
                'sharpe': round(float(row.get('best_short_sharpe', 0)), 2),
                'score': round(score, 3),
            })

tom_buys.sort(key=lambda x: x.get('score', 0), reverse=True)
tom_shorts.sort(key=lambda x: x.get('score', 0), reverse=True)

print()
print(f"  {'='*60}")
print(f"  YARIN ({tom_str}) PENCERE ACILACAK:")
print(f"  {'='*60}")
if tom_buys:
    print(f"  [LONG] ({len(tom_buys)} hisse):")
    for t in tom_buys[:5]:
        print(f"     {t['ticker']:14s} ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  exdiv={t['exdiv_date']}")
else:
    print("  Yarin yeni long penceresi yok")
if tom_shorts:
    print(f"  [SHORT] ({len(tom_shorts)} hisse):")
    for t in tom_shorts[:5]:
        print(f"     {t['ticker']:14s} ret={t['expected_return']:+.2f}%  shrp={t['sharpe']:.1f}  exdiv={t['exdiv_date']}")
else:
    print("  Yarin yeni short penceresi yok")

print()
print("  Bu veriler Quant Engine'de [Ex-Div Plan] butonuna tiklaninca gorunecek.")
print(f"{'='*80}")
