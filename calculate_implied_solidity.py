import pandas as pd
import numpy as np

# Risk Premium aralığı: 0.8% ile 7% arası
RISK_PREMIUM_MIN = 0.8
RISK_PREMIUM_MAX = 7.0
TARGET_CONSTANT = 90

# CSV dosyasını oku
df = pd.read_csv('nekheldkuponlu.csv')

# Gerekli sütunları sayısal hale getir
df['COUPON'] = df['COUPON'].str.replace('%', '').astype(float) / 100
df['Div adj.price'] = pd.to_numeric(df['Div adj.price'], errors='coerce')
df['TIME TO DIV'] = pd.to_numeric(df['TIME TO DIV'], errors='coerce')

# Current yield hesapla
df['CURRENT_YIELD'] = (25 / df['Div adj.price']) * df['COUPON'] * 100

# Risk free rate (4.5% varsayalım)
RISK_FREE_RATE = 4.5

# Risk primi hesapla
df['RISK_PREMIUM'] = df['CURRENT_YIELD'] - RISK_FREE_RATE

# Risk premium'u normalize et (0.8-7.0 arası)
df['RISK_PREMIUM_NORM'] = np.clip(df['RISK_PREMIUM'], RISK_PREMIUM_MIN, RISK_PREMIUM_MAX)

# Implied solidity hesapla
df['IMPLIED_SOLIDITY'] = TARGET_CONSTANT / df['RISK_PREMIUM_NORM']

# Test: Implied Solidity × Risk Premium = 90
df['TEST_RESULT'] = df['IMPLIED_SOLIDITY'] * df['RISK_PREMIUM_NORM']

print("=== IMPLIED SOLIDITY HESAPLAMA ===")
print(f"Sabit Değer: {TARGET_CONSTANT}")
print(f"Risk Premium Aralığı: {RISK_PREMIUM_MIN}% - {RISK_PREMIUM_MAX}%")
print(f"Toplam hisse sayısı: {len(df)}")
print()

# En yüksek implied solidity (en güvenli)
print("=== EN YÜKSEK IMPLIED SOLIDITY (EN GÜVENLİ) ===")
highest_solidity = df.nlargest(10, 'IMPLIED_SOLIDITY')
for _, stock in highest_solidity.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Current Yield: {stock['CURRENT_YIELD']:.2f}%")
    print(f"  Risk Premium: {stock['RISK_PREMIUM']:.2f}% → {stock['RISK_PREMIUM_NORM']:.2f}%")
    print(f"  Implied Solidity: {stock['IMPLIED_SOLIDITY']:.1f}")
    print(f"  Test Result: {stock['TEST_RESULT']:.1f}")
    print()

# En düşük implied solidity (en riskli)
print("=== EN DÜŞÜK IMPLIED SOLIDITY (EN RİSKLİ) ===")
lowest_solidity = df.nsmallest(10, 'IMPLIED_SOLIDITY')
for _, stock in lowest_solidity.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Current Yield: {stock['CURRENT_YIELD']:.2f}%")
    print(f"  Risk Premium: {stock['RISK_PREMIUM']:.2f}% → {stock['RISK_PREMIUM_NORM']:.2f}%")
    print(f"  Implied Solidity: {stock['IMPLIED_SOLIDITY']:.1f}")
    print(f"  Test Result: {stock['TEST_RESULT']:.1f}")
    print()

# İstatistikler
print("=== İSTATİSTİKLER ===")
print(f"Ortalama Implied Solidity: {df['IMPLIED_SOLIDITY'].mean():.1f}")
print(f"En yüksek Implied Solidity: {df['IMPLIED_SOLIDITY'].max():.1f}")
print(f"En düşük Implied Solidity: {df['IMPLIED_SOLIDITY'].min():.1f}")
print(f"Standart Sapma: {df['IMPLIED_SOLIDITY'].std():.1f}")
print()
print(f"Ortalama Test Sonucu: {df['TEST_RESULT'].mean():.1f}")
print(f"Test Sonucu Standart Sapma: {df['TEST_RESULT'].std():.1f}")

# Sonuçları CSV'ye kaydet
result_df = df[['PREF IBKR', 'CMON', 'CURRENT_YIELD', 'RISK_PREMIUM', 
                'RISK_PREMIUM_NORM', 'IMPLIED_SOLIDITY', 'TEST_RESULT']].copy()
result_df.to_csv('implied_solidity_results.csv', index=False)
print(f"\nSonuçlar 'implied_solidity_results.csv' dosyasına kaydedildi.")

# Örnek verilerle formül arayışı
print("\n=== FORMÜL ARAMA İÇİN ÖRNEK VERİLER ===")
sample = df.head(5)
for _, stock in sample.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied Solidity: {stock['IMPLIED_SOLIDITY']:.1f}")
    print(f"  Market Cap: {stock.get('COM_MKTCAP', 'N/A')}")
    print(f"  Credit Score: {stock.get('CRDT_SCORE', 'N/A')}")
    print(f"  Last Price: {stock.get('Last Price', 'N/A')}")
    print(f"  52W Low: {stock.get('COM_52W_LOW', 'N/A')}")
    print(f"  52W High: {stock.get('COM_52W_HIGH', 'N/A')}")
    print() 