import pandas as pd
import numpy as np

# Implied solidity sonuçlarını yükle
implied_df = pd.read_csv('implied_solidity_results.csv')

# Ana veriyi yükle (doğru dosya)
main_df = pd.read_csv('comekheldkuponlu.csv')

# Verileri birleştir
df = pd.merge(main_df, implied_df[['PREF IBKR', 'IMPLIED_SOLIDITY']], on='PREF IBKR', how='left')

# Gerekli sütunları sayısal hale getir
df['CRDT_SCORE'] = pd.to_numeric(df['CRDT_SCORE'], errors='coerce')
df['COM_LAST_PRICE'] = pd.to_numeric(df['COM_LAST_PRICE'], errors='coerce')
df['COM_MKTCAP'] = pd.to_numeric(df['COM_MKTCAP'], errors='coerce')
df['COM_52W_LOW'] = pd.to_numeric(df['COM_52W_LOW'], errors='coerce')
df['COM_52W_HIGH'] = pd.to_numeric(df['COM_52W_HIGH'], errors='coerce')

# Eksik verileri doldur
df['CRDT_SCORE'] = df['CRDT_SCORE'].fillna(10)  # Varsayılan credit score
df['COM_LAST_PRICE'] = df['COM_LAST_PRICE'].fillna(20)     # Varsayılan fiyat
df['COM_MKTCAP'] = df['COM_MKTCAP'].fillna(10000) # Varsayılan market cap
df['COM_52W_LOW'] = df['COM_52W_LOW'].fillna(15)
df['COM_52W_HIGH'] = df['COM_52W_HIGH'].fillna(25)

print("=== SOLIDITY FORMÜL GELİŞTİRME ===")
print(f"Toplam hisse sayısı: {len(df)}")
print()

# Formül 1: Market Cap + Credit Score + Fiyat Performansı
def formula1(row):
    credit_score = row['CRDT_SCORE']
    market_cap = row['COM_MKTCAP']
    last_price = row['COM_LAST_PRICE']
    low_52w = row['COM_52W_LOW']
    high_52w = row['COM_52W_HIGH']
    
    # Market cap score (0-25 arası)
    # Büyük market cap = daha güvenli
    market_cap_norm = np.clip(market_cap / 1000, 1, 1000)
    market_cap_score = np.log10(market_cap_norm) * 8
    
    # Credit score (0-25 arası)
    # Yüksek credit score = daha güvenli
    credit_score_norm = np.clip(credit_score, 0, 15)
    credit_score_calc = credit_score_norm * 1.67
    
    # Fiyat performansı score (0-25 arası)
    # 52W high'a yakın = daha güvenli, low'a yakın = daha riskli
    if high_52w > low_52w:
        price_position = (last_price - low_52w) / (high_52w - low_52w)
        price_score = price_position * 25
    else:
        price_score = 12.5  # Orta değer
    
    # Formül: 25 + Market Cap + Credit Score + Price Score
    solidity = 25 + market_cap_score + credit_score_calc + price_score
    return np.clip(solidity, 25, 75)

# Formül 2: Karma formül (daha detaylı)
def formula2(row):
    credit_score = row['CRDT_SCORE']
    market_cap = row['COM_MKTCAP']
    last_price = row['COM_LAST_PRICE']
    low_52w = row['COM_52W_LOW']
    high_52w = row['COM_52W_HIGH']
    
    # Market cap bazlı güvenlik (0-20 arası)
    market_cap_norm = np.clip(market_cap / 1000, 1, 1000)
    market_cap_score = np.log10(market_cap_norm) * 6
    
    # Credit score bazlı güvenlik (0-20 arası)
    credit_score_norm = np.clip(credit_score, 0, 15)
    credit_score_calc = credit_score_norm * 1.33
    
    # Fiyat performansı (0-20 arası)
    if high_52w > low_52w:
        price_position = (last_price - low_52w) / (high_52w - low_52w)
        price_score = price_position * 20
    else:
        price_score = 10
    
    # Ek güvenlik faktörü (0-15 arası)
    # Market cap büyükse ve credit score yüksekse bonus
    bonus = 0
    if market_cap > 50000:  # 50B+ market cap
        bonus += 5
    if credit_score > 12:
        bonus += 5
    if price_position > 0.7:  # 52W high'a yakın
        bonus += 5
    
    # Formül: 20 + Market Cap + Credit Score + Price Score + Bonus
    solidity = 20 + market_cap_score + credit_score_calc + price_score + bonus
    return np.clip(solidity, 20, 80)

