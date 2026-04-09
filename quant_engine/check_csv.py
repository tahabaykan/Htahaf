import pandas as pd
import os

files = [
    r"c:\StockTracker\janall\janalldata.csv"
]

symbols = ['HOVNP', 'TPGAL', 'NSA PRA']

for f in files:
    if os.path.exists(f):
        print(f"Checking {f}")
        df = pd.read_csv(f)
        # Normalize column names to check
        cols = df.columns.tolist()
        print(f"Columns: {cols}")
        
        for sym in symbols:
            row = df[df['PREF IBKR'] == sym]
            if not row.empty:
                print(f"\nSymbol: {sym}")
                for col in ['SMA63 chg', 'SMA246 chg', 'SMA63_CHG', 'SMA246_CHG']:
                    if col in df.columns:
                        val = row[col].values[0]
                        print(f"  {col}: {val} (Type: {type(val)})")
            else:
                print(f"\nSymbol: {sym} NOT FOUND")
    else:
        print(f"File {f} NOT FOUND")
