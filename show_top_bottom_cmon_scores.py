import pandas as pd

def show_top_bottom_cmon_scores():
    # CSV dosyasını oku
    df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
    
    # CMON bazında gruplandır ve ortalama değerleri al
    cmon_stats = df.groupby('CMON').agg({
        'PREF IBKR': 'first',  # İlk PREF IBKR'yi al
        'COM_MKTCAP': 'mean',  # Market cap ortalaması
        'MKTCAP_NORM': 'mean',  # Market cap norm ortalaması
        'SOLIDITY_SCORE': 'mean',  # Solidity score ortalaması
        'SOLIDITY_SCORE_NORM': 'mean'  # Solidity norm ortalaması
    }).reset_index()
    
    print("=" * 80)
    print("MARKET CAP NORM - EN YÜKSEK 20 CMON")
    print("=" * 80)
    top_mktcap = cmon_stats.nlargest(20, 'MKTCAP_NORM')[['CMON', 'PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']]
    print(top_mktcap.round(2).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("MARKET CAP NORM - EN DÜŞÜK 20 CMON")
    print("=" * 80)
    bottom_mktcap = cmon_stats.nsmallest(20, 'MKTCAP_NORM')[['CMON', 'PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']]
    print(bottom_mktcap.round(2).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("SOLIDITY SCORE NORM - EN YÜKSEK 20 CMON")
    print("=" * 80)
    top_solidity = cmon_stats.nlargest(20, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    print(top_solidity.round(2).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("SOLIDITY SCORE NORM - EN DÜŞÜK 20 CMON")
    print("=" * 80)
    bottom_solidity = cmon_stats.nsmallest(20, 'SOLIDITY_SCORE_NORM')[['CMON', 'PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    print(bottom_solidity.round(2).to_string(index=False))
    
    # İstatistikler
    print("\n" + "=" * 80)
    print("İSTATİSTİKLER")
    print("=" * 80)
    print(f"Toplam CMON sayısı: {len(cmon_stats)}")
    print(f"Toplam hisse sayısı: {len(df)}")
    print(f"Market Cap Norm - Ortalama: {cmon_stats['MKTCAP_NORM'].mean():.2f}")
    print(f"Market Cap Norm - Min: {cmon_stats['MKTCAP_NORM'].min():.2f}, Max: {cmon_stats['MKTCAP_NORM'].max():.2f}")
    print(f"Solidity Score Norm - Ortalama: {cmon_stats['SOLIDITY_SCORE_NORM'].mean():.2f}")
    print(f"Solidity Score Norm - Min: {cmon_stats['SOLIDITY_SCORE_NORM'].min():.2f}, Max: {cmon_stats['SOLIDITY_SCORE_NORM'].max():.2f}")
    
    # Her CMON için kaç tane hisse var
    print(f"\nCMON başına ortalama hisse sayısı: {len(df) / len(cmon_stats):.1f}")

if __name__ == "__main__":
    show_top_bottom_cmon_scores() 