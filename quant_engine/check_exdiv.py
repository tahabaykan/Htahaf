"""janalldata.csv ve ekheld kaynaklarini incele"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(r'c:\StockTracker')

import pandas as pd
from datetime import datetime

TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

# 1) janalldata.csv
jdf = pd.read_csv('janalldata.csv')
print(f"janalldata.csv: {len(jdf)} rows")
print(f"Ticker col: '{jdf.columns[0]}'")
print(f"ExDiv col: 'EX-DIV DATE'")
print()

# Sample dates
print("Sample EX-DIV DATEs:")
for _, r in jdf.head(15).iterrows():
    print(f"  {str(r['PREF IBKR']):14s}  EX-DIV={r['EX-DIV DATE']}")
print()

# Check date format
sample_dates = jdf['EX-DIV DATE'].dropna().head(20).tolist()
print(f"Date format samples: {sample_dates[:5]}")
print()

# 2) ekheld CSVs
print("ekheld dosyalari:")
for root, dirs, files in os.walk('.'):
    for f in files:
        if 'ekheld' in f.lower() and f.endswith('.csv'):
            fp = os.path.join(root, f)
            try:
                edf = pd.read_csv(fp, nrows=2)
                print(f"  {fp}: {list(edf.columns[:6])}")
            except:
                print(f"  {fp}: OKUNAMADI")

# 3) CMSA ve ONBPO kontrolu
print()
for tk in ['CMSA', 'ONBPO', 'COF PRI', 'COF PRN', 'STT PRG']:
    row = jdf[jdf['PREF IBKR'] == tk]
    if not row.empty:
        exd = row.iloc[0]['EX-DIV DATE']
        print(f"{tk:14s}  janalldata EX-DIV = {exd}")
        # Parse and project
        try:
            dt = pd.to_datetime(exd, format='%m/%d/%Y')
            base_day = dt.day
            base_month = dt.month
            print(f"  Base: {dt.strftime('%Y-%m-%d')} (gun={base_day})")
            # +3, +6, +9... ay ekle
            projections = []
            for n in range(1, 20):
                m = base_month + 3 * n
                y = dt.year + (m - 1) // 12
                m = ((m - 1) % 12) + 1
                import calendar
                max_d = calendar.monthrange(y, m)[1]
                d = min(base_day, max_d)
                proj = pd.Timestamp(y, m, d)
                if proj >= TODAY - pd.Timedelta(days=30) and proj <= TODAY + pd.Timedelta(days=120):
                    projections.append(proj)
            for p in projections:
                du = (p - TODAY).days
                status = "GECMIS" if du < 0 else ("BUGUN" if du == 0 else f"{du}d sonra")
                print(f"  >> {p.strftime('%Y-%m-%d')} ({status}) [pencere: {p.day-4}-{p.day+4}]")
        except Exception as e:
            print(f"  Parse error: {e}")
    else:
        print(f"{tk:14s}  janalldata'da YOK!")
