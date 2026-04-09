
import pandas as pd
import os
from pathlib import Path
from app.market_data.grouping import resolve_primary_group

def find_csv_file():
    possible_paths = [
        Path(r"C:\StockTracker") / 'janalldata.csv',
        Path(os.getcwd()) / 'janalldata.csv',
        Path(r"C:\StockTracker\janall") / 'janalldata.csv',
        Path(os.getcwd()) / 'janall' / 'janalldata.csv',
        Path(os.getcwd()).parent / 'janall' / 'janalldata.csv',
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    return None

def analyze():
    csv_path = find_csv_file()
    if not csv_path:
        print("CSV file not found")
        return

    try:
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='latin-1')
        
        print(f"Loaded {len(df)} rows from {csv_path}")
        
        # Ensure PREF IBKR exists
        if 'PREF IBKR' not in df.columns:
            print("PREF IBKR column missing")
            return
            
        df = df[df['PREF IBKR'].notna()]
        df = df[df['PREF IBKR'] != 'nan']
        
        # Resolve GROUP if missing (simulate StaticDataStore logic)
        if 'GROUP' not in df.columns:
            df['GROUP'] = None
        
        # Fill missing GROUP using resolve_primary_group (mock logic if needed, or use actual function)
        # We imported resolve_primary_group, so let's use it if needed, or just rely on what's there.
        # But wait, resolve_primary_group requires a dict.
        
        # Let's just check the GROUP column content first
        if 'GROUP' in df.columns:
            counts = df['GROUP'].value_counts()
            print("\n--- GROUP Counts ---")
            print(counts)
            
            held_count = counts.get('heldkuponlu', 0)
            print(f"\nheldkuponlu count: {held_count}")
        else:
            print("\nGROUP column not found in CSV itself.")

        if 'CGRUP' in df.columns:
            print("\n--- CGRUP Counts (Top 10) ---")
            print(df['CGRUP'].value_counts().head(10))

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze()
