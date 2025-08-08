import pandas as pd
import numpy as np

# CSV dosyasını oku
df = pd.read_csv('neknottitrekhc.csv')

# Gerekli sütunları sayısal hale getir
df['COUPON'] = df['COUPON'].str.replace('%', '').astype(float) / 100
df['Div adj.price'] = pd.to_numeric(df['Div adj.price'], errors='coerce')
df['TIME TO DIV'] = pd.to_numeric(df['TIME TO DIV'], errors='coerce')

# Current yield hesapla: (25/div adj price) * coupon rate
df['CURRENT_YIELD'] = (25 / df['Div adj.price']) * df['COUPON'] * 100

# Risk free rate (4.5% varsayalım)
RISK_FREE_RATE = 4.5

# Risk primi hesapla
df['RISK_PREMIUM'] = df['CURRENT_YIELD'] - RISK_FREE_RATE

# Risk primine göre solidity score hesapla (risk primi düşük = yüksek solidity)
# Risk primi -5% ile 15% arasında normalize et
df['RISK_PREMIUM_NORM'] = np.clip(df['RISK_PREMIUM'], -5, 15)
df['SOLIDITY_FROM_YIELD'] = 100 - ((df['RISK_PREMIUM_NORM'] + 5) / 20) * 100

# Sonuçları göster
print("=== NEKNOTTITREKHC.CSV - CURRENT YIELD ANALİZİ ===")
print(f"Toplam hisse sayısı: {len(df)}")

# En düşük current yield (en yüksek solidity)
print("\n=== EN DÜŞÜK CURRENT YIELD (EN YÜKSEK SOLIDITY) ===")
lowest_yield = df.nsmallest(10, 'CURRENT_YIELD')
for _, stock in lowest_yield.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Current Yield: {stock['CURRENT_YIELD']:.2f}%")
    print(f"  Risk Premium: {stock['RISK_PREMIUM']:.2f}%")
    print(f"  Solidity from Yield: {stock['SOLIDITY_FROM_YIELD']:.1f}")
    print(f"  Div Adj Price: ${stock['Div adj.price']:.2f}")
    print(f"  Coupon Rate: {stock['COUPON']*100:.1f}%")
    print()

# En yüksek current yield (en düşük solidity)
print("\n=== EN YÜKSEK CURRENT YIELD (EN DÜŞÜK SOLIDITY) ===")
highest_yield = df.nlargest(10, 'CURRENT_YIELD')
for _, stock in highest_yield.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Current Yield: {stock['CURRENT_YIELD']:.2f}%")
    print(f"  Risk Premium: {stock['RISK_PREMIUM']:.2f}%")
    print(f"  Solidity from Yield: {stock['SOLIDITY_FROM_YIELD']:.1f}")
    print(f"  Div Adj Price: ${stock['Div adj.price']:.2f}")
    print(f"  Coupon Rate: {stock['COUPON']*100:.1f}%")
    print()

# İstatistikler
print("=== İSTATİSTİKLER ===")
print(f"Ortalama Current Yield: {df['CURRENT_YIELD'].mean():.2f}%")
print(f"Medyan Current Yield: {df['CURRENT_YIELD'].median():.2f}%")
print(f"En düşük Current Yield: {df['CURRENT_YIELD'].min():.2f}%")
print(f"En yüksek Current Yield: {df['CURRENT_YIELD'].max():.2f}%")
print()
print(f"Ortalama Risk Premium: {df['RISK_PREMIUM'].mean():.2f}%")
print(f"En düşük Risk Premium: {df['RISK_PREMIUM'].min():.2f}%")
print(f"En yüksek Risk Premium: {df['RISK_PREMIUM'].max():.2f}%")
print()
print(f"Ortalama Solidity from Yield: {df['SOLIDITY_FROM_YIELD'].mean():.1f}")
print(f"En yüksek Solidity from Yield: {df['SOLIDITY_FROM_YIELD'].max():.1f}")
print(f"En düşük Solidity from Yield: {df['SOLIDITY_FROM_YIELD'].min():.1f}")

# Sonuçları CSV'ye kaydet
result_df = df[['PREF IBKR', 'CMON', 'COUPON', 'Div adj.price', 'TIME TO DIV', 
                'CURRENT_YIELD', 'RISK_PREMIUM', 'SOLIDITY_FROM_YIELD']].copy()
result_df.to_csv('current_yield_nottitrekhc.csv', index=False)
print(f"\nSonuçlar 'current_yield_nottitrekhc.csv' dosyasına kaydedildi.") 