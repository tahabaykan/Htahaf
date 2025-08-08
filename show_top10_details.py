import pandas as pd
import numpy as np

def show_top10_detailed_breakdown():
    """Top 10 hisse için detaylı breakdown göster"""
    
    # Sonuç dosyasını oku
    try:
        df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"Dosya okundu: {len(df)} satır")
    except FileNotFoundError:
        print("allcomek_sld.csv dosyası bulunamadı!")
        return
    
    # Top 10 hisseyi al (SOLIDITY_SCORE_NORM'e göre)
    top10 = df.nlargest(10, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'COM_MKTCAP', 'CRDT_SCORE', 'CRDT_NORM', 'MKTCAP_NORM', 'TOTAL_SCORE_NORM', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    
    print("\n" + "="*100)
    print("TOP 10 HİSSE - DETAYLI BREAKDOWN")
    print("="*100)
    
    print(f"{'CMON':<8} | {'PREF IBKR':<12} | {'Market Cap(B$)':<15} | {'CRDT_SCORE':<12} | {'CRDT_NORM':<10} | {'MKTCAP_NORM':<12} | {'TOTAL_SCORE_NORM':<18} | {'SOLIDITY_SCORE':<15} | {'SOLIDITY_NORM':<12}")
    print("-"*100)
    
    for idx, row in top10.iterrows():
        print(f"{row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['COM_MKTCAP']:<15.2f} | {row['CRDT_SCORE']:<12.2f} | {row['CRDT_NORM']:<10.2f} | {row['MKTCAP_NORM']:<12.2f} | {row['TOTAL_SCORE_NORM']:<18.2f} | {row['SOLIDITY_SCORE']:<15.2f} | {row['SOLIDITY_SCORE_NORM']:<12.2f}")
    
    print("\n" + "="*100)
    print("DETAYLI ANALİZ")
    print("="*100)
    
    for idx, row in top10.iterrows():
        print(f"\n{row['CMON']} ({row['PREF IBKR']}):")
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
    
    print("\n" + "="*100)
    print("ÖZET İSTATİSTİKLER")
    print("="*100)
    
    print(f"Top 10 Ortalama Değerler:")
    print(f"  Credit Score: {top10['CRDT_SCORE'].mean():.2f}")
    print(f"  Credit Score Norm: {top10['CRDT_NORM'].mean():.2f}")
    print(f"  Market Cap Norm: {top10['MKTCAP_NORM'].mean():.2f}")
    print(f"  Total Score Norm: {top10['TOTAL_SCORE_NORM'].mean():.2f}")
    print(f"  Solidity Score Norm: {top10['SOLIDITY_SCORE_NORM'].mean():.2f}")
    
    print(f"\nTop 10 Min-Max Değerler:")
    print(f"  Credit Score: {top10['CRDT_SCORE'].min():.2f} - {top10['CRDT_SCORE'].max():.2f}")
    print(f"  Credit Score Norm: {top10['CRDT_NORM'].min():.2f} - {top10['CRDT_NORM'].max():.2f}")
    print(f"  Market Cap Norm: {top10['MKTCAP_NORM'].min():.2f} - {top10['MKTCAP_NORM'].max():.2f}")
    print(f"  Total Score Norm: {top10['TOTAL_SCORE_NORM'].min():.2f} - {top10['TOTAL_SCORE_NORM'].max():.2f}")

if __name__ == "__main__":
    show_top10_detailed_breakdown() 