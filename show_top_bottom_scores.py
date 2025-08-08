import pandas as pd

def show_top_bottom_scores():
    # CSV dosyasını oku
    df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
    
    print("=" * 80)
    print("MARKET CAP NORM - EN YÜKSEK 20 HİSSE")
    print("=" * 80)
    top_mktcap = df.nlargest(20, 'MKTCAP_NORM')[['PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']]
    print(top_mktcap.round(2).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("MARKET CAP NORM - EN DÜŞÜK 20 HİSSE")
    print("=" * 80)
    bottom_mktcap = df.nsmallest(20, 'MKTCAP_NORM')[['PREF IBKR', 'COM_MKTCAP', 'MKTCAP_NORM']]
    print(bottom_mktcap.round(2).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("SOLIDITY SCORE NORM - EN YÜKSEK 20 HİSSE")
    print("=" * 80)
    top_solidity = df.nlargest(20, 'SOLIDITY_SCORE_NORM')[['PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    print(top_solidity.round(2).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("SOLIDITY SCORE NORM - EN DÜŞÜK 20 HİSSE")
    print("=" * 80)
    bottom_solidity = df.nsmallest(20, 'SOLIDITY_SCORE_NORM')[['PREF IBKR', 'SOLIDITY_SCORE', 'SOLIDITY_SCORE_NORM']]
    print(bottom_solidity.round(2).to_string(index=False))
    
    # İstatistikler
    print("\n" + "=" * 80)
    print("İSTATİSTİKLER")
    print("=" * 80)
    print(f"Toplam hisse sayısı: {len(df)}")
    print(f"Market Cap Norm - Ortalama: {df['MKTCAP_NORM'].mean():.2f}")
    print(f"Market Cap Norm - Min: {df['MKTCAP_NORM'].min():.2f}, Max: {df['MKTCAP_NORM'].max():.2f}")
    print(f"Solidity Score Norm - Ortalama: {df['SOLIDITY_SCORE_NORM'].mean():.2f}")
    print(f"Solidity Score Norm - Min: {df['SOLIDITY_SCORE_NORM'].min():.2f}, Max: {df['SOLIDITY_SCORE_NORM'].max():.2f}")

if __name__ == "__main__":
    show_top_bottom_scores() 