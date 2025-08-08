import pandas as pd
import numpy as np

def clean_numeric_data(df):
    numeric_columns = [
        'COM_LAST_PRICE', 'COM_52W_LOW', 'COM_52W_HIGH',
        'COM_6M_PRICE', 'COM_3M_PRICE', 'COM_5Y_LOW',
        'COM_5Y_HIGH', 'COM_MKTCAP', 'CRDT_SCORE',
        'COM_FEB2020_PRICE', 'COM_MAR2020_PRICE'
    ]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(',', '')
                .str.replace('$', '')
                .str.replace('B', '')
            )
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df

def normalize_custom(series):
    valid_series = series[pd.notnull(series)]
    if valid_series.empty:
        return pd.Series(1, index=series.index)
    max_val = valid_series.max()
    min_val = valid_series.min()
    if max_val == min_val:
        return pd.Series(1, index=series.index)
    return 1 + ((series - min_val) / (max_val - min_val)) * 99

def normalize_score(series):
    valid_series = series.dropna()
    if valid_series.empty:
        return pd.Series(10, index=series.index)
    min_val = valid_series.min()
    max_val = valid_series.max()
    if min_val == max_val:
        return pd.Series(10, index=series.index)
    normalized = 10 + ((series - min_val) / (max_val - min_val)) * 80
    return normalized.clip(lower=10, upper=90)

def normalize_market_cap(series):
    def score_market_cap(x):
        if pd.isna(x):
            return 35
        billions = float(x)
        if billions >= 500:
            return 95
        elif billions >= 200:
            return 90 + ((billions - 200) / 300) * 5
        elif billions >= 100:
            return 85 + ((billions - 100) / 100) * 5
        elif billions >= 50:
            return 77 + ((billions - 50) / 50) * 8
        elif billions >= 10:
            return 60 + ((billions - 10) / 40) * 17
        elif billions >= 5:
            return 50 + ((billions - 5) / 5) * 10
        elif billions >= 1:
            return 40 + ((billions - 1) / 4) * 10
        else:
            return max(35, 35 + (billions * 5))
    return series.apply(score_market_cap)

def calculate_solidity_scores(df):
    # Market Cap norm
    df['MKTCAP_NORM'] = normalize_market_cap(df['COM_MKTCAP'])
    # Credit Score norm
    df['CRDT_NORM'] = normalize_custom(df['CRDT_SCORE'])
    # TOTAL_SCORE_NORM için örnek: sadece COM_LAST_PRICE ve CRDT_NORM ile (daha gelişmişi eklenebilir)
    df['TOTAL_SCORE_NORM'] = normalize_custom(df['COM_LAST_PRICE'].fillna(0) + df['CRDT_NORM'].fillna(0))
    def calc_solidity(row):
        market_cap = row['COM_MKTCAP']
        mktcap_norm = row['MKTCAP_NORM']
        if pd.isna(market_cap):
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.4 + row['MKTCAP_NORM'] * 0.35 + row['CRDT_NORM'] * 0.25)
        elif market_cap >= 1 and market_cap < 3:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.65 + row['MKTCAP_NORM'] * 0.25 + row['CRDT_NORM'] * 0.10)
        elif market_cap >= 3 and market_cap < 7:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.55 + row['MKTCAP_NORM'] * 0.30 + row['CRDT_NORM'] * 0.15)
        elif market_cap >= 7 and market_cap < 12:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.40 + row['MKTCAP_NORM'] * 0.40 + row['CRDT_NORM'] * 0.20)
        elif market_cap >= 12 and market_cap < 20:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.35 + row['MKTCAP_NORM'] * 0.45 + row['CRDT_NORM'] * 0.20)
        elif market_cap >= 20 and market_cap < 35:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.30 + row['MKTCAP_NORM'] * 0.50 + row['CRDT_NORM'] * 0.20)
        elif market_cap >= 35 and market_cap < 75:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.25 + row['MKTCAP_NORM'] * 0.50 + row['CRDT_NORM'] * 0.25)
        elif market_cap >= 75 and market_cap < 200:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.15 + row['MKTCAP_NORM'] * 0.55 + row['CRDT_NORM'] * 0.30)
        elif market_cap >= 200:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.10 + row['MKTCAP_NORM'] * 0.55 + row['CRDT_NORM'] * 0.35)
        else:
            solidity = mktcap_norm * (row['TOTAL_SCORE_NORM'] * 0.70 + row['MKTCAP_NORM'] * 0.20 + row['CRDT_NORM'] * 0.10)
        # BB ise %2 artır
        try:
            if 'Type' in row and str(row['Type']).strip() == 'BB':
                solidity *= 1.02
        except:
            pass
        return solidity
    df['SOLIDITY_SCORE'] = df.apply(calc_solidity, axis=1)
    # Normalize solidity (10-90 arası)
    df['SOLIDITY_SCORE_NORM'] = normalize_score(df['SOLIDITY_SCORE'])
    return df

def main():
    df = pd.read_csv('allcomek.csv', encoding='utf-8-sig')
    df = clean_numeric_data(df)
    df = calculate_solidity_scores(df)
    df.to_csv('allcomek_sld.csv', index=False, encoding='utf-8-sig')
    print("allcomek_sld.csv dosyası oluşturuldu!")
    print(df[['PREF IBKR','SOLIDITY_SCORE','SOLIDITY_SCORE_NORM']].head(10))

if __name__ == "__main__":
    main() 