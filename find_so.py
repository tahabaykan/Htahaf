import pandas as pd
import numpy as np

def find_so():
    """SO (Southern Company) hissesini bul"""
    
    # Sonuç dosyasını oku
    try:
        df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"Dosya okundu: {len(df)} satır")
    except FileNotFoundError:
        print("allcomek_sld.csv dosyası bulunamadı!")
        return
    
    # SO hisselerini ara
    so_stocks = df[df['CMON'] == 'SO']
    
    print("\n" + "="*80)
    print("SO (SOUTHERN COMPANY) HİSSELERİ")
    print("="*80)
    
    if not so_stocks.empty:
        print(f"{'CMON':<8} | {'PREF IBKR':<12} | {'Market Cap(B$)':<15} | {'CRDT_SCORE':<12} | {'CRDT_NORM':<10} | {'MKTCAP_NORM':<12} | {'TOTAL_SCORE_NORM':<18} | {'SOLIDITY_SCORE':<15} | {'SOLIDITY_NORM':<12}")
        print("-"*80)
        
        for idx, row in so_stocks.iterrows():
            print(f"{row['CMON']:<8} | {row['PREF IBKR']:<12} | {row['COM_MKTCAP']:<15.2f} | {row['CRDT_SCORE']:<12.2f} | {row['CRDT_NORM']:<10.2f} | {row['MKTCAP_NORM']:<12.2f} | {row['TOTAL_SCORE_NORM']:<18.2f} | {row['SOLIDITY_SCORE']:<15.2f} | {row['SOLIDITY_SCORE_NORM']:<12.2f}")
        
        print(f"\nToplam SO hissesi: {len(so_stocks)} adet")
        
        # Ortalama değerler
        print(f"\nSO Ortalama Değerler:")
        print(f"  Market Cap: {so_stocks['COM_MKTCAP'].mean():.2f}B$")
        print(f"  Credit Score: {so_stocks['CRDT_SCORE'].mean():.2f}")
        print(f"  Credit Score Norm: {so_stocks['CRDT_NORM'].mean():.2f}")
        print(f"  Market Cap Norm: {so_stocks['MKTCAP_NORM'].mean():.2f}")
        print(f"  Total Score Norm: {so_stocks['TOTAL_SCORE_NORM'].mean():.2f}")
        print(f"  Solidity Score: {so_stocks['SOLIDITY_SCORE'].mean():.2f}")
        print(f"  Solidity Norm: {so_stocks['SOLIDITY_SCORE_NORM'].mean():.2f}")
        
        # Market cap range'ini belirle
        mktcap = so_stocks['COM_MKTCAP'].iloc[0]
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
        
    else:
        print("SO hissesi bulunamadı!")
    
    # Tüm CMON'ları listele ve SO'nun sırasını bul
    cmon_stats = df.groupby('CMON').agg({
        'SOLIDITY_SCORE_NORM': 'mean'
    }).reset_index()
    
    cmon_sorted = cmon_stats.sort_values('SOLIDITY_SCORE_NORM', ascending=False)
    so_rank = cmon_sorted[cmon_sorted['CMON'] == 'SO'].index[0] + 1 if 'SO' in cmon_sorted['CMON'].values else None
    
    if so_rank:
        print(f"\nSO'nun CMON sıralamasındaki yeri: {so_rank}. sıra")
        print(f"Toplam CMON sayısı: {len(cmon_sorted)}")
        
        # SO'nun etrafındaki 5 CMON'u göster
        start_idx = max(0, so_rank - 6)
        end_idx = min(len(cmon_sorted), so_rank + 5)
        
        print(f"\nSO'nun etrafındaki CMON'lar:")
        for i in range(start_idx, end_idx):
            rank = i + 1
            cmon = cmon_sorted.iloc[i]['CMON']
            solidity = cmon_sorted.iloc[i]['SOLIDITY_SCORE_NORM']
            marker = " ← SO" if cmon == 'SO' else ""
            print(f"  {rank}. {cmon}: {solidity:.2f}{marker}")

if __name__ == "__main__":
    find_so() 