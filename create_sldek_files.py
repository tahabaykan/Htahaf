import pandas as pd
import os
import glob

def create_sldek_files():
    """allcomek_sld.csv'den sldek*.csv dosyalarını oluştur"""
    
    print("=== SLDEK DOSYALARI OLUŞTURULUYOR ===")
    
    # allcomek_sld.csv dosyasını oku
    try:
        df = pd.read_csv('allcomek_sld.csv', encoding='utf-8-sig')
        print(f"✓ allcomek_sld.csv okundu: {len(df)} satır")
    except FileNotFoundError:
        print("❌ allcomek_sld.csv dosyası bulunamadı!")
        return
    except Exception as e:
        print(f"❌ allcomek_sld.csv okunurken hata: {e}")
        return
    
    # Filtreleme kriterleri (örnek - gerçek kriterler dosyaya göre ayarlanmalı)
    filters = {
        'sldekheldbesmaturlu.csv': {
            'description': 'Held besmaturlu hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('BESMATURLU', na=False)
        },
        'sldekheldcilizyeniyedi.csv': {
            'description': 'Held ciliz yeniyedi hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('CILIZ', na=False)
        },
        'sldekheldcommonsuz.csv': {
            'description': 'Held commonsuz hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('COMMONSUZ', na=False)
        },
        'sldekhelddeznff.csv': {
            'description': 'Held deznff hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('DEZNFF', na=False)
        },
        'sldekheldff.csv': {
            'description': 'Held ff hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('FF', na=False)
        },
        'sldekheldflr.csv': {
            'description': 'Held flr hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('FLR', na=False)
        },
        'sldekheldgarabetaltiyedi.csv': {
            'description': 'Held garabet altiyedi hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('GARABET', na=False)
        },
        'sldekheldkuponlu.csv': {
            'description': 'Held kuponlu hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('KUPONLU', na=False)
        },
        'sldekheldkuponlukreciliz.csv': {
            'description': 'Held kuponlu kredi liz hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('KUPONLU', na=False) & x['CMON'].str.contains('KREDI', na=False)
        },
        'sldekheldkuponlukreorta.csv': {
            'description': 'Held kuponlu kredi orta hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('KUPONLU', na=False) & x['CMON'].str.contains('ORTA', na=False)
        },
        'sldekheldnff.csv': {
            'description': 'Held nff hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('NFF', na=False)
        },
        'sldekheldotelremorta.csv': {
            'description': 'Held otel re orta hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('OTEL', na=False)
        },
        'sldekheldsolidbig.csv': {
            'description': 'Held solid big hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('SOLID', na=False)
        },
        'sldekheldtitrekhc.csv': {
            'description': 'Held titrek hc hisseler',
            'filter': lambda x: x['CMON'].str.contains('HELD', na=False) & x['CMON'].str.contains('TITREK', na=False)
        },
        'sldekhighmatur.csv': {
            'description': 'High matur hisseler',
            'filter': lambda x: x['CMON'].str.contains('HIGH', na=False) & x['CMON'].str.contains('MATUR', na=False)
        },
        'sldeknotbesmaturlu.csv': {
            'description': 'Not besmaturlu hisseler',
            'filter': lambda x: x['CMON'].str.contains('NOT', na=False) & x['CMON'].str.contains('BESMATURLU', na=False)
        },
        'sldeknotcefilliquid.csv': {
            'description': 'Not cefilliquid hisseler',
            'filter': lambda x: x['CMON'].str.contains('NOT', na=False) & x['CMON'].str.contains('CEFILLIQUID', na=False)
        },
        'sldeknottitrekhc.csv': {
            'description': 'Not titrek hc hisseler',
            'filter': lambda x: x['CMON'].str.contains('NOT', na=False) & x['CMON'].str.contains('TITREK', na=False)
        },
        'sldekrumoreddanger.csv': {
            'description': 'Rumored danger hisseler',
            'filter': lambda x: x['CMON'].str.contains('RUMORED', na=False) & x['CMON'].str.contains('DANGER', na=False)
        },
        'sldeksalakilliquid.csv': {
            'description': 'Salakilliquid hisseler',
            'filter': lambda x: x['CMON'].str.contains('SALAKILLIQUID', na=False)
        },
        'sldekshitremhc.csv': {
            'description': 'Shitremhc hisseler',
            'filter': lambda x: x['CMON'].str.contains('SHITREMHC', na=False)
        }
    }
    
    # Her filtre için dosya oluştur
    for filename, filter_info in filters.items():
        try:
            print(f"\n--- {filename} oluşturuluyor ---")
            print(f"Açıklama: {filter_info['description']}")
            
            # Filtreleme yap
            filtered_df = df[filter_info['filter'](df)]
            
            if len(filtered_df) > 0:
                # Dosyayı kaydet
                filtered_df.to_csv(filename, index=False, encoding='utf-8-sig')
                print(f"✓ {filename} oluşturuldu: {len(filtered_df)} satır")
                
                # İlk birkaç satırı göster
                print(f"İlk 3 satır:")
                if 'PREF IBKR' in filtered_df.columns and 'CMON' in filtered_df.columns:
                    print(filtered_df.head(3)[['PREF IBKR', 'CMON']].to_string())
                else:
                    print(filtered_df.head(3).to_string())
            else:
                print(f"⚠️ {filename} için hiç hisse bulunamadı")
                
        except Exception as e:
            print(f"❌ {filename} oluşturulurken hata: {e}")
    
    print(f"\n=== SLDEK DOSYALARI OLUŞTURULDU ===")
    print("Tüm sldek dosyaları oluşturuldu!")

if __name__ == "__main__":
    create_sldek_files() 