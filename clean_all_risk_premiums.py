import pandas as pd
import glob
import os

def clean_all_risk_premiums():
    """
    Tüm YEK dosyalarından Adjusted Risk Premium ve All-Inc Risk Prim kolonlarını siler
    """
    print("=== Tüm Risk Premium Kolonlarını Temizleme ===")
    
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
            
            # Silinecek kolonları belirle
            columns_to_remove = []
            
            # Adjusted Risk Premium kolonlarını bul
            for col in df.columns:
                if 'Adjusted Risk Premium' in col or 'Adjusted Risk Prem' in col:
                    columns_to_remove.append(col)
                    print(f"    Silinecek: {col}")
            
            # All-Inc Risk Prim kolonlarını bul
            for col in df.columns:
                if 'All-Inc Risk Prim' in col:
                    columns_to_remove.append(col)
                    print(f"    Silinecek: {col}")
            
            # Kolonları sil
            if columns_to_remove:
                df = df.drop(columns=columns_to_remove)
                print(f"    {len(columns_to_remove)} kolon silindi")
                
                # Dosyayı kaydet
                df.to_csv(yek_file, index=False)
                print(f"    {yek_file} güncellendi")
                total_processed += 1
            else:
                print(f"    Silinecek kolon bulunamadı")
                
        except Exception as e:
            print(f"    HATA: {e}")
    
    print(f"\n=== Temizlik Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    clean_all_risk_premiums() 