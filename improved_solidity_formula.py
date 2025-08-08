import pandas as pd
import numpy as np

def calculate_improved_solidity(df):
    """Geliştirilmiş solidity formülü - düşük solidity nedenlerini daha iyi yansıtır"""
    
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
    df['COM_LAST_PRICE'] = df['COM_LAST_PRICE'].fillna(20)
    df['COM_MKTCAP'] = df['COM_MKTCAP'].fillna(1000)
    df['COM_52W_LOW'] = df['COM_52W_LOW'].fillna(15)
    df['COM_52W_HIGH'] = df['COM_52W_HIGH'].fillna(25)
    df['COM_FEB2020_PRICE'] = df['COM_FEB2020_PRICE'].fillna(20)
    df['COM_MAR2020_PRICE'] = df['COM_MAR2020_PRICE'].fillna(10)
    
    # Current yield hesapla
    df['CURRENT_YIELD'] = (df['COUPON'].str.rstrip('%').astype(float) / 100) / (df['Oct19_Price'] / 100) * 100
    df['RISK_PREMIUM'] = df['CURRENT_YIELD'] - 4.5
    df['IMPLIED_SOLIDITY'] = 90 / df['RISK_PREMIUM']
    
    # 1. Market Cap Risk Faktörü (0-20 arası)
    # Küçük market cap = yüksek risk = düşük solidity
    df['MARKET_CAP_RISK'] = np.clip(20 - np.log10(df['COM_MKTCAP']/100) * 4, 0, 20)
    
    # 2. Credit Risk Faktörü (0-20 arası)
    # Düşük credit score = yüksek risk = düşük solidity
    df['CREDIT_RISK'] = np.clip(20 - (df['CRDT_SCORE'] - 6) * 2, 0, 20)
    
    # 3. Price Performance Risk Faktörü (0-20 arası)
    # Kötü price performance = yüksek risk = düşük solidity
    price_performance = (df['COM_LAST_PRICE'] - df['COM_52W_LOW']) / (df['COM_52W_HIGH'] - df['COM_52W_LOW'])
    df['PRICE_RISK'] = np.clip(20 - price_performance * 20, 0, 20)
    
    # 4. COVID Recovery Risk Faktörü (0-20 arası)
    covid_recovery = (df['COM_LAST_PRICE'] - df['COM_MAR2020_PRICE']) / (df['COM_FEB2020_PRICE'] - df['COM_MAR2020_PRICE'])
    df['COVID_RISK'] = np.clip(20 - covid_recovery * 10, 0, 20)
    
    # 5. Current Yield Risk Faktörü (0-20 arası)
    # Yüksek current yield = yüksek risk = düşük solidity
    df['YIELD_RISK'] = np.clip(df['CURRENT_YIELD'] - 8, 0, 20)
    
    # Risk faktörlerini topla ve solidity'den çıkar
    total_risk = df['MARKET_CAP_RISK'] + df['CREDIT_RISK'] + df['PRICE_RISK'] + df['COVID_RISK'] + df['YIELD_RISK']
    
    # Base solidity score (yüksek riskli hisseler için düşük)
    base_solidity = 60  # Orta seviye base
    
    # Final solidity score
    df['CALCULATED_SOLIDITY'] = base_solidity - (total_risk / 5)  # Risk faktörlerinin ortalamasını çıkar
    
    # Maksimum ve minimum sınırlar
    df['CALCULATED_SOLIDITY'] = np.clip(df['CALCULATED_SOLIDITY'], 2, 80)
    
    return df

# Test: comekheldgarabetaltiyedi.csv (düşük solidity'li dosya)
print("=== GELİŞTİRİLMİŞ SOLIDITY FORMÜLÜ TEST ===")
try:
    df = pd.read_csv('comekheldgarabetaltiyedi.csv')
    df = calculate_improved_solidity(df)
    
    # Karşılaştırma için sonuçları hazırla
    comparison = df[['PREF IBKR', 'CMON', 'CURRENT_YIELD', 'RISK_PREMIUM', 'IMPLIED_SOLIDITY', 'CALCULATED_SOLIDITY']].copy()
    comparison['DIFFERENCE'] = comparison['CALCULATED_SOLIDITY'] - comparison['IMPLIED_SOLIDITY']
    comparison['PERCENTAGE_ERROR'] = abs(comparison['DIFFERENCE'] / comparison['IMPLIED_SOLIDITY']) * 100
    
    # En iyi uyumlar
    best_matches = comparison.nsmallest(5, 'PERCENTAGE_ERROR')
    worst_matches = comparison.nlargest(5, 'PERCENTAGE_ERROR')
    
    print("\nEn İyi Uyumlar:")
    print(best_matches.to_string(index=False))
    
    print("\nEn Kötü Uyumlar:")
    print(worst_matches.to_string(index=False))
    
    print(f"\nİstatistikler:")
    print(f"Ortalama Hata: {comparison['PERCENTAGE_ERROR'].mean():.1f}%")
    print(f"Medyan Hata: {comparison['PERCENTAGE_ERROR'].median():.1f}%")
    print(f"Standart Sapma: {comparison['PERCENTAGE_ERROR'].std():.1f}%")
    
    # Risk faktörlerinin analizi
    print(f"\nRisk Faktörleri Analizi:")
    print(f"Ortalama Market Cap Risk: {df['MARKET_CAP_RISK'].mean():.1f}")
    print(f"Ortalama Credit Risk: {df['CREDIT_RISK'].mean():.1f}")
    print(f"Ortalama Price Risk: {df['PRICE_RISK'].mean():.1f}")
    print(f"Ortalama COVID Risk: {df['COVID_RISK'].mean():.1f}")
    print(f"Ortalama Yield Risk: {df['YIELD_RISK'].mean():.1f}")
    
    # Sonuçları kaydet
    comparison.to_csv('improved_solidity_results.csv', index=False)
    
except Exception as e:
    print(f"Hata: {e}")

print("\n" + "="*50)
print("Geliştirilmiş formül testi tamamlandı!") 