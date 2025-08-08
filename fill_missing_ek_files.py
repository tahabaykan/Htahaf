import pandas as pd
import os

def fill_missing_ek_files():
    """Eksik ek*.csv dosyalarını sek*.csv dosyalarından veri çekerek doldur"""
    
    # Eksik dosyalar ve kaynak dosyaları
    file_mappings = [
        {
            'missing': 'eknotbesmaturlu.csv',
            'source': 'seknotbesmaturlu.csv'
        },
        {
            'missing': 'eknotcefilliquid.csv',
            'source': 'seknotcefilliquid.csv'
        },
        {
            'missing': 'eknottitrekhc.csv',
            'source': 'seknottitrekhc.csv'
        },
        {
            'missing': 'ekrumoreddanger.csv',
            'source': 'sekrumoreddanger.csv'
        },
        {
            'missing': 'eksalakilliquid.csv',
            'source': 'seksalakilliquid.csv'
        },
        {
            'missing': 'ekshitremhc.csv',
            'source': 'sekshitremhc.csv'
        }
    ]
    
    for mapping in file_mappings:
        missing_file = mapping['missing']
        source_file = mapping['source']
        
        print(f"\n=== {missing_file} dolduruluyor ===")
        
        try:
            # Kaynak dosyayı oku
            if os.path.exists(source_file):
                source_df = pd.read_csv(source_file)
                print(f"✓ {source_file} okundu: {len(source_df)} satır")
                
                # Eksik dosyayı oku (boş olabilir)
                if os.path.exists(missing_file):
                    missing_df = pd.read_csv(missing_file)
                    print(f"✓ {missing_file} mevcut: {len(missing_df)} satır")
                else:
                    # Boş DataFrame oluştur
                    missing_df = pd.DataFrame(columns=source_df.columns)
                    print(f"✓ {missing_file} boş DataFrame oluşturuldu")
                
                # Kaynak dosyadan veriyi kopyala
                filled_df = source_df.copy()
                
                # Dosyayı kaydet
                filled_df.to_csv(missing_file, index=False, encoding='utf-8-sig')
                print(f"✓ {missing_file} dolduruldu: {len(filled_df)} satır")
                
                # İlk birkaç satırı göster
                print(f"İlk 3 satır:")
                print(filled_df.head(3)[['PREF IBKR', 'CMON', 'Last Price']].to_string())
                
            else:
                print(f"❌ {source_file} bulunamadı!")
                
        except Exception as e:
            print(f"❌ {missing_file} doldurulurken hata: {e}")
    
    print(f"\n=== TÜM DOSYALAR DOLDURULDU ===")
    print("Artık nibkrtry.py çalıştırabilirsin!")

if __name__ == "__main__":
    fill_missing_ek_files() 