import pandas as pd
import numpy as np

# Load the data with new TOTAL_SCORE calculations
df = pd.read_csv('allcomek_sld.csv')

# Stocks to analyze
stocks_to_check = ['PSA', 'SO', 'ETR', 'DTE', 'ACGL', 'FCNCA', 'AFG', 'CMS']

print("=== YENİ TOTAL_SCORE ANALİZİ (Fiyat Değişim Mantığı) ===\n")

def safe_fmt(val):
    try:
        return f"{float(val):.2f}"
    except:
        return str(val)

for stock in stocks_to_check:
    if stock in df['CMON'].values:
        stock_data = df[df['CMON'] == stock].iloc[0]
        
        print(f"\n{'='*60}")
        print(f"HİSSE: {stock}")
        print(f"{'='*60}")
        
        print(f"LAST_PRICE: {safe_fmt(stock_data['COM_LAST_PRICE'])}")
        
        # Show price changes
        change_columns = [col for col in df.columns if col.startswith('CHANGE_')]
        print(f"\nFİYAT DEĞİŞİMLERİ (%):")
        for col in change_columns:
            if col in stock_data:
                change_value = stock_data[col]
                norm_col = col + '_NORM'
                norm_value = stock_data[norm_col] if norm_col in stock_data else 'N/A'
                
                # Extract the price point name for display
                point_name = col.replace('CHANGE_COM_', '').replace('_PRICE', '').replace('_', ' ')
                print(f"  {point_name}: {safe_fmt(change_value)}% (Norm: {safe_fmt(norm_value)})")
        
        # Show TOTAL_SCORE
        print(f"\nTOTAL SKOR:")
        total_score = stock_data.get('TOTAL_SCORE', 'N/A')
        total_score_norm = stock_data.get('TOTAL_SCORE_NORM', 'N/A')
        print(f"  TOTAL_SCORE: {safe_fmt(total_score)}")
        print(f"  TOTAL_SCORE_NORM: {safe_fmt(total_score_norm)}")
        
        # Show other scores
        print(f"\nDİĞER SKORLAR:")
        mktcap_norm = stock_data.get('MKTCAP_NORM', 'N/A')
        crdt_norm = stock_data.get('CRDT_NORM', 'N/A')
        solidity_score = stock_data.get('SOLIDITY_SCORE', 'N/A')
        solidity_score_norm = stock_data.get('SOLIDITY_SCORE_NORM', 'N/A')
        print(f"  MKTCAP_NORM: {safe_fmt(mktcap_norm)}")
        print(f"  CRDT_NORM: {safe_fmt(crdt_norm)}")
        print(f"  SOLIDITY_SCORE: {safe_fmt(solidity_score)}")
        print(f"  SOLIDITY_SCORE_NORM: {safe_fmt(solidity_score_norm)}")
        
    else:
        print(f"\n{stock} hissesi bulunamadı!")

print(f"\n{'='*60}")
print("ANALİZ TAMAMLANDI")
print(f"{'='*60}") 