# Formül 3: Basit ama etkili formül
def formula3(row):
    credit_score = row['CRDT_SCORE']
    market_cap = row['COM_MKTCAP']
    last_price = row['COM_LAST_PRICE']
    low_52w = row['COM_52W_LOW']
    high_52w = row['COM_52W_HIGH']
    
    # Market cap score (0-30 arası)
    market_cap_norm = np.clip(market_cap / 1000, 1, 1000)
    market_cap_score = np.log10(market_cap_norm) * 10
    
    # Credit score (0-25 arası)
    credit_score_norm = np.clip(credit_score, 0, 15)
    credit_score_calc = credit_score_norm * 1.67
    
    # Fiyat performansı (0-25 arası)
    if high_52w > low_52w:
        price_position = (last_price - low_52w) / (high_52w - low_52w)
        price_score = price_position * 25
    else:
        price_score = 12.5
    
    # Formül: 20 + Market Cap + Credit Score + Price Score
    solidity = 20 + market_cap_score + credit_score_calc + price_score
    return np.clip(solidity, 20, 80)

# Formülleri uygula
df['FORMULA1_SOLIDITY'] = df.apply(formula1, axis=1)
df['FORMULA2_SOLIDITY'] = df.apply(formula2, axis=1)
df['FORMULA3_SOLIDITY'] = df.apply(formula3, axis=1)

# Hata hesapla
df['ERROR1'] = abs(df['FORMULA1_SOLIDITY'] - df['IMPLIED_SOLIDITY'])
df['ERROR2'] = abs(df['FORMULA2_SOLIDITY'] - df['IMPLIED_SOLIDITY'])
df['ERROR3'] = abs(df['FORMULA3_SOLIDITY'] - df['IMPLIED_SOLIDITY'])

print("=== FORMÜL KARŞILAŞTIRMASI ===")
print(f"Formül 1 Ortalama Hata: {df['ERROR1'].mean():.1f}")
print(f"Formül 2 Ortalama Hata: {df['ERROR2'].mean():.1f}")
print(f"Formül 3 Ortalama Hata: {df['ERROR3'].mean():.1f}")
print()

# En iyi formülü bul
best_formula = 'FORMULA1_SOLIDITY' if df['ERROR1'].mean() <= min(df['ERROR1'].mean(), df['ERROR2'].mean(), df['ERROR3'].mean()) else \
               'FORMULA2_SOLIDITY' if df['ERROR2'].mean() <= min(df['ERROR1'].mean(), df['ERROR2'].mean(), df['ERROR3'].mean()) else \
               'FORMULA3_SOLIDITY'

print(f"En iyi formül: {best_formula}")
print()

# Örnek sonuçlar
print("=== ÖRNEK SONUÇLAR ===")
sample = df.head(10)
for _, stock in sample.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied Solidity: {stock['IMPLIED_SOLIDITY']:.1f}")
    print(f"  Formula 1: {stock['FORMULA1_SOLIDITY']:.1f} (Hata: {stock['ERROR1']:.1f})")
    print(f"  Formula 2: {stock['FORMULA2_SOLIDITY']:.1f} (Hata: {stock['ERROR2']:.1f})")
    print(f"  Formula 3: {stock['FORMULA3_SOLIDITY']:.1f} (Hata: {stock['ERROR3']:.1f})")
    print(f"  Credit Score: {stock['CRDT_SCORE']:.1f}")
    print(f"  Market Cap: {stock['COM_MKTCAP']:.0f}")
    print(f"  Last Price: {stock['COM_LAST_PRICE']:.2f}")
    print(f"  52W Range: {stock['COM_52W_LOW']:.2f} - {stock['COM_52W_HIGH']:.2f}")
    print()

# En iyi ve en kötü örnekler
print("=== EN İYİ UYUMLAR ===")
best_matches = df.nsmallest(5, 'ERROR1')
for _, stock in best_matches.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Formula: {stock['FORMULA1_SOLIDITY']:.1f}")
    print(f"  Credit: {stock['CRDT_SCORE']:.1f}, Market Cap: {stock['COM_MKTCAP']:.0f}")
    print()

print("=== EN KÖTÜ UYUMLAR ===")
worst_matches = df.nlargest(5, 'ERROR1')
for _, stock in worst_matches.iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Formula: {stock['FORMULA1_SOLIDITY']:.1f}")
    print(f"  Credit: {stock['CRDT_SCORE']:.1f}, Market Cap: {stock['COM_MKTCAP']:.0f}")
    print()

# Sonuçları kaydet
result_df = df[['PREF IBKR', 'CMON', 'IMPLIED_SOLIDITY', 'FORMULA1_SOLIDITY', 
                'FORMULA2_SOLIDITY', 'FORMULA3_SOLIDITY', 'ERROR1', 'ERROR2', 'ERROR3',
                'CRDT_SCORE', 'COM_MKTCAP', 'COM_LAST_PRICE', 'COM_52W_LOW', 'COM_52W_HIGH']].copy()
result_df.to_csv('solidity_formula_results.csv', index=False)
print(f"Sonuçlar 'solidity_formula_results.csv' dosyasına kaydedildi.") 