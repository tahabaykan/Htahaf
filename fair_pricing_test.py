import pandas as pd
import numpy as np

# Örnek veri oluştur
test_data = [
    {'Stock': 'A', 'Current_Yield': 8.0, 'Solidity': 51, 'Risk_Premium': 3.5},
    {'Stock': 'B', 'Current_Yield': 7.0, 'Solidity': 58, 'Risk_Premium': 2.5},
    {'Stock': 'C', 'Current_Yield': 6.0, 'Solidity': 65, 'Risk_Premium': 1.5},
    {'Stock': 'D', 'Current_Yield': 9.0, 'Solidity': 45, 'Risk_Premium': 4.5},
    {'Stock': 'E', 'Current_Yield': 5.5, 'Solidity': 70, 'Risk_Premium': 1.0}
]

df = pd.DataFrame(test_data)

print("=== FAIR PRICING FORMÜL TESTİ ===")
print("Test Verisi:")
print(df)
print()

# Formül 1: Solidity × Current Yield
df['Formula1'] = df['Solidity'] * df['Current_Yield']
print("=== FORMÜL 1: Solidity × Current Yield ===")
print(df[['Stock', 'Current_Yield', 'Solidity', 'Formula1']])
print(f"Ortalama: {df['Formula1'].mean():.1f}")
print(f"Standart Sapma: {df['Formula1'].std():.1f}")
print()

# Formül 2: Solidity / Current Yield
df['Formula2'] = df['Solidity'] / df['Current_Yield']
print("=== FORMÜL 2: Solidity / Current Yield ===")
print(df[['Stock', 'Current_Yield', 'Solidity', 'Formula2']])
print(f"Ortalama: {df['Formula2'].mean():.1f}")
print(f"Standart Sapma: {df['Formula2'].std():.1f}")
print()

# Formül 3: (Solidity × Current Yield) / Risk Premium
df['Formula3'] = (df['Solidity'] * df['Current_Yield']) / df['Risk_Premium']
print("=== FORMÜL 3: (Solidity × Current Yield) / Risk Premium ===")
print(df[['Stock', 'Current_Yield', 'Solidity', 'Risk_Premium', 'Formula3']])
print(f"Ortalama: {df['Formula3'].mean():.1f}")
print(f"Standart Sapma: {df['Formula3'].std():.1f}")
print()

# Formül 4: Solidity / Risk Premium
df['Formula4'] = df['Solidity'] / df['Risk_Premium']
print("=== FORMÜL 4: Solidity / Risk Premium ===")
print(df[['Stock', 'Solidity', 'Risk_Premium', 'Formula4']])
print(f"Ortalama: {df['Formula4'].mean():.1f}")
print(f"Standart Sapma: {df['Formula4'].std():.1f}")
print()

# Formül 5: Solidity × (1 / Risk Premium)
df['Formula5'] = df['Solidity'] * (1 / df['Risk_Premium'])
print("=== FORMÜL 5: Solidity × (1 / Risk Premium) ===")
print(df[['Stock', 'Solidity', 'Risk_Premium', 'Formula5']])
print(f"Ortalama: {df['Formula5'].mean():.1f}")
print(f"Standart Sapma: {df['Formula5'].std():.1f}")
print()

# En iyi formülü bul (en düşük standart sapma)
formulas = ['Formula1', 'Formula2', 'Formula3', 'Formula4', 'Formula5']
std_devs = [df[formula].std() for formula in formulas]

print("=== STANDART SAPMA KARŞILAŞTIRMASI ===")
for i, formula in enumerate(formulas):
    print(f"{formula}: {std_devs[i]:.1f}")

best_formula = formulas[np.argmin(std_devs)]
print(f"\nEn iyi formül: {best_formula} (En düşük standart sapma)")
print(f"Değer: {df[best_formula].mean():.1f} ± {df[best_formula].std():.1f}")

# Gerçek verilerle test
print("\n=== GERÇEK VERİLERLE TEST ===")
print("nekheldkuponlu.csv'den örnekler:")

# Gerçek veriyi yükle
try:
    real_df = pd.read_csv('current_yield_analysis_final.csv')
    sample = real_df.head(5)
    
    print("Örnek hisseler:")
    for _, row in sample.iterrows():
        current_yield = row['CURRENT_YIELD']
        solidity = row['SOLIDITY_FROM_YIELD']
        risk_premium = row['RISK_PREMIUM']
        
        formula1 = solidity * current_yield
        formula2 = solidity / current_yield
        formula3 = (solidity * current_yield) / risk_premium if risk_premium != 0 else 0
        
        print(f"{row['PREF IBKR']}: CY={current_yield:.1f}%, Solidity={solidity:.1f}")
        print(f"  Formula1: {formula1:.1f}")
        print(f"  Formula2: {formula2:.1f}")
        print(f"  Formula3: {formula3:.1f}")
        print()
        
except FileNotFoundError:
    print("current_yield_analysis_final.csv dosyası bulunamadı.") 