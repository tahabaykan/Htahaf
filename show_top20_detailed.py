import pandas as pd
import numpy as np

def show_top20_detailed():
    """İlk 20 CMON hissenin tüm normlarını detaylı göster"""
    
    # Sonuç dosyasını oku
    try:
        df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"Dosya okundu: {len(df)} satır")
    except FileNotFoundError:
        print("allcomek_sld.csv dosyası bulunamadı!")
        return
    
    # CMON bazında gruplandır ve ortalama değerleri al
    cmon_stats = df.groupby('CMON').agg({
        'PREF IBKR': 'first',
        'COM_MKTCAP': 'mean',
        'CRDT_SCORE': 'mean',
        'CRDT_NORM': 'mean',
        'MKTCAP_NORM': 'mean',
        'TOTAL_SCORE_NORM': 'mean',
        'SOLIDITY_SCORE': 'mean',
        'SOLIDITY_SCORE_NORM': 'mean'
    }).reset_index()
    
    # Solidity score norm'a göre sırala
    top20_cmon = cmon_stats.nlargest(20, 'SOLIDITY_SCORE_NORM')
    
    print("\n" + "="*140)
    print("İLK 20 CMON - TÜM NORM DEĞERLERİ")
    print("="*140)
    
    print(f"{'SIRA':<4} | {'CMON':<8} | {'PREF IBKR':<12} | {'Market Cap(B$)':<15} | {'CRDT_SCORE':<12} | {'CRDT_NORM':<10} | {'MKTCAP_NORM':<12} | {'TOTAL_SCORE_NORM':<18} | {'SOLIDITY_SCORE':<15} | {'SOLIDITY_NORM':<12}")
    print("-"*140)
    
    for idx, row in top20_cmon.iterrows():
        rank = idx + 1
        print(f"{rank:<4} | {row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['COM_MKTCAP']:<15.2f} | {row['CRDT_SCORE']:<12.2f} | {row['CRDT_NORM']:<10.2f} | {row['MKTCAP_NORM']:<12.2f} | {row['TOTAL_SCORE_NORM']:<18.2f} | {row['SOLIDITY_SCORE']:<15.2f} | {row['SOLIDITY_SCORE_NORM']:<12.2f}")
    
    print("\n" + "="*140)
    print("DETAYLI ANALİZ - TÜM 20 CMON")
    print("="*140)
    
    for idx, row in top20_cmon.iterrows():
        rank = idx + 1
        print(f"\n{rank}. {row['CMON']} ({row['PREF IBKR']}):")
        print(f"  Market Cap: {row['COM_MKTCAP']:.2f}B$")
        print(f"  Credit Score: {row['CRDT_SCORE']:.2f}")
        print(f"  Credit Score Norm: {row['CRDT_NORM']:.2f}")
        print(f"  Market Cap Norm: {row['MKTCAP_NORM']:.2f}")
        print(f"  Total Score Norm: {row['TOTAL_SCORE_NORM']:.2f}")
        print(f"  Solidity Score: {row['SOLIDITY_SCORE']:.2f}")
        print(f"  Solidity Norm: {row['SOLIDITY_SCORE_NORM']:.2f}")
        
        # Market cap range'ini belirle
        mktcap = row['COM_MKTCAP']
        if pd.isna(mktcap):
            range_info = "Unknown"
        elif mktcap < 1:
            range_info = "< 1B (60% Total, 35% Market Cap, 5% Credit)"
        elif mktcap < 3:
            range_info = "1-3B (55% Total, 35% Market Cap, 10% Credit)"
        elif mktcap < 7:
            range_info = "3-7B (50% Total, 30% Market Cap, 20% Credit)"
        elif mktcap < 12:
            range_info = "7-12B (45% Total, 25% Market Cap, 30% Credit)"
        elif mktcap < 20:
            range_info = "12-20B (40% Total, 20% Market Cap, 40% Credit)"
        elif mktcap < 35:
            range_info = "20-35B (35% Total, 20% Market Cap, 45% Credit)"
        elif mktcap < 75:
            range_info = "35-75B (30% Total, 20% Market Cap, 50% Credit)"
        elif mktcap < 200:
            range_info = "75-200B (25% Total, 20% Market Cap, 55% Credit)"
        else:
            range_info = "200B+ (20% Total, 20% Market Cap, 60% Credit)"
        
        print(f"  Market Cap Range: {range_info}")
    
    print("\n" + "="*140)
    print("ÖZET İSTATİSTİKLER")
    print("="*140)
    
    print(f"Top 20 Ortalama Değerler:")
    print(f"  Market Cap: {top20_cmon['COM_MKTCAP'].mean():.2f}B$")
    print(f"  Credit Score: {top20_cmon['CRDT_SCORE'].mean():.2f}")
    print(f"  Credit Score Norm: {top20_cmon['CRDT_NORM'].mean():.2f}")
    print(f"  Market Cap Norm: {top20_cmon['MKTCAP_NORM'].mean():.2f}")
    print(f"  Total Score Norm: {top20_cmon['TOTAL_SCORE_NORM'].mean():.2f}")
    print(f"  Solidity Score Norm: {top20_cmon['SOLIDITY_SCORE_NORM'].mean():.2f}")
    
    print(f"\nTop 20 Min-Max Değerler:")
    print(f"  Market Cap: {top20_cmon['COM_MKTCAP'].min():.2f}B$ - {top20_cmon['COM_MKTCAP'].max():.2f}B$")
    print(f"  Credit Score: {top20_cmon['CRDT_SCORE'].min():.2f} - {top20_cmon['CRDT_SCORE'].max():.2f}")
    print(f"  Credit Score Norm: {top20_cmon['CRDT_NORM'].min():.2f} - {top20_cmon['CRDT_NORM'].max():.2f}")
    print(f"  Market Cap Norm: {top20_cmon['MKTCAP_NORM'].min():.2f} - {top20_cmon['MKTCAP_NORM'].max():.2f}")
    print(f"  Total Score Norm: {top20_cmon['TOTAL_SCORE_NORM'].min():.2f} - {top20_cmon['TOTAL_SCORE_NORM'].max():.2f}")
    print(f"  Solidity Score Norm: {top20_cmon['SOLIDITY_SCORE_NORM'].min():.2f} - {top20_cmon['SOLIDITY_SCORE_NORM'].max():.2f}")
    
    # En yüksek değerler
    print(f"\nEn Yüksek Değerler:")
    max_credit = top20_cmon.loc[top20_cmon['CRDT_SCORE'].idxmax()]
    max_mktcap = top20_cmon.loc[top20_cmon['COM_MKTCAP'].idxmax()]
    max_total = top20_cmon.loc[top20_cmon['TOTAL_SCORE_NORM'].idxmax()]
    
    print(f"  En Yüksek Credit Score: {max_credit['CMON']} ({max_credit['PREF IBKR']}) - {max_credit['CRDT_SCORE']:.2f}")
    print(f"  En Yüksek Market Cap: {max_mktcap['CMON']} ({max_mktcap['PREF IBKR']}) - {max_mktcap['COM_MKTCAP']:.2f}B$")
    print(f"  En Yüksek Total Score Norm: {max_total['CMON']} ({max_total['PREF IBKR']}) - {max_total['TOTAL_SCORE_NORM']:.2f}")

if __name__ == "__main__":
    show_top20_detailed() 