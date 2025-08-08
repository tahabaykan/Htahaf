import pandas as pd
import numpy as np

def check_total_score_calculation():
    """Total Score Norm hesaplamasını kontrol et"""
    
    # Sonuç dosyasını oku
    try:
        df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"Dosya okundu: {len(df)} satır")
    except FileNotFoundError:
        print("allcomek_sld.csv dosyası bulunamadı!")
        return
    
    # FCNCA ve diğer hisseleri kontrol et
    print("\n" + "="*100)
    print("TOTAL SCORE NORM HESAPLAMA KONTROLÜ")
    print("="*100)
    
    # FCNCA hisselerini bul
    fcnca_stocks = df[df['CMON'] == 'FCNCA']
    
    print(f"\nFCNCA Hisseleri (Total Score Norm = 100.00):")
    print(f"{'PREF IBKR':<12} | {'COM_LAST_PRICE':<15} | {'CRDT_NORM':<10} | {'TOTAL_SCORE_NORM':<18}")
    print("-"*60)
    
    for idx, row in fcnca_stocks.iterrows():
        print(f"{row['PREF IBKR']:<12} | {row['COM_LAST_PRICE']:<15.2f} | {row['CRDT_NORM']:<10.2f} | {row['TOTAL_SCORE_NORM']:<18.2f}")
    
    # JPM hisselerini kontrol et
    jpm_stocks = df[df['CMON'] == 'JPM'].head(3)
    
    print(f"\nJPM Hisseleri (Total Score Norm = 16.35):")
    print(f"{'PREF IBKR':<12} | {'COM_LAST_PRICE':<15} | {'CRDT_NORM':<10} | {'TOTAL_SCORE_NORM':<18}")
    print("-"*60)
    
    for idx, row in jpm_stocks.iterrows():
        print(f"{row['PREF IBKR']:<12} | {row['COM_LAST_PRICE']:<15.2f} | {row['CRDT_NORM']:<10.2f} | {row['TOTAL_SCORE_NORM']:<18.2f}")
    
    # APO hisselerini kontrol et
    apo_stocks = df[df['CMON'] == 'APO'].head(3)
    
    print(f"\nAPO Hisseleri (Total Score Norm = 10.54):")
    print(f"{'PREF IBKR':<12} | {'COM_LAST_PRICE':<15} | {'CRDT_NORM':<10} | {'TOTAL_SCORE_NORM':<18}")
    print("-"*60)
    
    for idx, row in apo_stocks.iterrows():
        print(f"{row['PREF IBKR']:<12} | {row['COM_LAST_PRICE']:<15.2f} | {row['CRDT_NORM']:<10.2f} | {row['TOTAL_SCORE_NORM']:<18.2f}")
    
    # COM_LAST_PRICE istatistikleri
    print(f"\n" + "="*100)
    print("COM_LAST_PRICE İSTATİSTİKLERİ")
    print("="*100)
    
    print(f"COM_LAST_PRICE - Min: {df['COM_LAST_PRICE'].min():.2f}")
    print(f"COM_LAST_PRICE - Max: {df['COM_LAST_PRICE'].max():.2f}")
    print(f"COM_LAST_PRICE - Ortalama: {df['COM_LAST_PRICE'].mean():.2f}")
    print(f"COM_LAST_PRICE - Median: {df['COM_LAST_PRICE'].median():.2f}")
    
    # CRDT_NORM istatistikleri
    print(f"\nCRDT_NORM İSTATİSTİKLERİ")
    print(f"CRDT_NORM - Min: {df['CRDT_NORM'].min():.2f}")
    print(f"CRDT_NORM - Max: {df['CRDT_NORM'].max():.2f}")
    print(f"CRDT_NORM - Ortalama: {df['CRDT_NORM'].mean():.2f}")
    
    # TOTAL_SCORE_NORM istatistikleri
    print(f"\nTOTAL_SCORE_NORM İSTATİSTİKLERİ")
    print(f"TOTAL_SCORE_NORM - Min: {df['TOTAL_SCORE_NORM'].min():.2f}")
    print(f"TOTAL_SCORE_NORM - Max: {df['TOTAL_SCORE_NORM'].max():.2f}")
    print(f"TOTAL_SCORE_NORM - Ortalama: {df['TOTAL_SCORE_NORM'].mean():.2f}")
    
    # En yüksek ve en düşük TOTAL_SCORE_NORM'ları göster
    print(f"\nEn Yüksek TOTAL_SCORE_NORM'lar:")
    top_total = df.nlargest(10, 'TOTAL_SCORE_NORM')[['CMON', 'PREF IBKR', 'COM_LAST_PRICE', 'CRDT_NORM', 'TOTAL_SCORE_NORM']]
    print(top_total.round(2).to_string(index=False))
    
    print(f"\nEn Düşük TOTAL_SCORE_NORM'lar:")
    bottom_total = df.nsmallest(10, 'TOTAL_SCORE_NORM')[['CMON', 'PREF IBKR', 'COM_LAST_PRICE', 'CRDT_NORM', 'TOTAL_SCORE_NORM']]
    print(bottom_total.round(2).to_string(index=False))

if __name__ == "__main__":
    check_total_score_calculation() 