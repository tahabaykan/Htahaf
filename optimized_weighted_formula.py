import pandas as pd
import numpy as np
from itertools import product

# Implied solidity sonuçlarını yükle
implied_df = pd.read_csv('implied_solidity_results.csv')

# Ana veriyi yükle
main_df = pd.read_csv('comekheldkuponlu.csv')

# Verileri birleştir
df = pd.merge(main_df, implied_df[['PREF IBKR', 'IMPLIED_SOLIDITY']], on='PREF IBKR', how='left')

# Gerekli sütunları sayısal hale getir
df['CRDT_SCORE'] = pd.to_numeric(df['CRDT_SCORE'], errors='coerce')
df['COM_LAST_PRICE'] = pd.to_numeric(df['COM_LAST_PRICE'], errors='coerce')
df['COM_MKTCAP'] = pd.to_numeric(df['COM_MKTCAP'], errors='coerce')
df['COM_52W_LOW'] = pd.to_numeric(df['COM_52W_LOW'], errors='coerce')
df['COM_52W_HIGH'] = pd.to_numeric(df['COM_52W_HIGH'], errors='coerce')
df['COM_6M_PRICE'] = pd.to_numeric(df['COM_6M_PRICE'], errors='coerce')
df['COM_3M_PRICE'] = pd.to_numeric(df['COM_3M_PRICE'], errors='coerce')
df['COM_5Y_LOW'] = pd.to_numeric(df['COM_5Y_LOW'], errors='coerce')
df['COM_5Y_HIGH'] = pd.to_numeric(df['COM_5Y_HIGH'], errors='coerce')
df['COM_FEB2020_PRICE'] = pd.to_numeric(df['COM_FEB2020_PRICE'], errors='coerce')
df['COM_MAR2020_PRICE'] = pd.to_numeric(df['COM_MAR2020_PRICE'], errors='coerce')

# Eksik verileri doldur
df['CRDT_SCORE'] = df['CRDT_SCORE'].fillna(10)
df['COM_LAST_PRICE'] = df['COM_LAST_PRICE'].fillna(20)
df['COM_MKTCAP'] = df['COM_MKTCAP'].fillna(10000)
df['COM_52W_LOW'] = df['COM_52W_LOW'].fillna(15)
df['COM_52W_HIGH'] = df['COM_52W_HIGH'].fillna(25)
df['COM_6M_PRICE'] = df['COM_6M_PRICE'].fillna(18)
df['COM_3M_PRICE'] = df['COM_3M_PRICE'].fillna(19)
df['COM_5Y_LOW'] = df['COM_5Y_LOW'].fillna(12)
df['COM_5Y_HIGH'] = df['COM_5Y_HIGH'].fillna(28)
df['COM_FEB2020_PRICE'] = df['COM_FEB2020_PRICE'].fillna(22)
df['COM_MAR2020_PRICE'] = df['COM_MAR2020_PRICE'].fillna(16)

print("=== AĞIRLIKLI FORMÜL OPTİMİZASYONU ===")
print(f"Toplam hisse sayısı: {len(df)}")
print()

