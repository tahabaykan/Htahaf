import pandas as pd
import numpy as np

def fill_missing_solidity_scores():
    """allcomek_sld.csv'den solidity skorlarını al ve eksik olanları doldur"""
    
    print("=== EKSİK SOLIDITY SKORLARINI DOLDURMA ===")
    
    # allcomek_sld.csv dosyasını yükle
    print("1. allcomek_sld.csv dosyası yükleniyor...")
    df = pd.read_csv('allcomek_sld.csv')
    
    print(f"Toplam hisse sayısı: {len(df)}")
    print(f"CMON boş olan hisse sayısı: {df['CMON'].isna().sum()}")
    print(f"SOLIDITY_SCORE_NORM eksik olan hisse sayısı: {df['SOLIDITY_SCORE_NORM'].isna().sum()}")
    
    # Tüm hisselerin SOLIDITY_SCORE_NORM ortalamasını hesapla
    avg_solidity = df['SOLIDITY_SCORE_NORM'].mean()
    print(f"\n2. Tüm hisselerin SOLIDITY_SCORE_NORM ortalaması: {avg_solidity:.2f}")
    
    # %70 değerini hesapla
    fill_value = avg_solidity * 0.7
    print(f"3. CMON boş hisseler için doldurulacak değer (%70): {fill_value:.2f}")
    
    # CMON boş olan hisseleri bul
    missing_cmon_mask = df['CMON'].isna()
    missing_cmon_count = missing_cmon_mask.sum()
    
    print(f"\n4. CMON boş olan {missing_cmon_count} hisse için SOLIDITY_SCORE_NORM dolduruluyor...")
    
    # CMON boş olan hisselerin SOLIDITY_SCORE_NORM değerlerini doldur
    df.loc[missing_cmon_mask, 'SOLIDITY_SCORE_NORM'] = fill_value
    
    # Doldurulan hisseleri göster
    if missing_cmon_count > 0:
        print(f"\nDoldurulan hisseler:")
        print("PREF IBKR          | CMON | SOLIDITY_SCORE_NORM")
        print("-------------------|------|-------------------")
        
        filled_stocks = df[missing_cmon_mask]
        for idx, row in filled_stocks.iterrows():
            print(f"{row['PREF IBKR']:<18} | {str(row['CMON']):<4} | {row['SOLIDITY_SCORE_NORM']:>17.2f}")
    
    # Sonuçları kontrol et
    final_missing = df['SOLIDITY_SCORE_NORM'].isna().sum()
    print(f"\n5. Sonuçlar:")
    print(f"İşlem sonrası SOLIDITY_SCORE_NORM eksik olan hisse sayısı: {final_missing}")
    
    # allcomek_sldf.csv olarak kaydet
    output_file = 'allcomek_sldf.csv'
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n6. Sonuçlar '{output_file}' dosyasına kaydedildi.")
    
    # İstatistikler
    print(f"\n7. SOLIDITY_SCORE_NORM İstatistikleri:")
    print(f"Ortalama: {df['SOLIDITY_SCORE_NORM'].mean():.2f}")
    print(f"Median: {df['SOLIDITY_SCORE_NORM'].median():.2f}")
    print(f"Min: {df['SOLIDITY_SCORE_NORM'].min():.2f}")
    print(f"Max: {df['SOLIDITY_SCORE_NORM'].max():.2f}")
    print(f"Std: {df['SOLIDITY_SCORE_NORM'].std():.2f}")
    
    # En yüksek ve en düşük 10 hisse
    print(f"\n8. EN YÜKSEK 10 SOLIDITY_SCORE_NORM:")
    top_10 = df.nlargest(10, 'SOLIDITY_SCORE_NORM')[['PREF IBKR', 'CMON', 'SOLIDITY_SCORE_NORM']]
    for idx, row in top_10.iterrows():
        print(f"{row['PREF IBKR']:<18} | {str(row['CMON']):<6} | {row['SOLIDITY_SCORE_NORM']:>6.2f}")
    
    print(f"\n9. EN DÜŞÜK 10 SOLIDITY_SCORE_NORM:")
    bottom_10 = df.nsmallest(10, 'SOLIDITY_SCORE_NORM')[['PREF IBKR', 'CMON', 'SOLIDITY_SCORE_NORM']]
    for idx, row in bottom_10.iterrows():
        print(f"{row['PREF IBKR']:<18} | {str(row['CMON']):<6} | {row['SOLIDITY_SCORE_NORM']:>6.2f}")
    
    print(f"\n=== İŞLEM TAMAMLANDI ===")
    return df

if __name__ == "__main__":
    fill_missing_solidity_scores() 