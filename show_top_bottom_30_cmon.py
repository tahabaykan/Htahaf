import pandas as pd

def show_top_bottom_30_cmon():
    # CSV dosyasını oku
    df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
    
    # CMON bazında gruplandır ve ortalama değerleri al
    cmon_stats = df.groupby('CMON').agg({
        'PREF IBKR': 'first',
        'COM_MKTCAP': 'mean',
        'MKTCAP_NORM': 'mean',
        'SOLIDITY_SCORE': 'mean',
        'SOLIDITY_SCORE_NORM': 'mean',
        'CRDT_SCORE': 'mean'
    }).reset_index()
    
    print("=" * 100)
    print("SOLIDITY SCORE NORM - EN YÜKSEK 30 CMON")
    print("=" * 100)
    print("CMON    | PREF IBKR | Market Cap(B$) | MKTCAP_NORM | SOLIDITY_SCORE | SOLIDITY_NORM | CRDT_SCORE")
    print("-" * 100)
    
    top_30 = cmon_stats.nlargest(30, 'SOLIDITY_SCORE_NORM')
    for idx, row in top_30.iterrows():
        print(f"{row['CMON']:<7} | {row['PREF IBKR']:<9} | {row['COM_MKTCAP']:>12.2f} | {row['MKTCAP_NORM']:>11.2f} | {row['SOLIDITY_SCORE']:>14.2f} | {row['SOLIDITY_SCORE_NORM']:>12.2f} | {row['CRDT_SCORE']:>9.2f}")
    
    print("\n" + "=" * 100)
    print("SOLIDITY SCORE NORM - EN DÜŞÜK 30 CMON")
    print("=" * 100)
    print("CMON    | PREF IBKR | Market Cap(B$) | MKTCAP_NORM | SOLIDITY_SCORE | SOLIDITY_NORM | CRDT_SCORE")
    print("-" * 100)
    
    bottom_30 = cmon_stats.nsmallest(30, 'SOLIDITY_SCORE_NORM')
    for idx, row in bottom_30.iterrows():
        print(f"{row['CMON']:<7} | {row['PREF IBKR']:<9} | {row['COM_MKTCAP']:>12.2f} | {row['MKTCAP_NORM']:>11.2f} | {row['SOLIDITY_SCORE']:>14.2f} | {row['SOLIDITY_SCORE_NORM']:>12.2f} | {row['CRDT_SCORE']:>9.2f}")
    
    # İstatistikler
    print("\n" + "=" * 100)
    print("İSTATİSTİKLER")
    print("=" * 100)
    print(f"Toplam CMON sayısı: {len(cmon_stats)}")
    print(f"Toplam hisse sayısı: {len(df)}")
    print(f"Solidity Score Norm - Ortalama: {cmon_stats['SOLIDITY_SCORE_NORM'].mean():.2f}")
    print(f"Solidity Score Norm - Min: {cmon_stats['SOLIDITY_SCORE_NORM'].min():.2f}, Max: {cmon_stats['SOLIDITY_SCORE_NORM'].max():.2f}")
    print(f"Market Cap Norm - Ortalama: {cmon_stats['MKTCAP_NORM'].mean():.2f}")
    print(f"Credit Score - Ortalama: {cmon_stats['CRDT_SCORE'].mean():.2f}")
    
    # En yüksek ve en düşük 5'inin detayları
    print("\n" + "=" * 100)
    print("EN YÜKSEK 5 CMON DETAYI")
    print("=" * 100)
    top_5 = cmon_stats.nlargest(5, 'SOLIDITY_SCORE_NORM')
    for idx, row in top_5.iterrows():
        print(f"\n{row['CMON']} ({row['PREF IBKR']}):")
        print(f"  Market Cap: {row['COM_MKTCAP']:.2f}B$")
        print(f"  Market Cap Norm: {row['MKTCAP_NORM']:.2f}")
        print(f"  Credit Score: {row['CRDT_SCORE']:.2f}")
        print(f"  Solidity Score: {row['SOLIDITY_SCORE']:.2f}")
        print(f"  Solidity Norm: {row['SOLIDITY_SCORE_NORM']:.2f}")
    
    print("\n" + "=" * 100)
    print("EN DÜŞÜK 5 CMON DETAYI")
    print("=" * 100)
    bottom_5 = cmon_stats.nsmallest(5, 'SOLIDITY_SCORE_NORM')
    for idx, row in bottom_5.iterrows():
        print(f"\n{row['CMON']} ({row['PREF IBKR']}):")
        print(f"  Market Cap: {row['COM_MKTCAP']:.2f}B$")
        print(f"  Market Cap Norm: {row['MKTCAP_NORM']:.2f}")
        print(f"  Credit Score: {row['CRDT_SCORE']:.2f}")
        print(f"  Solidity Score: {row['SOLIDITY_SCORE']:.2f}")
        print(f"  Solidity Norm: {row['SOLIDITY_SCORE_NORM']:.2f}")

if __name__ == "__main__":
    show_top_bottom_30_cmon() 