def calculate_enhanced_price_score(row):
    current_price = row['COM_LAST_PRICE']
    feb_2020 = row['COM_FEB2020_PRICE']
    mar_2020 = row['COM_MAR2020_PRICE']
    low_52w = row['COM_52W_LOW']
    high_52w = row['COM_52W_HIGH']
    price_6m = row['COM_6M_PRICE']
    price_3m = row['COM_3M_PRICE']
    low_5y = row['COM_5Y_LOW']
    high_5y = row['COM_5Y_HIGH']
    
    score = 0
    max_score = 20
    
    # 1. COVID öncesi performans (0-5 puan)
    if feb_2020 > 0:
        covid_pre_performance = (current_price - feb_2020) / feb_2020
        if covid_pre_performance > 0.5:
            score += 5
        elif covid_pre_performance > 0.2:
            score += 4
        elif covid_pre_performance > 0:
            score += 3
        elif covid_pre_performance > -0.2:
            score += 2
        elif covid_pre_performance > -0.5:
            score += 1
    
    # 2. COVID sonrası toparlanma (0-5 puan)
    if mar_2020 > 0:
        covid_recovery = (current_price - mar_2020) / mar_2020
        if covid_recovery > 2.0:
            score += 5
        elif covid_recovery > 1.5:
            score += 4
        elif covid_recovery > 1.0:
            score += 3
        elif covid_recovery > 0.5:
            score += 2
        elif covid_recovery > 0:
            score += 1
    
    # 3. 52W performansı (0-4 puan)
    if high_52w > low_52w:
        position_52w = (current_price - low_52w) / (high_52w - low_52w)
        if position_52w > 0.8:
            score += 4
        elif position_52w > 0.6:
            score += 3
        elif position_52w > 0.4:
            score += 2
        elif position_52w > 0.2:
            score += 1
    
    # 4. 5Y performansı (0-3 puan)
    if high_5y > low_5y:
        position_5y = (current_price - low_5y) / (high_5y - low_5y)
        if position_5y > 0.7:
            score += 3
        elif position_5y > 0.5:
            score += 2
        elif position_5y > 0.3:
            score += 1
    
    # 5. Kısa vadeli momentum (0-3 puan)
    if price_3m > 0 and price_6m > 0:
        momentum_3m = (current_price - price_3m) / price_3m
        momentum_6m = (current_price - price_6m) / price_6m
        
        if momentum_3m > 0.1 and momentum_6m > 0.2:
            score += 3
        elif momentum_3m > 0.05 and momentum_6m > 0.1:
            score += 2
        elif momentum_3m > 0 and momentum_6m > 0:
            score += 1
    
    return np.clip(score, 0, max_score)

# Price score'ları hesapla
df['PRICE_SCORE'] = df.apply(calculate_enhanced_price_score, axis=1)

# Market cap ve credit score'ları normalize et
df['MARKET_CAP_NORM'] = np.log10(np.clip(df['COM_MKTCAP'] / 1000, 1, 1000)) * 10
df['CREDIT_SCORE_NORM'] = df['CRDT_SCORE'] * 2

print("=== NORMALİZE EDİLMİŞ DEĞERLER ===")
print(f"Market Cap Norm - Ortalama: {df['MARKET_CAP_NORM'].mean():.1f}, Min: {df['MARKET_CAP_NORM'].min():.1f}, Max: {df['MARKET_CAP_NORM'].max():.1f}")
print(f"Credit Score Norm - Ortalama: {df['CREDIT_SCORE_NORM'].mean():.1f}, Min: {df['CREDIT_SCORE_NORM'].min():.1f}, Max: {df['CREDIT_SCORE_NORM'].max():.1f}")
print(f"Price Score - Ortalama: {df['PRICE_SCORE'].mean():.1f}, Min: {df['PRICE_SCORE'].min():.1f}, Max: {df['PRICE_SCORE'].max():.1f}")
print()

def calculate_weighted_solidity(row, market_cap_weight, credit_weight, price_weight, base_score):
    market_cap_score = row['MARKET_CAP_NORM'] * market_cap_weight
    credit_score = row['CREDIT_SCORE_NORM'] * credit_weight
    price_score = row['PRICE_SCORE'] * price_weight
    
    solidity = base_score + market_cap_score + credit_score + price_score
    return np.clip(solidity, 20, 80)

# Ağırlık kombinasyonlarını test et
print("=== AĞIRLIK OPTİMİZASYONU ===")
best_error = float('inf')
best_weights = None
best_base = None

# Ağırlık aralıkları
market_cap_weights = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
credit_weights = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
price_weights = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
base_scores = [15, 20, 25, 30]

total_combinations = len(market_cap_weights) * len(credit_weights) * len(price_weights) * len(base_scores)
print(f"Test edilecek kombinasyon sayısı: {total_combinations}")

for market_cap_w, credit_w, price_w, base in product(market_cap_weights, credit_weights, price_weights, base_scores):
    df['TEST_SOLIDITY'] = df.apply(lambda row: calculate_weighted_solidity(row, market_cap_w, credit_w, price_w, base), axis=1)
    df['TEST_ERROR'] = abs(df['TEST_SOLIDITY'] - df['IMPLIED_SOLIDITY'])
    avg_error = df['TEST_ERROR'].mean()
    
    if avg_error < best_error:
        best_error = avg_error
        best_weights = (market_cap_w, credit_w, price_w)
        best_base = base

