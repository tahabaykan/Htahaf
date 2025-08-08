import pandas as pd
import numpy as np

# CSV dosyasını oku
df = pd.read_csv('sldekheldkuponlu.csv')

# Gerekli sütunları sayısal hale getir
df['COUPON'] = df['COUPON'].str.replace('%', '').astype(float) / 100
df['Aug2022_Price'] = pd.to_numeric(df['Aug2022_Price'], errors='coerce')
df['Oct19_Price'] = pd.to_numeric(df['Oct19_Price'], errors='coerce')

# Current yield hesapla: (25/div adj price) * coupon rate
df['CURRENT_YIELD'] = (25 / df['Oct19_Price']) * df['COUPON'] * 100

# Risk free rate (4.5% varsayalım)
RISK_FREE_RATE = 4.5

# Risk primi hesapla
df['RISK_PREMIUM'] = df['CURRENT_YIELD'] - RISK_FREE_RATE

# Risk primine göre solidity score hesapla (risk primi düşük = yüksek solidity)
# Risk primi 0-10% arasında normalize et
df['RISK_PREMIUM_NORM'] = np.clip(df['RISK_PREMIUM'], 0, 10)
df['SOLIDITY_FROM_YIELD'] = 100 - (df['RISK_PREMIUM_NORM'] * 10)

print("=== CURRENT YIELD ANALİZİ ===")
print(f"Risk Free Rate: {RISK_FREE_RATE}%")
print(f"Toplam hisse sayısı: {len(df)}")

print("\n=== EN DÜŞÜK CURRENT YIELD'LAR (En Yüksek Solidity) ===")
df_sorted_yield = df.sort_values('CURRENT_YIELD')
print(df_sorted_yield[['PREF IBKR', 'CMON', 'COUPON', 'Oct19_Price', 'CURRENT_YIELD', 'RISK_PREMIUM', 'SOLIDITY_FROM_YIELD']].head(15))

print("\n=== EN YÜKSEK CURRENT YIELD'LAR (En Düşük Solidity) ===")
print(df_sorted_yield[['PREF IBKR', 'CMON', 'COUPON', 'Oct19_Price', 'CURRENT_YIELD', 'RISK_PREMIUM', 'SOLIDITY_FROM_YIELD']].tail(15))

print("\n=== CURRENT YIELD İSTATİSTİKLERİ ===")
print(f"En düşük current yield: {df['CURRENT_YIELD'].min():.2f}%")
print(f"En yüksek current yield: {df['CURRENT_YIELD'].max():.2f}%")
print(f"Ortalama current yield: {df['CURRENT_YIELD'].mean():.2f}%")
print(f"Medyan current yield: {df['CURRENT_YIELD'].median():.2f}%")

print("\n=== RİSK PRİMİ İSTATİSTİKLERİ ===")
print(f"En düşük risk primi: {df['RISK_PREMIUM'].min():.2f}%")
print(f"En yüksek risk primi: {df['RISK_PREMIUM'].max():.2f}%")
print(f"Ortalama risk primi: {df['RISK_PREMIUM'].mean():.2f}%")

print("\n=== MEVCUT vs YIELD-BASED SOLIDITY KARŞILAŞTIRMASI ===")
comparison = df[['PREF IBKR', 'CMON', 'SOLIDITY_SCORE', 'SOLIDITY_FROM_YIELD', 'CURRENT_YIELD', 'RISK_PREMIUM']].copy()
comparison['DIFFERENCE'] = comparison['SOLIDITY_FROM_YIELD'] - comparison['SOLIDITY_SCORE']
comparison_sorted = comparison.sort_values('DIFFERENCE', ascending=False)

print("En büyük fark (Yield-based daha yüksek):")
print(comparison_sorted.head(10))

print("\nEn büyük fark (Mevcut daha yüksek):")
print(comparison_sorted.tail(10))

# Sonuçları CSV'ye kaydet
df.to_csv('current_yield_analysis.csv', index=False)
print(f"\nSonuçlar 'current_yield_analysis.csv' dosyasına kaydedildi.") 