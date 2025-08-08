import pandas as pd
import glob
import os

# --- CONFIG ---
MASTER_CSV = 'crdt_master.csv'
TARGET_PATTERN = 'ekheld*.csv'
REPORT_FILE = 'fill_crdt_report.txt'

# --- LOAD MASTER DATA ---
master_df = pd.read_csv(MASTER_CSV)
master_dict = dict(zip(master_df['TICKER'], master_df['CRDT_RTNG']))

def convert_pref_ibkr_to_master_ticker(pref_ibkr):
    # Example: "WRB PRF" -> "WRB-F"
    if pd.isna(pref_ibkr):
        return None
    parts = str(pref_ibkr).split()
    if len(parts) == 2 and parts[1].startswith("PR"):
        return parts[0] + "-" + parts[1][2:]
    return pref_ibkr

def fill_missing_crdt(filename, master_dict, report):
    df = pd.read_csv(filename)
    updated = 0
    unmatched = []
    for idx, row in df.iterrows():
        if pd.isna(row.get('CRDT_RTNG')) or str(row.get('CRDT_RTNG')).strip() == '':
            ticker = row.get('PREF IBKR')
            master_ticker = convert_pref_ibkr_to_master_ticker(ticker)
            crdt = master_dict.get(master_ticker)
            if crdt:
                df.at[idx, 'CRDT_RTNG'] = crdt
                updated += 1
            else:
                unmatched.append((ticker, master_ticker))
    df.to_csv(filename, index=False)
    report.append(f"{filename}: {updated} rows updated, {len(unmatched)} unmatched.")
    if unmatched:
        report.append(f"  Unmatched tickers: {unmatched}")

def main():
    report = []
    files = glob.glob(TARGET_PATTERN)
    if not files:
        report.append("No target files found.")
    for file in files:
        fill_missing_crdt(file, master_dict, report)
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        for line in report:
            f.write(str(line) + '\n')
    print("Done. See fill_crdt_report.txt for details.")

if __name__ == '__main__':
    main()
