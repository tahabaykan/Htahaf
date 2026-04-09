import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r'c:\StockTracker\quant_engine')

from app.api.pattern_suggestions_routes import _build_suggestions
import pandas as pd

today = pd.Timestamp(2026, 2, 16)
data, err = _build_suggestions(today)
if err:
    print('ERROR:', err)
    exit(1)

print('=== ACTIVE LONGS (entry penceresi bugun acik) ===')
for t in data['active_longs'][:5]:
    tk = t['ticker']
    st = t['strategy']
    cl = t['cycle_label']
    ed = t['exdiv_date']
    ret = t['expected_return']
    wr = t['win_rate']
    sh = t['sharpe']
    print(f'  {tk:14s} {st:16s} {cl:30s} ExDiv={ed}  ret={ret:+.2f}%  win={wr:.0%}  shrp={sh:+.1f}')

print()
print('=== ACTIVE SHORTS (entry penceresi bugun acik) ===')
for t in data['active_shorts'][:5]:
    tk = t['ticker']
    st = t['strategy']
    cl = t['cycle_label']
    ed = t['exdiv_date']
    ret = t['expected_return']
    wr = t['win_rate']
    sh = t['sharpe']
    print(f'  {tk:14s} {st:16s} {cl:30s} ExDiv={ed}  ret={ret:+.2f}%  win={wr:.0%}  shrp={sh:+.1f}')

print()
print('=== HOLDING LONGS ===')
for t in data['holding_longs'][:5]:
    tk = t['ticker']
    st = t['strategy']
    cl = t['cycle_label']
    ed = t['exdiv_date']
    di = t['days_in']
    de = t['days_to_exit']
    print(f'  {tk:14s} {st:16s} {cl:30s} ExDiv={ed}  {di}d icinde, exit {de}d sonra')

print()
print('=== UPCOMING LONGS (7 gun icinde) ===')
for t in data['upcoming_longs'][:5]:
    tk = t['ticker']
    st = t['strategy']
    cl = t['cycle_label']
    ed = t['exdiv_date']
    dte = t['days_to_entry']
    ret = t['expected_return']
    print(f'  {tk:14s} {st:16s} {cl:30s} ExDiv={ed}  entry {dte}d sonra  ret={ret:+.2f}%')

print()
print('=== UPCOMING SHORTS (7 gun icinde) ===')
for t in data['upcoming_shorts'][:5]:
    tk = t['ticker']
    st = t['strategy']
    cl = t['cycle_label']
    ed = t['exdiv_date']
    dte = t['days_to_entry']
    ret = t['expected_return']
    print(f'  {tk:14s} {st:16s} {cl:30s} ExDiv={ed}  entry {dte}d sonra  ret={ret:+.2f}%')

print()
al = len(data['active_longs'])
ash = len(data['active_shorts'])
hl = len(data['holding_longs'])
hs = len(data['holding_shorts'])
ul = len(data['upcoming_longs'])
us = len(data['upcoming_shorts'])
print(f'Toplam: {al} active long, {ash} active short')
print(f'        {hl} holding long, {hs} holding short')
print(f'        {ul} upcoming long, {us} upcoming short')