print(f"En iyi kombinasyon bulundu!")
print(f"Market Cap Ağırlığı: {best_weights[0]}")
print(f"Credit Score Ağırlığı: {best_weights[1]}")
print(f"Price Score Ağırlığı: {best_weights[2]}")
print(f"Base Score: {best_base}")
print(f"Ortalama Hata: {best_error:.1f}")
print()

# En iyi formülü uygula
df['OPTIMIZED_SOLIDITY'] = df.apply(lambda row: calculate_weighted_solidity(row, best_weights[0], best_weights[1], best_weights[2], best_base), axis=1)
df['FINAL_ERROR'] = abs(df['OPTIMIZED_SOLIDITY'] - df['IMPLIED_SOLIDITY'])

print("=== OPTİMİZE EDİLMİŞ FORMÜL PERFORMANSI ===")
print(f"Ortalama Hata: {df['FINAL_ERROR'].mean():.1f}")
print(f"Medyan Hata: {df['FINAL_ERROR'].median():.1f}")
print(f"Standart Sapma: {df['FINAL_ERROR'].std():.1f}")
print()

# En iyi uyumlar
print("=== EN İYİ UYUMLAR (Hata < 2) ===")
best_matches = df[df['FINAL_ERROR'] < 2].sort_values('FINAL_ERROR')
for _, stock in best_matches.head(10).iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Optimized: {stock['OPTIMIZED_SOLIDITY']:.1f}")
    print(f"  Market Cap: {stock['MARKET_CAP_NORM']:.1f}, Credit: {stock['CREDIT_SCORE_NORM']:.1f}, Price: {stock['PRICE_SCORE']:.1f}")
    print()

# En kötü uyumlar
print("=== EN KÖTÜ UYUMLAR (Hata > 10) ===")
worst_matches = df[df['FINAL_ERROR'] > 10].sort_values('FINAL_ERROR', ascending=False)
for _, stock in worst_matches.head(10).iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Optimized: {stock['OPTIMIZED_SOLIDITY']:.1f}")
    print(f"  Market Cap: {stock['MARKET_CAP_NORM']:.1f}, Credit: {stock['CREDIT_SCORE_NORM']:.1f}, Price: {stock['PRICE_SCORE']:.1f}")
    print()

# Sektör analizi
print("=== SEKTÖR ANALİZİ ===")
sector_analysis = df.groupby('Sector').agg({
    'FINAL_ERROR': ['mean', 'count'],
    'IMPLIED_SOLIDITY': 'mean',
    'OPTIMIZED_SOLIDITY': 'mean'
}).round(1)
print(sector_analysis)
print()

# Sonuçları kaydet
result_df = df[['PREF IBKR', 'CMON', 'Sector', 'IMPLIED_SOLIDITY', 'OPTIMIZED_SOLIDITY', 
                'FINAL_ERROR', 'MARKET_CAP_NORM', 'CREDIT_SCORE_NORM', 'PRICE_SCORE',
                'CRDT_SCORE', 'COM_MKTCAP', 'COM_LAST_PRICE']].copy()
result_df.to_csv('optimized_solidity_results.csv', index=False)
print(f"Sonuçlar 'optimized_solidity_results.csv' dosyasına kaydedildi.")

# Formül özeti
print("=== OPTİMİZE EDİLMİŞ FORMÜL ÖZETİ ===")
print(f"Optimized Solidity = {best_base} + (Market Cap Norm × {best_weights[0]}) + (Credit Score Norm × {best_weights[1]}) + (Price Score × {best_weights[2]})")
print(f"Market Cap Norm = log10(market_cap/1000) × 10")
print(f"Credit Score Norm = credit_score × 2")
print(f"Price Score = Enhanced price score (0-20)")
print()
print(f"Bu formül implied solidity değerlerine ortalama {best_error:.1f} hata ile yaklaşıyor.") 