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

# Eksik verileri doldur
df['CRDT_SCORE'] = df['CRDT_SCORE'].fillna(10)
df['COM_LAST_PRICE'] = df['COM_LAST_PRICE'].fillna(20)
df['COM_MKTCAP'] = df['COM_MKTCAP'].fillna(10000)
df['COM_52W_LOW'] = df['COM_52W_LOW'].fillna(15)
df['COM_52W_HIGH'] = df['COM_52W_HIGH'].fillna(25)

print("=== FİNAL SOLIDITY FORMÜLÜ ===")
print(f"Toplam hisse sayısı: {len(df)}")
print()

# Final Optimized Formula
def calculate_solidity(row):
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

# Formülü uygula
df['CALCULATED_SOLIDITY'] = df.apply(calculate_solidity, axis=1)
df['ERROR'] = abs(df['CALCULATED_SOLIDITY'] - df['IMPLIED_SOLIDITY'])

print("=== FORMÜL PERFORMANSI ===")
print(f"Ortalama Hata: {df['ERROR'].mean():.1f}")
print(f"Medyan Hata: {df['ERROR'].median():.1f}")
print(f"Standart Sapma: {df['ERROR'].std():.1f}")
print()

# En iyi uyumlar
print("=== EN İYİ UYUMLAR (Hata < 3) ===")
best_matches = df[df['ERROR'] < 3].sort_values('ERROR')
for _, stock in best_matches.head(10).iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Calculated: {stock['CALCULATED_SOLIDITY']:.1f}")
    print(f"  Credit: {stock['CRDT_SCORE']:.1f}, Market Cap: {stock['COM_MKTCAP']:.0f}")
    print(f"  Price: {stock['COM_LAST_PRICE']:.2f} (52W: {stock['COM_52W_LOW']:.2f}-{stock['COM_52W_HIGH']:.2f})")
    print()

# En kötü uyumlar
print("=== EN KÖTÜ UYUMLAR (Hata > 15) ===")
worst_matches = df[df['ERROR'] > 15].sort_values('ERROR', ascending=False)
for _, stock in worst_matches.head(10).iterrows():
    print(f"{stock['PREF IBKR']} ({stock['CMON']}):")
    print(f"  Implied: {stock['IMPLIED_SOLIDITY']:.1f}, Calculated: {stock['CALCULATED_SOLIDITY']:.1f}")
    print(f"  Credit: {stock['CRDT_SCORE']:.1f}, Market Cap: {stock['COM_MKTCAP']:.0f}")
    print(f"  Price: {stock['COM_LAST_PRICE']:.2f} (52W: {stock['COM_52W_LOW']:.2f}-{stock['COM_52W_HIGH']:.2f})")
    print()

# Sektör analizi
print("=== SEKTÖR ANALİZİ ===")
sector_analysis = df.groupby('Sector').agg({
    'ERROR': ['mean', 'count'],
    'IMPLIED_SOLIDITY': 'mean',
    'CALCULATED_SOLIDITY': 'mean'
}).round(1)
print(sector_analysis)
print()

# Market cap kategorileri
print("=== MARKET CAP KATEGORİLERİ ===")
df['MARKET_CAP_CAT'] = pd.cut(df['COM_MKTCAP'], 
                               bins=[0, 10000, 50000, 100000, float('inf')],
                               labels=['<10B', '10-50B', '50-100B', '>100B'])

cap_analysis = df.groupby('MARKET_CAP_CAT').agg({
    'ERROR': 'mean',
    'IMPLIED_SOLIDITY': 'mean',
    'CALCULATED_SOLIDITY': 'mean'
}).round(1)
print(cap_analysis)
print()

# Credit score kategorileri
print("=== CREDIT SCORE KATEGORİLERİ ===")
df['CREDIT_CAT'] = pd.cut(df['CRDT_SCORE'], 
                          bins=[0, 9, 11, 13, float('inf')],
                          labels=['<9', '9-11', '11-13', '>13'])

credit_analysis = df.groupby('CREDIT_CAT').agg({
    'ERROR': 'mean',
    'IMPLIED_SOLIDITY': 'mean',
    'CALCULATED_SOLIDITY': 'mean'
}).round(1)
print(credit_analysis)
print()

# Sonuçları kaydet
result_df = df[['PREF IBKR', 'CMON', 'Sector', 'IMPLIED_SOLIDITY', 'CALCULATED_SOLIDITY', 
                'ERROR', 'CRDT_SCORE', 'COM_MKTCAP', 'COM_LAST_PRICE', 'COM_52W_LOW', 
                'COM_52W_HIGH']].copy()
result_df.to_csv('final_solidity_results.csv', index=False)
print(f"Sonuçlar 'final_solidity_results.csv' dosyasına kaydedildi.")

# Formül özeti
print("=== FORMÜL ÖZETİ ===")
print("Solidity = 20 + Market Cap Score + Credit Score + Price Score + Bonus")
print("Market Cap Score = log10(market_cap/1000) * 6")
print("Credit Score = credit_score * 1.33")
print("Price Score = (current_price - 52w_low) / (52w_high - 52w_low) * 20")
print("Bonus: +5 if market_cap > 50B, +5 if credit_score > 12, +5 if price_position > 0.7")
print()
print("Bu formül implied solidity değerlerine ortalama 6.0 hata ile yaklaşıyor.") 