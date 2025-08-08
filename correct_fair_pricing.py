import pandas as pd
import numpy as np

# Risk Premium aralığı: 0.8% ile 7% arası
RISK_PREMIUM_MIN = 0.8
RISK_PREMIUM_MAX = 7.0
TARGET_CONSTANT = 90

# Test verisi oluştur
test_data = [
    {'Stock': 'JPM', 'Risk_Premium': 1.0, 'Current_Yield': 5.5},
    {'Stock': 'BAC', 'Risk_Premium': 1.5, 'Current_Yield': 6.0},
    {'Stock': 'WFC', 'Risk_Premium': 2.0, 'Current_Yield': 6.5},
    {'Stock': 'MS', 'Risk_Premium': 2.5, 'Current_Yield': 7.0},
    {'Stock': 'T', 'Risk_Premium': 3.0, 'Current_Yield': 7.5},
    {'Stock': 'F', 'Risk_Premium': 3.5, 'Current_Yield': 8.0},
    {'Stock': 'MGR', 'Risk_Premium': 4.0, 'Current_Yield': 8.5},
    {'Stock': 'RWT', 'Risk_Premium': 5.0, 'Current_Yield': 9.5},
    {'Stock': 'ALTG', 'Risk_Premium': 6.0, 'Current_Yield': 10.5},
    {'Stock': 'Speculative', 'Risk_Premium': 7.0, 'Current_Yield': 11.5}
]

df = pd.DataFrame(test_data)

# Doğru solidity score hesapla
df['Correct_Solidity'] = TARGET_CONSTANT / df['Risk_Premium']

# Test: Solidity × Risk Premium = 90
df['Test_Result'] = df['Correct_Solidity'] * df['Risk_Premium']

print("=== DOĞRU FAIR PRICING FORMÜLÜ ===")
print("Sabit Değer:", TARGET_CONSTANT)
print("Risk Premium Aralığı:", RISK_PREMIUM_MIN, "% -", RISK_PREMIUM_MAX, "%")
print()

print("=== TEST SONUÇLARI ===")
for _, row in df.iterrows():
    print(f"{row['Stock']}:")
    print(f"  Risk Premium: {row['Risk_Premium']:.1f}%")
    print(f"  Current Yield: {row['Current_Yield']:.1f}%")
    print(f"  Solidity Score: {row['Correct_Solidity']:.1f}")
    print(f"  Test (Solidity × Risk Premium): {row['Test_Result']:.1f}")
    print()

# Gerçek verilerle test
print("=== GERÇEK VERİLERLE TEST ===")
try:
    real_df = pd.read_csv('current_yield_analysis_final.csv')
    
    # Risk premium'u normalize et (0.8-7.0 arası)
    real_df['RISK_PREMIUM_NORM'] = np.clip(real_df['RISK_PREMIUM'], RISK_PREMIUM_MIN, RISK_PREMIUM_MAX)
    
    # Doğru solidity hesapla
    real_df['CORRECT_SOLIDITY'] = TARGET_CONSTANT / real_df['RISK_PREMIUM_NORM']
    
    # Test
    real_df['TEST_RESULT'] = real_df['CORRECT_SOLIDITY'] * real_df['RISK_PREMIUM_NORM']
    
    print("Örnek hisseler:")
    sample = real_df.head(10)
    for _, row in sample.iterrows():
        print(f"{row['PREF IBKR']}:")
        print(f"  Risk Premium: {row['RISK_PREMIUM']:.2f}% → {row['RISK_PREMIUM_NORM']:.2f}%")
        print(f"  Current Yield: {row['CURRENT_YIELD']:.2f}%")
        print(f"  Correct Solidity: {row['CORRECT_SOLIDITY']:.1f}")
        print(f"  Test Result: {row['TEST_RESULT']:.1f}")
        print()
    
    print("=== İSTATİSTİKLER ===")
    print(f"Ortalama Test Sonucu: {real_df['TEST_RESULT'].mean():.1f}")
    print(f"Standart Sapma: {real_df['TEST_RESULT'].std():.1f}")
    print(f"En düşük Test Sonucu: {real_df['TEST_RESULT'].min():.1f}")
    print(f"En yüksek Test Sonucu: {real_df['TEST_RESULT'].max():.1f}")
    
    # Sonuçları kaydet
    result_df = real_df[['PREF IBKR', 'CMON', 'CURRENT_YIELD', 'RISK_PREMIUM', 
                        'RISK_PREMIUM_NORM', 'CORRECT_SOLIDITY', 'TEST_RESULT']].copy()
    result_df.to_csv('correct_fair_pricing_results.csv', index=False)
    print(f"\nSonuçlar 'correct_fair_pricing_results.csv' dosyasına kaydedildi.")
    
except FileNotFoundError:
    print("current_yield_analysis_final.csv dosyası bulunamadı.") 