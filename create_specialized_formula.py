import pandas as pd
import numpy as np

def calculate_specialized_solidity(df, target_range=(2, 4)):
    """Bu dosyalar için özelleştirilmiş solidity formülü"""
    # Gerekli sütunları sayısal hale getir
    df['CRDT_SCORE'] = pd.to_numeric(df['CRDT_SCORE'], errors='coerce')
    df['COM_LAST_PRICE'] = pd.to_numeric(df['COM_LAST_PRICE'], errors='coerce')
    df['COM_MKTCAP'] = pd.to_numeric(df['COM_MKTCAP'], errors='coerce')
    df['COM_52W_LOW'] = pd.to_numeric(df['COM_52W_LOW'], errors='coerce')
    df['COM_52W_HIGH'] = pd.to_numeric(df['COM_52W_HIGH'], errors='coerce')
    df['COM_FEB2020_PRICE'] = pd.to_numeric(df['COM_FEB2020_PRICE'], errors='coerce')
    df['COM_MAR2020_PRICE'] = pd.to_numeric(df['COM_MAR2020_PRICE'], errors='coerce')
    
    # Eksik verileri doldur
    df['CRDT_SCORE'] = df['CRDT_SCORE'].fillna(8)
    df['COM_LAST_PRICE'] = df['COM_LAST_PRICE'].fillna(15)
    df['COM_MKTCAP'] = df['COM_MKTCAP'].fillna(500)
    df['COM_52W_LOW'] = df['COM_52W_LOW'].fillna(10)
    df['COM_52W_HIGH'] = df['COM_52W_HIGH'].fillna(20)
    df['COM_FEB2020_PRICE'] = df['COM_FEB2020_PRICE'].fillna(15)
    df['COM_MAR2020_PRICE'] = df['COM_MAR2020_PRICE'].fillna(8)
    
    # Market Cap Score (0-1 arası, küçük değerler için)
    df['MARKET_CAP_SCORE'] = np.clip(np.log10(df['COM_MKTCAP']/100) * 0.3, 0, 1)
    
    # Credit Score (0-1 arası)
    df['CREDIT_SCORE'] = np.clip((df['CRDT_SCORE'] - 6) / 6, 0, 1)
    
    # Price Score (0-1 arası)
    # COVID öncesi performans
    covid_pre_score = np.clip((df['COM_LAST_PRICE'] - df['COM_MAR2020_PRICE']) / (df['COM_FEB2020_PRICE'] - df['COM_MAR2020_PRICE']), 0, 1)
    
    # 52-week pozisyon
    week52_score = np.clip((df['COM_LAST_PRICE'] - df['COM_52W_LOW']) / (df['COM_52W_HIGH'] - df['COM_52W_LOW']), 0, 1)
    
    df['PRICE_SCORE'] = (covid_pre_score + week52_score) / 2
    
    # Base score + weighted components
    base_score = 2.0  # Hedef aralığın alt sınırı
    df['CALCULATED_SOLIDITY'] = base_score + (df['MARKET_CAP_SCORE'] * 0.5) + (df['CREDIT_SCORE'] * 0.5) + (df['PRICE_SCORE'] * 0.5)
    
    # Maksimum 4'e sınırla
    df['CALCULATED_SOLIDITY'] = np.clip(df['CALCULATED_SOLIDITY'], 2, 4)
    
    return df

def calculate_implied_solidity(df, risk_free_rate=4.5):
    """Implied solidity hesapla"""
    df['CURRENT_YIELD'] = (df['COUPON'].str.rstrip('%').astype(float) / 100) / (df['Oct19_Price'] / 100) * 100
    df['RISK_PREMIUM'] = df['CURRENT_YIELD'] - risk_free_rate
    df['IMPLIED_SOLIDITY'] = 90 / df['RISK_PREMIUM']
    return df

