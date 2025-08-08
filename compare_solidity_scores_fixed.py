import pandas as pd
import numpy as np

def our_solidity_formula_fixed(df):
    n = len(df)
    
    # Common stock verisi var mı kontrol et
    has_common_data = 'COM_MKTCAP' in df.columns and 'Last Price' in df.columns and 'COM_52W_LOW' in df.columns and 'COM_52W_HIGH' in df.columns
    
    if not has_common_data:
        # Common stock verisi yoksa solidity = 25
        df['OUR_SOLIDITY'] = 25
        return df
    
    # Common stock verisi varsa, CMON bazında hesapla
    # Her CMON için tek bir solidity değeri hesapla
    cmon_solidity = {}
    
    for cmon in df['CMON'].unique():
        if pd.isna(cmon) or cmon == '-':
            cmon_solidity[cmon] = 25
            continue
            
        # Bu CMON için verileri al
        cmon_data = df[df['CMON'] == cmon].iloc[0]  # İlk satırı al
        
        # Credit score
        crdt_score = pd.to_numeric(cmon_data.get('CRDT_SCORE', 8), errors='coerce')
        if pd.isna(crdt_score):
            crdt_score = 8
            
        # Market cap
        mktcap = pd.to_numeric(cmon_data.get('COM_MKTCAP', 1000), errors='coerce')
        if pd.isna(mktcap):
            mktcap = 1000
            
        # Price data
        last_price = pd.to_numeric(cmon_data.get('Last Price', 20), errors='coerce')
        if pd.isna(last_price):
            last_price = 20
            
        low = pd.to_numeric(cmon_data.get('COM_52W_LOW', 15), errors='coerce')
        if pd.isna(low):
            low = 15
            
        high = pd.to_numeric(cmon_data.get('COM_52W_HIGH', 25), errors='coerce')
        if pd.isna(high):
            high = 25
            
        # Market Cap Score (0-20)
        market_cap_score = np.clip(np.log10(mktcap/1000) * 6, 0, 20)
        
        # Credit Score (0-20)
        credit_score = np.clip(crdt_score * 1.33, 0, 20)
        
        # Price Score (0-20)
        price_score = np.clip((last_price - low) / (high - low) * 20, 0, 20)
        
        # Final solidity (CMON bazında)
        cmon_solidity[cmon] = 20 + market_cap_score + credit_score + price_score
    
    # Her satır için CMON'a göre solidity ata
    df['OUR_SOLIDITY'] = df['CMON'].map(cmon_solidity)
    
    return df

def compare_solidity_fixed(file_csv, file_cy):
    df = pd.read_csv(file_csv)
    df_cy = pd.read_csv(file_cy)
    merged = pd.merge(df, df_cy[['PREF IBKR', 'CURRENT_YIELD', 'IMPLIED_SOLIDITY']], on='PREF IBKR', how='left')
    merged = our_solidity_formula_fixed(merged)
    out = merged[['PREF IBKR', 'CMON', 'CURRENT_YIELD', 'IMPLIED_SOLIDITY', 'OUR_SOLIDITY']].copy()
    out = out.sort_values('IMPLIED_SOLIDITY', ascending=False)
    print(f"\n=== {file_csv} DÜZELTİLMİŞ KARŞILAŞTIRMA ===")
    print(out.to_string(index=False))
    out.to_csv(file_csv.replace('.csv', '_solidity_comparison_fixed.csv'), index=False)

compare_solidity_fixed('nekheldgarabetaltiyedi.csv', 'correct_current_yield_nek_garabetaltiyedi.csv')
compare_solidity_fixed('nekheldotelremorta.csv', 'correct_current_yield_nek_otelremorta.csv')
print("\nDüzeltilmiş karşılaştırma tamamlandı!") 