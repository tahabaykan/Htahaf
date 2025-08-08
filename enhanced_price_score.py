import pandas as pd
import numpy as np

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

print("=== GELİŞMİŞ PRICE SCORE FORMÜLÜ ===")
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
        if covid_pre_performance > 0.5:  # %50+ yukarıda
            score += 5
        elif covid_pre_performance > 0.2:  # %20+ yukarıda
            score += 4
        elif covid_pre_performance > 0:  # Pozitif
            score += 3
        elif covid_pre_performance > -0.2:  # %20'den az düşüş
            score += 2
        elif covid_pre_performance > -0.5:  # %50'den az düşüş
            score += 1
        # Negatif değerler 0 puan
    
    # 2. COVID sonrası toparlanma (0-5 puan)
    if mar_2020 > 0:
        covid_recovery = (current_price - mar_2020) / mar_2020
        if covid_recovery > 2.0:  # %200+ toparlanma
            score += 5
        elif covid_recovery > 1.5:  # %150+ toparlanma
            score += 4
        elif covid_recovery > 1.0:  # %100+ toparlanma
            score += 3
        elif covid_recovery > 0.5:  # %50+ toparlanma
            score += 2
        elif covid_recovery > 0:  # Pozitif toparlanma
            score += 1
    
    # 3. 52W performansı (0-4 puan)
    if high_52w > low_52w:
        position_52w = (current_price - low_52w) / (high_52w - low_52w)
        if position_52w > 0.8:  # High'a çok yakın
            score += 4
        elif position_52w > 0.6:  # High'a yakın
            score += 3
        elif position_52w > 0.4:  # Orta
            score += 2
        elif position_52w > 0.2:  # Low'a yakın
            score += 1
    
    # 4. 5Y performansı (0-3 puan)
    if high_5y > low_5y:
        position_5y = (current_price - low_5y) / (high_5y - low_5y)
        if position_5y > 0.7:  # 5Y high'a yakın
            score += 3
        elif position_5y > 0.5:  # 5Y orta
            score += 2
        elif position_5y > 0.3:  # 5Y low'a yakın
            score += 1
    
    # 5. Kısa vadeli momentum (0-3 puan)
    if price_3m > 0 and price_6m > 0:
        # 3M ve 6M fiyatlara göre momentum
        momentum_3m = (current_price - price_3m) / price_3m
        momentum_6m = (current_price - price_6m) / price_6m
        
        if momentum_3m > 0.1 and momentum_6m > 0.2:  # Güçlü momentum
            score += 3
        elif momentum_3m > 0.05 and momentum_6m > 0.1:  # Orta momentum
            score += 2
        elif momentum_3m > 0 and momentum_6m > 0:  # Pozitif momentum
            score += 1
    
    return np.clip(score, 0, max_score)

def calculate_enhanced_solidity(row):
    credit_score = row['CRDT_SCORE']
    market_cap = row['COM_MKTCAP']
    
    # Market cap bazlı güvenlik (0-20 arası)
    market_cap_norm = np.clip(market_cap / 1000, 1, 1000)
    market_cap_score = np.log10(market_cap_norm) * 6
    
    # Credit score bazlı güvenlik (0-20 arası)
    credit_score_norm = np.clip(credit_score, 0, 15)
    credit_score_calc = credit_score_norm * 1.33
    
    # Gelişmiş price score (0-20 arası)
    price_score = calculate_enhanced_price_score(row)
    
    # Ek güvenlik faktörü (0-15 arası)
    bonus = 0
    if market_cap > 50000:  # 50B+ market cap
        bonus += 5
    if credit_score > 12:
        bonus += 5
    if price_score > 15:  # Yüksek price score
        bonus += 5
    
    # Formül: 20 + Market Cap + Credit Score + Enhanced Price Score + Bonus
    solidity = 20 + market_cap_score + credit_score_calc + price_score + bonus
    return np.clip(solidity, 20, 80)

# Formülleri uygula
df['ENHANCED_PRICE_SCORE'] = df.apply(calculate_enhanced_price_score, axis=1)
df['ENHANCED_SOLIDITY'] = df.apply(calculate_enhanced_solidity, axis=1)
df['ERROR'] = abs(df['ENHANCED_SOLIDITY'] - df['IMPLIED_SOLIDITY'])

