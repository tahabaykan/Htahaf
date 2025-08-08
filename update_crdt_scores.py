import pandas as pd

# Rating to score mapping
rating_to_score = {
    'AAA': 100,
    'AA+': 95,
    'AA': 90,
    'AAp': 85,
    'A+': 80,
    'A': 75,
    'Ap': 70,
    'BBB+': 65,
    'BBB': 60,
    'BBBp': 55,
    'BB+': 50,
    'BB': 45,
    'BBp': 40,
    'B+': 35,
    'B': 30,
    'Bp': 25,
    'CCC+': 20,
    'CCC': 15,
    'CCCp': 10,
    'CC': 8,
    'C': 6,
    'D': 5
}

def get_score(rtng):
    if pd.isna(rtng) or str(rtng).strip() == '' or str(rtng).strip().upper() == 'NR':
        return 40
    key = str(rtng).strip().upper()
    return rating_to_score.get(key, 40)

import os
import glob

# Find all ek*.csv files in the current directory except ekcurdata.csv
csv_files = [f for f in glob.glob(os.path.join(os.getcwd(), 'ek*.csv')) if not f.endswith('ekcurdata.csv')]

for filename in csv_files:
    try:
        df = pd.read_csv(filename)
        if 'CRDT_RTNG' in df.columns:
            df['CRDT_SCORE'] = df['CRDT_RTNG'].apply(get_score)
            df.to_csv(filename, index=False)
        else:
            print(f"[Skipped] {filename}: 'CRDT_RTNG' column not found.")
    except Exception as e:
        print(f"[Error] {filename}: {e}")