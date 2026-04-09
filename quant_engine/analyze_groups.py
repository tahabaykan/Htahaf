
import pandas as pd
import os
from pathlib import Path

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
            print(f"Found CSV at: {path}")
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
        
        # Check available columns
        print(f"Columns: {list(df.columns)}")
        
        # Determine grouping column
        group_col = None
        if 'GROUP' in df.columns:
            group_col = 'GROUP'
        elif 'CGRUP' in df.columns:
            group_col = 'CGRUP'
        
        if not group_col:
            print("No GROUP or CGRUP column found")
            return

        print(f"Analyzing using group column: {group_col}")
        
        # Filter valid rows
        if 'PREF IBKR' in df.columns:
            df = df[df['PREF IBKR'].notna()]
            df = df[df['PREF IBKR'] != 'nan']
        
        # Count by group
        counts = df[group_col].value_counts()
        
        print("\n--- Group Counts ---")
        print(counts)
        
        print("\n--- Total Stocks ---")
        print(len(df))
        
        # Specific check for heldkuponlu
        held_count = counts.get('heldkuponlu', 0)
        print(f"\nheldkuponlu count: {held_count}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze()
