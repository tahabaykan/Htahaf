import pandas as pd
import numpy as np
import os

def check_missing_columns():
    """CSV dosyalarındaki boş kolonları tespit et"""
    
    # Test edilecek dosyalar
    test_files = [
        'sekheldkuponlu.csv',
        'nsekheldkuponlu.csv',
        'advekheldkuponlu.csv',
        'finekheldkuponlu.csv'
    ]
    
    print("=== BOŞ KOLON ANALİZİ ===\n")
    
    for file in test_files:
        if not os.path.exists(file):
            print(f"! {file} dosyası bulunamadı")
            continue
            
        print(f"\n--- {file} ---")
        df = pd.read_csv(file)
        
        # Tüm kolonları kontrol et
        for col in df.columns:
            # NaN değerleri say
            nan_count = df[col].isna().sum()
            empty_count = (df[col] == '').sum()
            zero_count = (df[col] == 0).sum() if df[col].dtype in ['int64', 'float64'] else 0
            
            total_missing = nan_count + empty_count
            
            if total_missing > 0:
                print(f"  {col}: {total_missing}/{len(df)} boş ({total_missing/len(df)*100:.1f}%)")
                
                # Örnek boş değerler
                if total_missing > 0:
                    missing_indices = df[df[col].isna() | (df[col] == '')].index[:3]
                    if len(missing_indices) > 0:
                        print(f"    Örnek boş hisseler: {list(df.loc[missing_indices, 'PREF IBKR'])}")
        
        # Özellikle önemli kolonları kontrol et
        important_cols = [
            'Oct19_diff', 'Aug2022_diff', 'SMA20', 'SMA63', 'SMA246',
            'SMA20 chg', 'SMA63 chg', 'SMA246 chg',
            '3M Low', '3M High', '6M Low', '6M High', '1Y Low', '1Y High',
            'Last Price', 'Div adj.price'
        ]
        
        print(f"\n  Önemli kolonlar kontrolü:")
        for col in important_cols:
            if col in df.columns:
                missing = df[col].isna().sum() + (df[col] == '').sum()
                if missing > 0:
                    print(f"    {col}: {missing}/{len(df)} boş")
            else:
                print(f"    {col}: KOLON YOK")

def check_specific_columns():
    """Belirli kolonların durumunu detaylı kontrol et"""
    
    print("\n=== DETAYLI KOLON ANALİZİ ===\n")
    
    # Test dosyası
    test_file = 'sekheldkuponlu.csv'
    if not os.path.exists(test_file):
        print(f"! {test_file} dosyası bulunamadı")
        return
        
    df = pd.read_csv(test_file)
    
    # Kontrol edilecek kolonlar
    columns_to_check = [
        'Oct19_diff', 'Aug2022_diff', 'SMA20', 'SMA63', 'SMA246',
        'SMA20 chg', 'SMA63 chg', 'SMA246 chg',
        '3M Low', '3M High', '6M Low', '6M High', '1Y Low', '1Y High',
        'Last Price', 'Div adj.price', 'TIME TO DIV'
    ]
    
    for col in columns_to_check:
        if col in df.columns:
            # Boş değerleri bul
            missing_mask = df[col].isna() | (df[col] == '')
            missing_count = missing_mask.sum()
            
            if missing_count > 0:
                print(f"\n{col} kolonu:")
                print(f"  Toplam: {len(df)}, Boş: {missing_count} ({missing_count/len(df)*100:.1f}%)")
                
                # Boş olan hisseleri listele
                missing_stocks = df[missing_mask]['PREF IBKR'].tolist()
                print(f"  Boş hisseler: {missing_stocks[:10]}")  # İlk 10 tanesini göster
                
                # Dolu değerlerin özeti
                non_missing = df[~missing_mask][col]
                if len(non_missing) > 0:
                    try:
                        numeric_values = pd.to_numeric(non_missing, errors='coerce')
                        numeric_values = numeric_values.dropna()
                        if len(numeric_values) > 0:
                            print(f"  Dolu değerler: Min={numeric_values.min():.2f}, Max={numeric_values.max():.2f}, Ort={numeric_values.mean():.2f}")
                    except:
                        print(f"  Dolu değerler: {len(non_missing)} adet")
        else:
            print(f"\n{col}: KOLON YOK")

if __name__ == "__main__":
    check_missing_columns()
    check_specific_columns() 