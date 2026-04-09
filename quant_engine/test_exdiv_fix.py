"""Test: janalldata.csv bazli yeni ex-div projeksiyon mantigi"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(r'c:\StockTracker\quant_engine')
sys.path.insert(0, '.')

import calendar
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
STOCKTRACKER = r'c:\StockTracker'
DRIFT_TOLERANCE = 4

# janalldata.csv yukle
base_exdiv_map = {}
jdf = pd.read_csv(os.path.join(STOCKTRACKER, 'janalldata.csv'))
for _, row in jdf.iterrows():
    tk = str(row.get('PREF IBKR', '')).strip()
    exd = row.get('EX-DIV DATE', '')
    if tk and pd.notna(exd) and str(exd).strip():
        try:
            dt = pd.to_datetime(str(exd).strip(), format='%m/%d/%Y')
            base_exdiv_map[tk] = dt
        except:
            try:
                dt = pd.to_datetime(str(exd).strip())
                base_exdiv_map[tk] = dt
            except:
                pass

print(f"janalldata: {len(base_exdiv_map)} ticker yuklu")
print(f"Bugun: {TODAY.strftime('%Y-%m-%d')}")
print()

def find_next_exdiv(ticker):
    if ticker not in base_exdiv_map:
        return None, None, None
    base_dt = base_exdiv_map[ticker]
    base_day = base_dt.day
    base_month = base_dt.month
    base_year = base_dt.year
    for n in range(1, 30):
        target_month = base_month + 3 * n
        target_year = base_year + (target_month - 1) // 12
        target_month = ((target_month - 1) % 12) + 1
        max_d = calendar.monthrange(target_year, target_month)[1]
        actual_day = min(base_day, max_d)
        projected = pd.Timestamp(target_year, target_month, actual_day)
        window_end = projected + timedelta(days=DRIFT_TOLERANCE)
        if window_end >= TODAY:
            days_until = (projected - TODAY).days
            return projected, days_until, base_day
    return None, None, None

# Test hisseleri
test_tickers = ['CMSA', 'ONBPO', 'COF PRI', 'COF PRN', 'STT PRG', 
                'MGRE', 'AHL PRF', 'F PRD', 'ATH PRD', 'TDS PRU',
                'TRTN PRF', 'SLG PRI']

print("=" * 80)
print(f"  {'Ticker':14s}  {'janalldata BAZ':14s}  {'Baz Gun':8s}  {'Sonraki Proj':14s}  {'Gun':6s}  {'Pencere':12s}")
print("=" * 80)
for tk in test_tickers:
    if tk in base_exdiv_map:
        base = base_exdiv_map[tk]
        proj, du, bd = find_next_exdiv(tk)
        if proj:
            lo = bd - DRIFT_TOLERANCE
            hi = bd + DRIFT_TOLERANCE
            print(f"  {tk:14s}  {base.strftime('%Y-%m-%d'):14s}  {bd:8d}  "
                  f"{proj.strftime('%Y-%m-%d'):14s}  {du:+5d}d  "
                  f"[{lo}-{hi}]")
        else:
            print(f"  {tk:14s}  {base.strftime('%Y-%m-%d'):14s}  {bd:8d}  PROJEKSIYON YOK")
    else:
        print(f"  {tk:14s}  JANALLDATA'DA YOK!")

# Pipeline summary ile eslestirme testi
print()
print("=" * 80)
sp = os.path.join('output', 'exdiv_v5', 'v5_summary.csv')
if os.path.exists(sp):
    sdf = pd.read_csv(sp)
    matched = 0
    unmatched = 0
    for _, row in sdf.iterrows():
        tk = row['ticker']
        if tk in base_exdiv_map:
            matched += 1
        else:
            unmatched += 1
    print(f"Pipeline summary: {len(sdf)} ticker")
    print(f"  - janalldata'da var: {matched}")
    print(f"  - janalldata'da YOK: {unmatched}")
    
    # Olmayanlari goster
    if unmatched > 0:
        missing = [row['ticker'] for _, row in sdf.iterrows() if row['ticker'] not in base_exdiv_map]
        print(f"  - Eksikler: {missing[:20]}")
else:
    print("Pipeline v5_summary.csv yok")
