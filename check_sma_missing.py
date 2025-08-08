import pandas as pd
import numpy as np
import os

def check_sma_missing():
    """SMA verileri eksik olan hisseleri tespit et"""
    
    # Test edilecek dosyalar
    test_files = [
        'sekheldkuponlu.csv',
        'nsekheldkuponlu.csv'
    ]
    
    print("=== SMA VERİLERİ EKSİK ANALİZİ ===\n")
    
    for file in test_files:
        if not os.path.exists(file):
            print(f"! {file} dosyası bulunamadı")
            continue
            
        print(f"\n--- {file} ---")
        df = pd.read_csv(file)
        
        # SMA kolonlarını kontrol et
        sma_columns = ['SMA20', 'SMA63', 'SMA246', 'SMA20 chg', 'SMA63 chg', 'SMA246 chg']
        
        for col in sma_columns:
            if col in df.columns:
                # NaN değerleri say
                nan_count = df[col].isna().sum()
                empty_count = (df[col] == '').sum()
                zero_count = (df[col] == 0).sum()
                
                if nan_count > 0 or empty_count > 0:
                    print(f"  {col}: {nan_count} NaN, {empty_count} boş, {zero_count} sıfır")
                    
                    # Hangi hisselerde eksik
                    missing_stocks = df[df[col].isna() | (df[col] == '')]['PREF IBKR'].tolist()
                    if missing_stocks:
                        print(f"    Eksik hisseler: {missing_stocks[:5]}...")  # İlk 5'ini göster
            else:
                print(f"  {col}: Kolon bulunamadı")

if __name__ == "__main__":
    check_sma_missing() 