import pandas as pd
import numpy as np

def calculate_correct_current_yield(df):
    """Doğru current yield hesaplama"""
    
    # Coupon rate'i sayısal hale getir (% işaretini kaldır)
    df['COUPON_RATE'] = df['COUPON'].str.rstrip('%').astype(float) / 100
    
    # Div adj price'ı sayısal hale getir
    df['DIV_ADJ_PRICE'] = pd.to_numeric(df['Oct19_Price'], errors='coerce')
    
    # Doğru current yield formülü: (Coupon Rate / Div Adj Price) * 100
    df['CURRENT_YIELD'] = (df['COUPON_RATE'] / df['DIV_ADJ_PRICE']) * 100
    
    # Risk premium hesapla
    df['RISK_PREMIUM'] = df['CURRENT_YIELD'] - 4.5
    
    # Implied solidity hesapla
    df['IMPLIED_SOLIDITY'] = 90 / df['RISK_PREMIUM']
    
    return df

# Test: comekheldgarabetaltiyedi.csv
print("=== DOĞRU CURRENT YIELD HESAPLAMA TEST ===")
try:
    df = pd.read_csv('comekheldgarabetaltiyedi.csv')
    df = calculate_correct_current_yield(df)
    
    # Sonuçları göster
    results = df[['PREF IBKR', 'CMON', 'COUPON', 'Oct19_Price', 'CURRENT_YIELD', 'RISK_PREMIUM', 'IMPLIED_SOLIDITY']].copy()
    results = results.sort_values('CURRENT_YIELD', ascending=False)
    
    print("\nEn Yüksek Current Yield'lar:")
    print(results.head(10).to_string(index=False))
    
    print("\nEn Düşük Current Yield'lar:")
    print(results.tail(10).to_string(index=False))
    
    print(f"\nİstatistikler:")
    print(f"Ortalama Current Yield: {results['CURRENT_YIELD'].mean():.2f}%")
    print(f"Medyan Current Yield: {results['CURRENT_YIELD'].median():.2f}%")
    print(f"En Yüksek Current Yield: {results['CURRENT_YIELD'].max():.2f}%")
    print(f"En Düşük Current Yield: {results['CURRENT_YIELD'].min():.2f}%")
    
    print(f"\nRisk Premium İstatistikleri:")
    print(f"Ortalama Risk Premium: {results['RISK_PREMIUM'].mean():.2f}%")
    print(f"En Yüksek Risk Premium: {results['RISK_PREMIUM'].max():.2f}%")
    print(f"En Düşük Risk Premium: {results['RISK_PREMIUM'].min():.2f}%")
    
    print(f"\nImplied Solidity İstatistikleri:")
    print(f"Ortalama Implied Solidity: {results['IMPLIED_SOLIDITY'].mean():.1f}")
    print(f"En Yüksek Implied Solidity: {results['IMPLIED_SOLIDITY'].max():.1f}")
    print(f"En Düşük Implied Solidity: {results['IMPLIED_SOLIDITY'].min():.1f}")
    
    # Sonuçları kaydet
    results.to_csv('correct_current_yield_results.csv', index=False)
    
except Exception as e:
    print(f"Hata: {e}")

print("\n" + "="*50)

# Test: comekheldotelremorta.csv
print("=== COMEKHELDOTELREMORTA.CSV DOĞRU CURRENT YIELD TEST ===")
try:
    df2 = pd.read_csv('comekheldotelremorta.csv')
    df2 = calculate_correct_current_yield(df2)
    
    # Sonuçları göster
    results2 = df2[['PREF IBKR', 'CMON', 'COUPON', 'Oct19_Price', 'CURRENT_YIELD', 'RISK_PREMIUM', 'IMPLIED_SOLIDITY']].copy()
    results2 = results2.sort_values('CURRENT_YIELD', ascending=False)
    
    print(f"\nİstatistikler:")
    print(f"Ortalama Current Yield: {results2['CURRENT_YIELD'].mean():.2f}%")
    print(f"En Yüksek Current Yield: {results2['CURRENT_YIELD'].max():.2f}%")
    print(f"En Düşük Current Yield: {results2['CURRENT_YIELD'].min():.2f}%")
    print(f"Ortalama Risk Premium: {results2['RISK_PREMIUM'].mean():.2f}%")
    print(f"Ortalama Implied Solidity: {results2['IMPLIED_SOLIDITY'].mean():.1f}")
    
    # Sonuçları kaydet
    results2.to_csv('correct_current_yield_otelremorta.csv', index=False)
    
except Exception as e:
    print(f"Hata: {e}")

print("\n" + "="*50)
print("Doğru current yield hesaplama tamamlandı!") 