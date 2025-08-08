import pandas as pd
import numpy as np

def our_solidity_formula(df):
    n = len(df)
    # Her sütun için eksikse dizi olarak doldur
    if 'CRDT_SCORE' in df.columns:
        crdt_score = pd.to_numeric(df['CRDT_SCORE'], errors='coerce').fillna(8)
    else:
        crdt_score = np.full(n, 8)
    if 'COM_MKTCAP' in df.columns:
        mktcap = pd.to_numeric(df['COM_MKTCAP'], errors='coerce').fillna(1000)
    else:
        mktcap = np.full(n, 1000)
    if 'Last Price' in df.columns:
        last_price = pd.to_numeric(df['Last Price'], errors='coerce').fillna(20)
    else:
        last_price = np.full(n, 20)
    if 'COM_52W_LOW' in df.columns:
        low = pd.to_numeric(df['COM_52W_LOW'], errors='coerce').fillna(15)
    else:
        low = np.full(n, 15)
    if 'COM_52W_HIGH' in df.columns:
        high = pd.to_numeric(df['COM_52W_HIGH'], errors='coerce').fillna(25)
    else:
        high = np.full(n, 25)
    # Market Cap Score (0-20)
    market_cap_score = np.clip(np.log10(mktcap/1000) * 6, 0, 20)
    # Credit Score (0-20)
    credit_score = np.clip(crdt_score * 1.33, 0, 20)
    # Price Score (0-20)
    price_score = np.clip((last_price - low) / (high - low) * 20, 0, 20)
    # Final solidity
    df['OUR_SOLIDITY'] = 20 + market_cap_score + credit_score + price_score
    return df

def compare_solidity(file_csv, file_cy):
    df = pd.read_csv(file_csv)
    df_cy = pd.read_csv(file_cy)
    merged = pd.merge(df, df_cy[['PREF IBKR', 'CURRENT_YIELD', 'IMPLIED_SOLIDITY']], on='PREF IBKR', how='left')
    merged = our_solidity_formula(merged)
    out = merged[['PREF IBKR', 'CMON', 'CURRENT_YIELD', 'IMPLIED_SOLIDITY', 'OUR_SOLIDITY']].copy()
    out = out.sort_values('IMPLIED_SOLIDITY', ascending=False)
    print(f"\n=== {file_csv} KARŞILAŞTIRMA ===")
    print(out.to_string(index=False))
    out.to_csv(file_csv.replace('.csv', '_solidity_comparison.csv'), index=False)

compare_solidity('nekheldgarabetaltiyedi.csv', 'correct_current_yield_nek_garabetaltiyedi.csv')
compare_solidity('nekheldotelremorta.csv', 'correct_current_yield_nek_otelremorta.csv')
print("\nKarşılaştırma tamamlandı!") 