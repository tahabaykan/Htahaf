import pandas as pd
import numpy as np

def calculate_correct_current_yield_with_nek_files():
    """Nek dosyalarından doğru current yield hesaplama (25 / div adj price) * coupon rate"""
    
    # Test 1: nekheldgarabetaltiyedi.csv
    print("=== NEKHELDGARABETALTIYEDI.CSV CURRENT YIELD TEST ===")
    try:
        df1 = pd.read_csv('nekheldgarabetaltiyedi.csv')
        div_adj_price_col = 'Div adj.price'
        if div_adj_price_col in df1.columns:
            print(f"Div adj price sütunu bulundu: {div_adj_price_col}")
            df1['COUPON_RATE'] = df1['COUPON'].str.rstrip('%').astype(float) / 100
            df1['DIV_ADJ_PRICE'] = pd.to_numeric(df1[div_adj_price_col], errors='coerce')
            df1['CURRENT_YIELD'] = (25 / df1['DIV_ADJ_PRICE']) * df1['COUPON_RATE'] * 100  # % olarak
            df1['RISK_PREMIUM'] = df1['CURRENT_YIELD'] - 4.5
            df1['IMPLIED_SOLIDITY'] = 90 / df1['RISK_PREMIUM']
            results1 = df1[['PREF IBKR', 'CMON', 'COUPON', div_adj_price_col, 'CURRENT_YIELD', 'RISK_PREMIUM', 'IMPLIED_SOLIDITY']].copy()
            results1 = results1.sort_values('CURRENT_YIELD', ascending=False)
            print("\nEn Yüksek Current Yield'lar:")
            print(results1.head(10).to_string(index=False))
            print(f"\nİstatistikler:")
            print(f"Ortalama Current Yield: {results1['CURRENT_YIELD'].mean():.2f}%")
            print(f"En Yüksek Current Yield: {results1['CURRENT_YIELD'].max():.2f}%")
            print(f"En Düşük Current Yield: {results1['CURRENT_YIELD'].min():.2f}%")
            print(f"Ortalama Risk Premium: {results1['RISK_PREMIUM'].mean():.2f}%")
            print(f"Ortalama Implied Solidity: {results1['IMPLIED_SOLIDITY'].mean():.1f}")
            results1.to_csv('correct_current_yield_nek_garabetaltiyedi.csv', index=False)
        else:
            print("Div adj price sütunu bulunamadı!")
    except Exception as e:
        print(f"Hata: {e}")
    print("\n" + "="*50)
    # Test 2: nekheldotelremorta.csv
    print("=== NEKHELDOTELREMORTA.CSV CURRENT YIELD TEST ===")
    try:
        df2 = pd.read_csv('nekheldotelremorta.csv')
        div_adj_price_col = 'Div adj.price'
        if div_adj_price_col in df2.columns:
            print(f"Div adj price sütunu bulundu: {div_adj_price_col}")
            df2['COUPON_RATE'] = df2['COUPON'].str.rstrip('%').astype(float) / 100
            df2['DIV_ADJ_PRICE'] = pd.to_numeric(df2[div_adj_price_col], errors='coerce')
            df2['CURRENT_YIELD'] = (25 / df2['DIV_ADJ_PRICE']) * df2['COUPON_RATE'] * 100
            df2['RISK_PREMIUM'] = df2['CURRENT_YIELD'] - 4.5
            df2['IMPLIED_SOLIDITY'] = 90 / df2['RISK_PREMIUM']
            results2 = df2[['PREF IBKR', 'CMON', 'COUPON', div_adj_price_col, 'CURRENT_YIELD', 'RISK_PREMIUM', 'IMPLIED_SOLIDITY']].copy()
            results2 = results2.sort_values('CURRENT_YIELD', ascending=False)
            print(f"\nİstatistikler:")
            print(f"Ortalama Current Yield: {results2['CURRENT_YIELD'].mean():.2f}%")
            print(f"En Yüksek Current Yield: {results2['CURRENT_YIELD'].max():.2f}%")
            print(f"En Düşük Current Yield: {results2['CURRENT_YIELD'].min():.2f}%")
            print(f"Ortalama Risk Premium: {results2['RISK_PREMIUM'].mean():.2f}%")
            print(f"Ortalama Implied Solidity: {results2['IMPLIED_SOLIDITY'].mean():.1f}")
            results2.to_csv('correct_current_yield_nek_otelremorta.csv', index=False)
        else:
            print("Div adj price sütunu bulunamadı!")
    except Exception as e:
        print(f"Hata: {e}")
    print("\n" + "="*50)
    # Test 3: nekheldkuponlu.csv (ana dosya)
    print("=== NEKHELDKUPONLU.CSV CURRENT YIELD TEST ===")
    try:
        df3 = pd.read_csv('nekheldkuponlu.csv')
        div_adj_price_col = 'Div adj.price'
        if div_adj_price_col in df3.columns:
            print(f"Div adj price sütunu bulundu: {div_adj_price_col}")
            df3['COUPON_RATE'] = df3['COUPON'].str.rstrip('%').astype(float) / 100
            df3['DIV_ADJ_PRICE'] = pd.to_numeric(df3[div_adj_price_col], errors='coerce')
            df3['CURRENT_YIELD'] = (25 / df3['DIV_ADJ_PRICE']) * df3['COUPON_RATE'] * 100
            df3['RISK_PREMIUM'] = df3['CURRENT_YIELD'] - 4.5
            df3['IMPLIED_SOLIDITY'] = 90 / df3['RISK_PREMIUM']
            results3 = df3[['PREF IBKR', 'CMON', 'COUPON', div_adj_price_col, 'CURRENT_YIELD', 'RISK_PREMIUM', 'IMPLIED_SOLIDITY']].copy()
            results3 = results3.sort_values('CURRENT_YIELD', ascending=False)
            print(f"\nİstatistikler:")
            print(f"Ortalama Current Yield: {results3['CURRENT_YIELD'].mean():.2f}%")
            print(f"En Yüksek Current Yield: {results3['CURRENT_YIELD'].max():.2f}%")
            print(f"En Düşük Current Yield: {results3['CURRENT_YIELD'].min():.2f}%")
            print(f"Ortalama Risk Premium: {results3['RISK_PREMIUM'].mean():.2f}%")
            print(f"Ortalama Implied Solidity: {results3['IMPLIED_SOLIDITY'].mean():.1f}")
            results3.to_csv('correct_current_yield_nek_kuponlu.csv', index=False)
        else:
            print("Div adj price sütunu bulunamadı!")
    except Exception as e:
        print(f"Hata: {e}")
    print("\n" + "="*50)
    print("Doğru current yield hesaplama tamamlandı!")

if __name__ == "__main__":
    calculate_correct_current_yield_with_nek_files() 