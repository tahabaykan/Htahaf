
import pandas as pd
try:
    df = pd.read_csv(r'C:\StockTracker\janall\janalldata.csv', nrows=1)
    for col in df.columns:
        print(f"COL: {col}")
except Exception as e:
    print("Error:", e)
