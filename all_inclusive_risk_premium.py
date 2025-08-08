import pandas as pd
import glob
import os
from datetime import datetime

def create_all_inclusive_risk_premium():
    """
    Tüm hisseler için "All-Inc Risk Prim" kolonu oluşturur
    Bu kolon her hissenin son risk primi değerini (adjusted veya normal) gösterir
    """
    print("=== All-Inclusive Risk Premium Kolonu Oluşturma ===")
    
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
            
            # All-Inc Risk Prim kolonu ekle
            if 'All-Inc Risk Prim' not in df.columns:
                # Adjusted Risk Premium kolonu var mı kontrol et
                if 'Adjusted Risk Premium' in df.columns:
                    # Adjusted Risk Premium varsa onu kullan
                    df['All-Inc Risk Prim'] = df['Adjusted Risk Premium']
                    print(f"  Adjusted Risk Premium kullanıldı")
                elif 'Adjusted Risk Prem' in df.columns:
                    # Adjusted Risk Prem varsa onu kullan
                    df['All-Inc Risk Prim'] = df['Adjusted Risk Prem']
                    print(f"  Adjusted Risk Prem kullanıldı")
                else:
                    # Normal Risk Premium kullan
                    df['All-Inc Risk Prim'] = df['Risk Premium']
                    print(f"  Normal Risk Premium kullanıldı")
                
                # Dosyayı kaydet
                df.to_csv(yek_file, index=False)
                print(f"  All-Inc Risk Prim kolonu eklendi ve kaydedildi")
                total_processed += 1
            else:
                print(f"  All-Inc Risk Prim kolonu zaten mevcut")
                
        except Exception as e:
            print(f"  HATA: {e}")
            continue
    
    print(f"\n=== İşlem Tamamlandı ===")
    print(f"Toplam işlenen dosya: {total_processed}")

if __name__ == "__main__":
    create_all_inclusive_risk_premium() 