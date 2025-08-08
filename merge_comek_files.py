import pandas as pd
import glob
import os

def merge_comek_files():
    """Tüm comek ile başlayan CSV dosyalarını birleştir"""
    
    # comek ile başlayan tüm CSV dosyalarını bul
    comek_files = glob.glob('comek*.csv')
    
    print(f"Bulunan comek dosyaları: {len(comek_files)}")
    for file in comek_files:
        print(f"  - {file}")
    
    if not comek_files:
        print("Hiç comek dosyası bulunamadı!")
        return
    
    # Tüm dosyaları birleştir
    all_dataframes = []
    
    for file in comek_files:
        try:
            print(f"\n{file} dosyası okunuyor...")
            df = pd.read_csv(file, encoding='utf-8-sig')
            
            # Dosya adını kaynak olarak ekle
            df['SOURCE_FILE'] = file
            
            # Satır sayısını göster
            print(f"  - {len(df)} satır okundu")
            
            all_dataframes.append(df)
            
        except Exception as e:
            print(f"Hata: {file} dosyası okunamadı - {e}")
    
    if not all_dataframes:
        print("Hiç dosya okunamadı!")
        return
    
    # Tüm dataframeleri birleştir
    print(f"\nTüm dosyalar birleştiriliyor...")
    merged_df = pd.concat(all_dataframes, ignore_index=True)
    
    print(f"Toplam {len(merged_df)} satır birleştirildi")
    
    # Tekrar eden satırları kontrol et
    print(f"Benzersiz PREF IBKR sayısı: {merged_df['PREF IBKR'].nunique()}")
    
    # Tekrar eden hisseleri göster
    duplicates = merged_df[merged_df.duplicated(subset=['PREF IBKR'], keep=False)]
    if not duplicates.empty:
        print(f"\nTekrar eden hisseler ({len(duplicates)} adet):")
        duplicate_counts = duplicates['PREF IBKR'].value_counts()
        print(duplicate_counts.head(10))
    
    # Birleştirilmiş dosyayı kaydet
    output_file = 'allcomek.csv'
    merged_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"\nBirleştirilmiş dosya '{output_file}' olarak kaydedildi")
    print(f"Toplam {len(merged_df)} satır, {merged_df['PREF IBKR'].nunique()} benzersiz hisse")
    
    # Kolonları göster
    print(f"\nKolonlar: {list(merged_df.columns)}")
    
    return merged_df

if __name__ == "__main__":
    merge_comek_files() 