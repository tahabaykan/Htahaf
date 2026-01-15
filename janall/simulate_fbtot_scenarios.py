import pandas as pd
import os

files = {
    'HELDSOLIDBIG': 'janek_ssfinekheldsolidbig.csv',
    'HELDKUPONLU': 'janek_ssfinekheldkuponlu.csv',
    'HELDFLR': 'janek_ssfinekheldflr.csv',
    'HELDFF': 'janek_ssfinekheldff.csv'
}

base_dir = r"c:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall"
output_file = os.path.join(base_dir, "scenarios_result.md")

# Run scenarios and save to INDIVIDUAL CSV files
for group_name, file_name in files.items():
    path = os.path.join(base_dir, file_name)
    if not os.path.exists(path):
        print(f"Skipping {group_name}: File not found")
        continue

    try:
        df = pd.read_csv(path)
        if 'FINAL_THG' not in df.columns or 'PREF IBKR' not in df.columns:
            print(f"Skipping {group_name}: Columns missing")
            continue

        df['Score'] = pd.to_numeric(df['FINAL_THG'], errors='coerce')
        df = df.dropna(subset=['Score'])
        df = df[df['Score'] > 0]
        
        if df.empty:
            print(f"Skipping {group_name}: No valid data")
            continue

        df = df.sort_values('Score', ascending=True).reset_index(drop=True)
        
        total_count = len(df)
        avg_score = df['Score'].mean()
        
        results = []
        for index, row in df.iterrows():
            symbol = row['PREF IBKR']
            score = row['Score']
            rank = index + 1
            plagr_raw = rank / total_count
            ratgr_raw = score / avg_score
            
            fbtot_orig = (plagr_raw * 0.5) + (ratgr_raw * 1.5)
            fbtot_rev = (plagr_raw * 1.5) + (ratgr_raw * 0.5)
            fbtot_bal = (plagr_raw * 1.0) + (ratgr_raw * 1.0)
            
            results.append({
                'Symbol': symbol,
                'Score': score,
                'Rank': rank,
                'Total': total_count,
                'Plagr': round(plagr_raw, 4),
                'Ratgr': round(ratgr_raw, 4),
                'ORIG_0.5_1.5': round(fbtot_orig, 4),
                'REV_1.5_0.5': round(fbtot_rev, 4),
                'BAL_1.0_1.0': round(fbtot_bal, 4)
            })
            
        res_df = pd.DataFrame(results)
        res_df = res_df.sort_values('ORIG_0.5_1.5', ascending=False)
        
        # Save to CSV
        csv_filename = f"fbtot_scenario_{group_name}.csv"
        csv_path = os.path.join(base_dir, csv_filename)
        res_df.to_csv(csv_path, index=False)
        print(f"Created {csv_path} ({len(res_df)} rows)")

    except Exception as e:
        print(f"Error {group_name}: {e}")

