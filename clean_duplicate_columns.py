import pandas as pd
import glob
import os

def clean_duplicate_columns():
    """
    YEK dosyalarındaki fazla kolonları temizler
    """
    print("=== Fazla Kolonları Temizleme ===")
    
    # YEK dosyalarını bul
    yek_files = glob.glob('yek*.csv')
    print(f"Bulunan YEK dosyaları: {len(yek_files)}")
    
    total_processed = 0
    
    for yek_file in yek_files:
        try:
            print(f"\nİşleniyor: {yek_file}")
            
            # YEK dosyasını oku
            df = pd.read_csv(yek_file)
            print(f"  {len(df)} satır okundu")
            
            # Fazla kolonları kontrol et ve temizle
            columns_to_remove = []
            
            # Eğer hem "Adjusted Risk Prem" hem "Adjusted Risk Premium" varsa
            if 'Adjusted Risk Prem' in df.columns and 'Adjusted Risk Premium' in df.columns:
                # "Adjusted Risk Prem" kolonunu kaldır, "Adjusted Risk Premium" kalsın
                columns_to_remove.append('Adjusted Risk Prem')
                print(f"  'Adjusted Risk Prem' kolonu kaldırıldı")
            
            # Fazla kolonları kaldır
            if columns_to_remove:
                df = df.drop(columns=columns_to_remove)
                df.to_csv(yek_file, index=False)
                print(f"  Fazla kolonlar temizlendi ve kaydedildi")
                total_processed += 1
            else:
                print(f"  Temizlenecek fazla kolon yok")
                
        except Exception as e:
            print(f"  HATA: {e}")
            continue
    
    print(f"\n=== İşlem Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    clean_duplicate_columns() 