print("=== GELİŞMİŞ FORMÜL PERFORMANSI ===")
print(f"Ortalama Hata: {df['ERROR'].mean():.1f}")
print(f"Medyan Hata: {df['ERROR'].median():.1f}")
print(f"Standart Sapma: {df['ERROR'].std():.1f}")
print()

# Price score analizi
print("=== PRICE SCORE ANALİZİ ===")
print(f"Ortalama Price Score: {df['ENHANCED_PRICE_SCORE'].mean():.1f}")
print(f"En Yüksek Price Score: {df['ENHANCED_PRICE_SCORE'].max():.1f}")
print(f"En Düşük Price Score: {df['ENHANCED_PRICE_SCORE'].min():.1f}")
print()

# En yüksek price score'lar
print("=== EN YÜKSEK PRICE SCORE'LAR ===")
top_price_scores = df.nlargest(10, 'ENHANCED_PRICE_SCORE')
for _, stock in top_price_scores.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Price Score: {stock['ENHANCED_PRICE_SCORE']:.1f}")
    print(f"  Current: {stock['COM_LAST_PRICE']:.2f}, Feb2020: {stock['COM_FEB2020_PRICE']:.2f}, Mar2020: {stock['COM_MAR2020_PRICE']:.2f}")
    print(f"  52W: {stock['COM_52W_LOW']:.2f}-{stock['COM_52W_HIGH']:.2f}")
    print()

# En düşük price score'lar
print("=== EN DÜŞÜK PRICE SCORE'LAR ===")
bottom_price_scores = df.nsmallest(10, 'ENHANCED_PRICE_SCORE')
for _, stock in bottom_price_scores.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Price Score: {stock['ENHANCED_PRICE_SCORE']:.1f}")
    print(f"  Current: {stock['COM_LAST_PRICE']:.2f}, Feb2020: {stock['COM_FEB2020_PRICE']:.2f}, Mar2020: {stock['COM_MAR2020_PRICE']:.2f}")
    print(f"  52W: {stock['COM_52W_LOW']:.2f}-{stock['COM_52W_HIGH']:.2f}")
    print()

# En iyi uyumlar
print("=== EN İYİ UYUMLAR (Hata < 3) ===")
best_matches = df[df['ERROR'] < 3].sort_values('ERROR')
for _, stock in best_matches.head(10).iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Enhanced: {stock['ENHANCED_SOLIDITY']:.1f}")
    print(f"  Price Score: {stock['ENHANCED_PRICE_SCORE']:.1f}")
    print()

# Sonuçları kaydet
result_df = df[['PREF IBKR', 'CMON', 'Sector', 'IMPLIED_SOLIDITY', 'ENHANCED_SOLIDITY', 
                'ENHANCED_PRICE_SCORE', 'ERROR', 'CRDT_SCORE', 'COM_MKTCAP', 
                'COM_LAST_PRICE', 'COM_FEB2020_PRICE', 'COM_MAR2020_PRICE',
                'COM_52W_LOW', 'COM_52W_HIGH', 'COM_6M_PRICE', 'COM_3M_PRICE',
                'COM_5Y_LOW', 'COM_5Y_HIGH']].copy()
result_df.to_csv('enhanced_solidity_results.csv', index=False)
print(f"Sonuçlar 'enhanced_solidity_results.csv' dosyasına kaydedildi.")

# Formül özeti
print("=== GELİŞMİŞ FORMÜL ÖZETİ ===")
print("Enhanced Price Score = COVID Pre-Performance + COVID Recovery + 52W Position + 5Y Position + Momentum")
print("COVID Pre-Performance: Current vs Feb2020 (%50+ = 5p, %20+ = 4p, pozitif = 3p, vs.)")
print("COVID Recovery: Current vs Mar2020 (%200+ = 5p, %150+ = 4p, %100+ = 3p, vs.)")
print("52W Position: Current position in 52W range (0.8+ = 4p, 0.6+ = 3p, vs.)")
print("5Y Position: Current position in 5Y range (0.7+ = 3p, 0.5+ = 2p, vs.)")
print("Momentum: 3M and 6M price momentum (güçlü = 3p, orta = 2p, pozitif = 1p)")
print()
print("Enhanced Solidity = 20 + Market Cap Score + Credit Score + Enhanced Price Score + Bonus") 