# Test 1: comekheldotelremorta.csv
print("=== COMEKHELDOTELREMORTA.CSV ÖZELLEŞTİRİLMİŞ FORMÜL TEST ===")
try:
    df1 = pd.read_csv('comekheldotelremorta.csv')
    
    # Her iki hesaplamayı yap
    df1 = calculate_specialized_solidity(df1)
    df1 = calculate_implied_solidity(df1)
    
    # Karşılaştırma için sonuçları hazırla
    comparison1 = df1[['PREF IBKR', 'CMON', 'CALCULATED_SOLIDITY', 'IMPLIED_SOLIDITY']].copy()
    comparison1['DIFFERENCE'] = comparison1['CALCULATED_SOLIDITY'] - comparison1['IMPLIED_SOLIDITY']
    comparison1['PERCENTAGE_ERROR'] = abs(comparison1['DIFFERENCE'] / comparison1['IMPLIED_SOLIDITY']) * 100
    
    # En iyi uyumlar
    best_matches1 = comparison1.nsmallest(5, 'PERCENTAGE_ERROR')
    worst_matches1 = comparison1.nlargest(5, 'PERCENTAGE_ERROR')
    
    print("\nEn İyi Uyumlar:")
    print(best_matches1.to_string(index=False))
    
    print("\nEn Kötü Uyumlar:")
    print(worst_matches1.to_string(index=False))
    
    print(f"\nİstatistikler:")
    print(f"Ortalama Hata: {comparison1['PERCENTAGE_ERROR'].mean():.1f}%")
    print(f"Medyan Hata: {comparison1['PERCENTAGE_ERROR'].median():.1f}%")
    print(f"Standart Sapma: {comparison1['PERCENTAGE_ERROR'].std():.1f}%")
    
    # Sonuçları kaydet
    comparison1.to_csv('specialized_solidity_otelremorta.csv', index=False)
    
except Exception as e:
    print(f"Hata: {e}")

print("\n" + "="*50)

# Test 2: comekheldgarabetaltiyedi.csv
print("=== COMEKHELDGARABETALTIYEDI.CSV ÖZELLEŞTİRİLMİŞ FORMÜL TEST ===")
try:
    df2 = pd.read_csv('comekheldgarabetaltiyedi.csv')
    
    # Her iki hesaplamayı yap
    df2 = calculate_specialized_solidity(df2)
    df2 = calculate_implied_solidity(df2)
    
    # Karşılaştırma için sonuçları hazırla
    comparison2 = df2[['PREF IBKR', 'CMON', 'CALCULATED_SOLIDITY', 'IMPLIED_SOLIDITY']].copy()
    comparison2['DIFFERENCE'] = comparison2['CALCULATED_SOLIDITY'] - comparison2['IMPLIED_SOLIDITY']
    comparison2['PERCENTAGE_ERROR'] = abs(comparison2['DIFFERENCE'] / comparison2['IMPLIED_SOLIDITY']) * 100
    
    # En iyi uyumlar
    best_matches2 = comparison2.nsmallest(5, 'PERCENTAGE_ERROR')
    worst_matches2 = comparison2.nlargest(5, 'PERCENTAGE_ERROR')
    
    print("\nEn İyi Uyumlar:")
    print(best_matches2.to_string(index=False))
    
    print("\nEn Kötü Uyumlar:")
    print(worst_matches2.to_string(index=False))
    
    print(f"\nİstatistikler:")
    print(f"Ortalama Hata: {comparison2['PERCENTAGE_ERROR'].mean():.1f}%")
    print(f"Medyan Hata: {comparison2['PERCENTAGE_ERROR'].median():.1f}%")
    print(f"Standart Sapma: {comparison2['PERCENTAGE_ERROR'].std():.1f}%")
    
    # Sonuçları kaydet
    comparison2.to_csv('specialized_solidity_garabetaltiyedi.csv', index=False)
    
except Exception as e:
    print(f"Hata: {e}")

print("\n" + "="*50)
print("Özelleştirilmiş formül testi tamamlandı!") 