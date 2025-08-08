import pandas as pd
import os
import glob

def create_ssfinek_files():
    """finek*.csv dosyalarından ssfinek*.csv dosyalarını oluştur"""
    
    print("=== SSFINEK DOSYALARI OLUŞTURULUYOR ===")
    
    # Tüm finek dosyalarını bul
    finek_files = glob.glob('finek*.csv')
    
    if not finek_files:
        print("❌ Hiç finek*.csv dosyası bulunamadı!")
        return
    
    print(f"Bulunan finek dosyaları: {len(finek_files)}")
    
    for finek_file in finek_files:
        try:
            print(f"\n--- {finek_file} işleniyor ---")
            
            # finek dosyasını oku
            df = pd.read_csv(finek_file, encoding='utf-8-sig')
            print(f"✓ {finek_file} okundu: {len(df)} satır")
            
            # ssfinek dosya adını oluştur
            ssfinek_file = finek_file.replace('finek', 'ssfinek')
            
            # Dosyayı kaydet
            df.to_csv(ssfinek_file, index=False, encoding='utf-8-sig')
            print(f"✓ {ssfinek_file} oluşturuldu: {len(df)} satır")
            
            # İlk birkaç satırı göster
            print(f"İlk 3 satır:")
            if 'PREF IBKR' in df.columns and 'CMON' in df.columns and 'Last Price' in df.columns:
                print(df.head(3)[['PREF IBKR', 'CMON', 'Last Price']].to_string())
            else:
                print(df.head(3).to_string())
                
        except Exception as e:
            print(f"❌ {finek_file} işlenirken hata: {e}")
    
    print(f"\n=== SSFINEK DOSYALARI OLUŞTURULDU ===")
    print("Tüm finek dosyaları ssfinek dosyalarına kopyalandı!")

if __name__ == "__main__":
    create_ssfinek_files() 